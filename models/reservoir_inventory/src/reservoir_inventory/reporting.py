"""Reproducible tables and plots; no invented savings percentages or date labels."""

from __future__ import annotations

from datetime import datetime, timezone
from importlib import metadata as import_metadata
import os
from pathlib import Path
import platform
import tempfile
from typing import Any

import numpy as np
import pandas as pd
import scipy

from .io import sha256_file, write_json
from .model import CaseData, InputError, Solution, comparison_metrics


SCENARIOS = ("M0", "M1", "M2")
SUM_COLUMNS = (
    "duration_hours", "inflow_m3", "evaporation_m3", "turbine_water_m3", "spill_m3",
    "hydro_mwh", "production_t", "delivery_t", "industrial_electricity_mwh",
    "other_load_mwh", "grid_net_mwh", "grid_purchase_mwh", "grid_sale_mwh",
    "grid_cost_cny", "holding_cost_cny", "production_cost_cny", "hydro_cost_cny",
    "total_cost_cny",
)
WEEKLY_COLUMNS = (
    "scenario", "week_start_date", "week_end_date", "coverage_start_date",
    "coverage_end_date", "period_count", *SUM_COLUMNS, "water_start_m3",
    "water_end_m3", "inventory_start_t", "inventory_end_t", "peak_inventory_t",
    "inventory_tonne_days", "average_inventory_t", "production_average_t_per_day",
    "hydro_average_mw", "grid_net_average_mw",
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _csv(frame: pd.DataFrame, destination: Path) -> None:
    frame.to_csv(destination, index=False, float_format="%.17g")


def _calendar_dates(labels: tuple[str, ...]) -> pd.DatetimeIndex | None:
    # An explicit ISO format avoids parsing warnings and accidental interpretation
    # of artificial labels such as period_1 as real calendar observations.
    dates = pd.to_datetime(list(labels), format="ISO8601", errors="coerce", utc=True)
    if dates.isna().any():
        return None
    return pd.DatetimeIndex(dates)


def _weekly_dispatch(case: CaseData, results: dict[str, Solution]) -> tuple[pd.DataFrame, dict[str, Any]]:
    empty = pd.DataFrame(columns=WEEKLY_COLUMNS)
    dates = _calendar_dates(tuple(case.time_labels))
    reason = None
    if dates is None:
        reason = "Non-calendar period labels: weekly aggregation is not applicable."
    elif not np.allclose(case.duration_hours, 24.0, rtol=0, atol=1e-9):
        reason = "Weekly aggregation requires 24-hour calendar-day periods; periods are not split implicitly."
    elif not (dates == dates.normalize()).all():
        reason = "Weekly aggregation requires periods beginning at calendar-day midnight."
    elif len(dates) > 1 and not np.all(np.diff(dates.asi8) == pd.Timedelta(days=1).value):
        reason = "Weekly aggregation requires consecutive chronological calendar days."
    info: dict[str, Any] = {
        "available": reason is None,
        "convention": "Monday through Sunday; partial first/last weeks retained; quantities summed, boundary states first/last.",
        "reason": reason,
        "rows": 0,
    }
    if reason is not None:
        return empty, info

    assert dates is not None
    weeks = dates.tz_convert(None).to_period("W-SUN")
    rows: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        frame = results[scenario].dispatch
        for week in weeks.unique():
            positions = np.flatnonzero(weeks == week)
            block = frame.iloc[positions]
            row: dict[str, Any] = {
                "scenario": scenario,
                "week_start_date": week.start_time.date().isoformat(),
                "week_end_date": week.end_time.date().isoformat(),
                "coverage_start_date": dates[positions[0]].date().isoformat(),
                "coverage_end_date": dates[positions[-1]].date().isoformat(),
                "period_count": len(positions),
            }
            row.update({column: float(block[column].sum()) for column in SUM_COLUMNS})
            for column in ("water_start_m3", "inventory_start_t"):
                row[column] = float(block[column].iloc[0])
            for column in ("water_end_m3", "inventory_end_t"):
                row[column] = float(block[column].iloc[-1])
            peak = max(float(block["inventory_start_t"].max()), float(block["inventory_end_t"].max()))
            pre_delivery = block["pre_delivery_inventory_t"].dropna()
            if not pre_delivery.empty:
                peak = max(peak, float(pre_delivery.max()))
            row["peak_inventory_t"] = peak
            row["inventory_tonne_days"] = float(np.dot(
                block["charged_inventory_t"], block["duration_hours"] / 24.0,
            ))
            days = row["duration_hours"] / 24.0
            row["average_inventory_t"] = row["inventory_tonne_days"] / days
            row["production_average_t_per_day"] = row["production_t"] / days
            row["hydro_average_mw"] = row["hydro_mwh"] / row["duration_hours"]
            row["grid_net_average_mw"] = row["grid_net_mwh"] / row["duration_hours"]
            rows.append(row)
    info["rows"] = len(rows)
    return pd.DataFrame(rows, columns=WEEKLY_COLUMNS), info


def _plot_comparison(case: CaseData, results: dict[str, Solution], destination: Path,
                     metrics: dict[str, Any]) -> None:
    cache = Path(tempfile.gettempdir()) / "reservoir_inventory_matplotlib"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(cache)
    import matplotlib
    matplotlib.use("Agg", force=True)
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    dates = _calendar_dates(tuple(case.time_labels))
    if dates is None:
        period_x = np.arange(1, len(case.time_labels) + 1)
        state_x = np.arange(len(case.time_labels) + 1)
        xlabel = "Period (ending)"
    else:
        period_x = dates.tz_convert(None) + pd.to_timedelta(case.duration_hours, unit="h")
        state_x = pd.DatetimeIndex([dates[0].tz_convert(None), *period_x])
        xlabel = "Date (period ending)"

    style = {
        "M0": {"color": "#555555", "linestyle": "-", "linewidth": 1.5},
        "M1": {"color": "#0072B2", "linestyle": "--", "linewidth": 1.7},
        "M2": {"color": "#D55E00", "linestyle": ":", "linewidth": 1.9},
    }
    fig, axes = plt.subplots(3, 2, figsize=(14, 10), sharex=True)
    axes = axes.ravel()
    try:
        for scenario in SCENARIOS:
            solution = results[scenario]
            frame = solution.dispatch
            kwargs = {"label": scenario, **style[scenario]}
            axes[0].plot(state_x, solution.water_state_m3 / 1e9, **kwargs)
            axes[1].plot(period_x, solution.inventory_state_t[1:], **kwargs)
            axes[2].plot(period_x, solution.production_t / (case.duration_hours / 24.0), **kwargs)
            axes[3].plot(period_x, solution.grid_net_mwh / case.duration_hours, **kwargs)
            axes[4].plot(period_x, solution.hydro_mwh / case.duration_hours, **kwargs)
            axes[5].plot(period_x, frame["total_cost_cny"].cumsum() / 1e6, **kwargs)
        titles = (
            "Reservoir storage", "End-of-period product inventory", "Production rate",
            "Net grid import (+) / export (-)", "Hydropower", "Cumulative listed operating cost",
        )
        ylabels = (
            "Billion m$^3$", "Inventory (t)", "Production (t/day)",
            "Average power (MW)", "Average power (MW)", "Million CNY",
        )
        for axis, title, ylabel in zip(axes, titles, ylabels):
            axis.set_title(title, fontsize=11)
            axis.set_ylabel(ylabel)
            axis.grid(True, alpha=0.25)
        axes[3].axhline(0.0, color="#999999", linewidth=0.7)
        for axis in axes[-2:]:
            axis.set_xlabel(xlabel)
            if dates is not None:
                locator = mdates.AutoDateLocator(minticks=3, maxticks=6)
                axis.xaxis.set_major_locator(locator)
                axis.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
        handles, labels = axes[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 0.958), frameon=False)
        fig.suptitle("Reservoir and industrial inventory: M0 / M1 / M2", fontsize=15, y=0.99)
        saving = metrics["additional_hydro_coordination_savings_cny"]
        fig.text(0.5, 0.035, f"Additional hydro coordination saving: {saving:,.2f} CNY. "
                 "Full-horizon foresight; listed operating costs only.", ha="center", fontsize=9)
        fig.text(0.5, 0.016, "Curves may overlap. Different reservoir paths at equal cost can be alternative optima; "
                 "a trajectory difference alone is not a saving.", ha="center", fontsize=8)
        fig.subplots_adjust(top=0.90, bottom=0.10, hspace=0.35, wspace=0.24)
        fig.savefig(destination, dpi=160, facecolor="white")
    finally:
        plt.close(fig)


