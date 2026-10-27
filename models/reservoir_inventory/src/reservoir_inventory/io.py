"""Five editable source-tagged CSV input tables plus a small case metadata file."""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
from typing import Any

import numpy as np
import pandas as pd

from .model import CaseData, InputError


TABLE_NAMES = ("reservoir.csv", "inflow.csv", "industry.csv", "economics.csv", "sources.csv")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.replace([np.inf, -np.inf], np.nan).to_csv(path, index=False, float_format="%.17g")


def write_input_tables(case: CaseData, destination: Path, sources: list[dict[str, Any]]) -> None:
    d = case.normalized()
    destination.mkdir(parents=True, exist_ok=True)
    values = [
        ("water_capacity_m3", float(d.water_capacity_m3[0]), "m3", "D01_RESERVOIR;SCENARIO_HYDRO"),
        ("water_min_m3", float(d.water_min_m3[0]), "m3", "SCENARIO_HYDRO"),
        ("hydro_capacity_mw", float(d.hydro_capacity_mw[0]), "MW", "D01_RESERVOIR;SCENARIO_HYDRO"),
        ("water_consumption_m3_per_kwh", d.water_consumption_m3_per_kwh, "m3/kWh", "D01_RESERVOIR"),
        ("initial_water_m3", d.initial_water_m3, "m3", "SCENARIO_HYDRO"),
        ("terminal_water_m3", d.terminal_water_m3, "m3", "SCENARIO_HYDRO"),
        ("initial_inventory_t", d.initial_inventory_t, "t", "SCENARIO_INDUSTRY"),
        ("terminal_inventory_t", d.terminal_inventory_t, "t", "SCENARIO_INDUSTRY"),
    ]
    _write_csv(pd.DataFrame(values, columns=["name", "value", "unit", "source_id"]), destination / "reservoir.csv")
    _write_csv(pd.DataFrame({
        "date": d.time_labels, "duration_hours": d.duration_hours, "inflow_m3": d.inflow_m3,
        "evaporation_m3": d.evaporation_m3, "min_release_m3": d.min_release_m3,
        "max_release_m3": d.max_release_m3,
        "water_min_m3": d.water_min_m3[1:], "water_max_m3": d.water_capacity_m3[1:],
        "hydro_capacity_mw": d.hydro_capacity_mw,
        "source_id": "D01_INFLOW;D01_RESERVOIR;SCENARIO_HYDRO",
    }), destination / "inflow.csv")
    _write_csv(pd.DataFrame({
        "date": d.time_labels, "delivery_t": d.delivery_t,
        "baseline_production_t": d.baseline_production_t,
        "production_min_t": d.production_min_t, "production_max_t": d.production_max_t,
        "electricity_mwh_per_t": d.electricity_mwh_per_t,
        "inventory_capacity_t": d.inventory_capacity_t[1:],
        "source_id": "D17_AC;SCENARIO_CASTING;SCENARIO_INDUSTRY",
    }), destination / "industry.csv")
    _write_csv(pd.DataFrame({
        "date": d.time_labels, "buy_price_cny_per_mwh": d.buy_price_cny_per_mwh,
        "sell_price_cny_per_mwh": d.sell_price_cny_per_mwh,
        "import_limit_mw": d.import_limit_mw, "export_limit_mw": d.export_limit_mw,
        "other_load_mwh": d.other_load_mwh, "holding_cost_cny_per_t_day": d.holding_cost_cny_per_t_day,
        "production_cost_cny_per_t": d.production_cost_cny_per_t,
        "hydro_cost_cny_per_mwh": d.hydro_cost_cny_per_mwh,
        "source_id": "SCENARIO_ECONOMICS;MODEL_BOUNDARY",
    }), destination / "economics.csv")
    _write_csv(pd.DataFrame(sources), destination / "sources.csv")
    write_json(destination / "case.json", {
        "schema_version": 1, "name": d.name, "inventory_accounting": d.inventory_accounting,
        "initial_inventory_capacity_t": float(d.inventory_capacity_t[0]),
        "metadata": d.metadata, "generated_input_fingerprint": d.fingerprint(),
        "editing_note": "Editable tables are authoritative. Update source_id / sources.csv when replacing assumptions.",
    })