def _versions() -> dict[str, str]:
    try:
        matplotlib_version = import_metadata.version("matplotlib")
    except import_metadata.PackageNotFoundError:
        matplotlib_version = "not installed"
    return {
        "python": platform.python_version(), "numpy": np.__version__,
        "pandas": pd.__version__, "scipy": scipy.__version__,
        "matplotlib": matplotlib_version,
    }


def write_results(case: CaseData, results: dict[str, Solution], out: Path,
                  *, plots: bool = True) -> dict[str, Any]:
    """Write an audited comparison without recalculating or altering its dispatch."""
    d = case.normalized()
    if set(results) != set(SCENARIOS):
        raise InputError("Reporting requires exactly M0, M1 and M2 results")
    fingerprint = d.fingerprint()
    for key in SCENARIOS:
        solution = results[key]
        if solution.scenario != key or solution.input_fingerprint != fingerprint:
            raise InputError("Reporting results must use the same case and matching scenario names")
        if not solution.audit.get("passed"):
            raise InputError(f"Cannot report an unaudited successful comparison: {key}")
        if solution.dispatch["period"].astype(str).tolist() != list(d.time_labels):
            raise InputError(f"{key}: dispatch period labels differ from case inputs")

    destination = Path(out)
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    metrics = comparison_metrics(results)
    for key in SCENARIOS:
        path = destination / f"{key}_dispatch.csv"
        _csv(results[key].dispatch, path)
        written.append(path)
    costs_path = destination / "cost_summary.csv"
    _csv(pd.DataFrame([results[key].summary for key in SCENARIOS]), costs_path)
    written.append(costs_path)
    weekly, weekly_info = _weekly_dispatch(d, results)
    weekly_path = destination / "weekly_dispatch.csv"
    _csv(weekly, weekly_path)
    written.append(weekly_path)

    if plots:
        plot_path = destination / "comparison.png"
        _plot_comparison(d, results, plot_path, metrics)
        written.append(plot_path)
    summary = _json_safe({
        "schema_version": 1, "case_name": d.name, "periods": len(d.time_labels),
        "total_hours": float(d.duration_hours.sum()),
        "inventory_accounting": d.inventory_accounting,
        "input_fingerprint": fingerprint, "metadata": d.metadata,
        **metrics,
        "scenario_summaries": {key: results[key].summary for key in SCENARIOS},
        "weekly_aggregation": weekly_info, "plot_written": bool(plots),
        "interpretation_notes": [
            "Savings are absolute CNY differences; no percentage is inferred from negative net operating costs.",
            "Negative cost means modeled sales revenue exceeds listed costs, not whole-company profit.",
            "Zero additional coordination saving is valid; differing paths alone do not establish an economic effect.",
            "Daily average operation does not verify intraday smelter thermal feasibility or real transmission rights.",
        ],
    })
    summary_path = destination / "comparison_summary.json"
    write_json(summary_path, summary)
    written.append(summary_path)

    source_root = Path(__file__).resolve().parents[1]
    source_hashes = {path.relative_to(source_root).as_posix(): sha256_file(path)
                     for path in sorted(source_root.rglob("*.py"))}
    write_json(destination / "run_manifest.json", _json_safe({
        "schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "case_name": d.name, "input_fingerprint": fingerprint,
        "versions": _versions(), "platform": platform.platform(),
        "input_file_sha256": d.metadata.get("input_file_sha256", {}),
        "source_data_sha256": d.metadata.get("source_data_sha256", {}),
        "case_metadata": d.metadata, "python_source_sha256": source_hashes,
        "information_assumption": metrics["information_assumption"],
        "attribution": metrics["attribution"],
        "audits": metrics["audits"], "weekly_aggregation": weekly_info,
        "plot_written": bool(plots),
        "output_sha256": {path.name: sha256_file(path) for path in written},
        "serialization": "Non-finite metadata values are recorded as JSON null; dispatch NaNs indicate not-applicable fields.",
    }))
    return summary