def load_input_tables(directory: str | Path) -> CaseData:
    root = Path(directory)
    for filename in (*TABLE_NAMES, "case.json"):
        if not (root / filename).is_file():
            raise InputError(f"Missing required input file: {root / filename}")
    meta = json.loads((root / "case.json").read_text(encoding="utf-8"))
    if meta.get("schema_version") != 1:
        raise InputError("Unsupported input schema_version")
    tables = {name: pd.read_csv(root / name, float_precision="round_trip") for name in TABLE_NAMES}
    reservoir, water, industry, economics, sources = (tables[key] for key in TABLE_NAMES)
    required = {
        "reservoir.csv": {"name", "value", "unit", "source_id"},
        "inflow.csv": {"date", "duration_hours", "inflow_m3", "evaporation_m3", "min_release_m3", "water_min_m3", "water_max_m3", "source_id"},
        "industry.csv": {"date", "delivery_t", "baseline_production_t", "production_min_t", "production_max_t", "electricity_mwh_per_t", "inventory_capacity_t", "source_id"},
        "economics.csv": {"date", "buy_price_cny_per_mwh", "sell_price_cny_per_mwh", "import_limit_mw", "export_limit_mw", "other_load_mwh", "holding_cost_cny_per_t_day", "production_cost_cny_per_t", "hydro_cost_cny_per_mwh", "source_id"},
        "sources.csv": {"source_id", "kind", "description", "source_url", "limitations"},
    }
    for name, keys in required.items():
        missing = keys - set(tables[name].columns)
        if missing:
            raise InputError(f"{name}: missing columns {sorted(missing)}")
    if reservoir["name"].duplicated().any() or sources["source_id"].duplicated().any():
        raise InputError("Duplicate reservoir parameter name or source_id")
    known_sources = set(sources["source_id"].dropna().astype(str))
    for name in TABLE_NAMES[:-1]:
        for source_list in tables[name]["source_id"]:
            if not isinstance(source_list, str) or not source_list.strip():
                raise InputError(f"{name}: every row needs a source_id")
            unknown = {source.strip() for source in source_list.split(";")} - known_sources
            if unknown:
                raise InputError(f"{name}: unregistered source_id {unknown}")
    dates = water["date"].astype(str).tolist()
    if industry["date"].astype(str).tolist() != dates or economics["date"].astype(str).tolist() != dates:
        raise InputError("Input date columns must be identical and in the same order; no silent join or filling")
    parsed = pd.to_datetime(dates, errors="raise")
    hours = water["duration_hours"].to_numpy(dtype=float)
    if len(parsed) > 1:
        intervals = np.diff(parsed.asi8) / 3.6e12
        if not np.allclose(intervals, hours[:-1], atol=1e-9, rtol=0):
            raise InputError("Dates and duration_hours must describe a continuous chronological horizon")
    parameters = reservoir.set_index("name")["value"].to_dict()
    scalar_names = ("water_capacity_m3", "water_min_m3", "hydro_capacity_mw",
                    "water_consumption_m3_per_kwh", "initial_water_m3", "terminal_water_m3",
                    "initial_inventory_t", "terminal_inventory_t")
    missing_parameters = set(scalar_names) - parameters.keys()
    if missing_parameters:
        raise InputError(f"reservoir.csv: missing parameters {sorted(missing_parameters)}")
    scalar = {name: float(parameters[name]) for name in scalar_names}
    metadata = dict(meta.get("metadata", {}))
    metadata["input_file_sha256"] = {name: sha256_file(root / name) for name in (*TABLE_NAMES, "case.json")}
    d = CaseData(
        name=meta["name"], time_labels=dates, duration_hours=hours,
        inflow_m3=water["inflow_m3"].to_numpy(), evaporation_m3=water["evaporation_m3"].to_numpy(),
        min_release_m3=water["min_release_m3"].to_numpy(),
        max_release_m3=water["max_release_m3"].fillna(np.inf).to_numpy() if "max_release_m3" in water else None,
        water_capacity_m3=np.r_[scalar.pop("water_capacity_m3"), water["water_max_m3"].to_numpy()],
        water_min_m3=np.r_[scalar.pop("water_min_m3"), water["water_min_m3"].to_numpy()],
        hydro_capacity_mw=water["hydro_capacity_mw"].to_numpy() if "hydro_capacity_mw" in water else scalar["hydro_capacity_mw"],
        delivery_t=industry["delivery_t"].to_numpy(), baseline_production_t=industry["baseline_production_t"].to_numpy(),
        production_min_t=industry["production_min_t"].to_numpy(), production_max_t=industry["production_max_t"].to_numpy(),
        inventory_capacity_t=np.r_[meta["initial_inventory_capacity_t"], industry["inventory_capacity_t"].to_numpy()],
        electricity_mwh_per_t=industry["electricity_mwh_per_t"].to_numpy(),
        buy_price_cny_per_mwh=economics["buy_price_cny_per_mwh"].to_numpy(),
        sell_price_cny_per_mwh=economics["sell_price_cny_per_mwh"].to_numpy(),
        import_limit_mw=economics["import_limit_mw"].fillna(np.inf).to_numpy(),
        export_limit_mw=economics["export_limit_mw"].fillna(np.inf).to_numpy(),
        other_load_mwh=economics["other_load_mwh"].to_numpy(),
        holding_cost_cny_per_t_day=economics["holding_cost_cny_per_t_day"].to_numpy(),
        production_cost_cny_per_t=economics["production_cost_cny_per_t"].to_numpy(),
        hydro_cost_cny_per_mwh=economics["hydro_cost_cny_per_mwh"].to_numpy(),
        inventory_accounting=meta["inventory_accounting"], metadata=metadata,
        **{key: value for key, value in scalar.items() if key != "hydro_capacity_mw"},
    )
    return d.normalized()
