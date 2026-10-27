"""Transparent toy and representative daily cases; no fitted-to-profit defaults."""

from __future__ import annotations

from pathlib import Path
import json
from typing import Any

import numpy as np
import pandas as pd

from .io import sha256_file, write_input_tables, write_json
from .model import CaseData, InputError


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "xiaowan_demo.json"


def toy_case(*, symmetric_trade: bool = False) -> CaseData:
    return CaseData(
        name="repo_two_period_symmetric" if symmetric_trade else "repo_two_period_no_export",
        time_labels=["period_1", "period_2"], duration_hours=24,
        inflow_m3=[6, 0], delivery_t=[1, 5], baseline_production_t=[1, 5],
        production_min_t=0, production_max_t=[3, 5], water_capacity_m3=3,
        initial_water_m3=0, terminal_water_m3=0, inventory_capacity_t=2,
        initial_inventory_t=0, terminal_inventory_t=0,
        water_consumption_m3_per_kwh=0.001, hydro_capacity_mw=1,
        electricity_mwh_per_t=1, buy_price_cny_per_mwh=[1, 3], sell_price_cny_per_mwh=[1, 3],
        export_limit_mw=None if symmetric_trade else 0,
        holding_cost_cny_per_t_day=0.2, inventory_accounting="boundary",
        metadata={"classification": "normalized artificial unit test; not engineering evidence",
                  "expected_source": "data/repo_toy_expected.json"},
    )


def _sources(config: dict[str, Any], provenance: dict[str, Any]) -> list[dict[str, str]]:
    commit = provenance["source_repository"]["commit"]
    base = f"https://github.com/HanqinXie/Reservoir_Industrial_Product_data/blob/{commit}/"
    return [
        {"source_id": "D01_INFLOW", "kind": "literature_model_input",
         "description": "Xiaowan daily m3, 1979–2016; original float64 values, then apply the stated scenario hydro scale",
         "source_url": provenance["D01_source"]["record_url"],
         "limitations": "Not verified measured inflow; historical hydrology years are not 38 years of actual plant operation."},
        {"source_id": "D01_RESERVOIR", "kind": "literature_model_input",
         "description": "Xiaowan active capacity 1e10 m3, 4200 MW, average water consumption 1.85 m3/kWh before scenario scaling",
         "source_url": base + provenance["source_repository"]["D01_manifest_path"],
         "limitations": "Fixed-head proxy; original absolute initial storage is not used; original GWh series is not used."},
        {"source_id": "D17_AC", "kind": "industry_regional_statistic",
         "description": "2025 China Total Energy AC = 13.203 MWh/t liquid aluminium",
         "source_url": provenance["IAI_reference_parameter"]["official_page"],
         "limitations": "Includes rectifier and usual smelter auxiliaries; excludes casting and carbon plant. Not a specific factory measurement."},
        {"source_id": "SCENARIO_HYDRO", "kind": "assumption",
         "description": json.dumps(config["hydro"], ensure_ascii=False), "source_url": "",
         "limitations": "R, K and P scaled together; initial/terminal active fractions and zero losses/ecological minimum are assumptions, not operating rules."},
        {"source_id": "SCENARIO_INDUSTRY", "kind": "assumption",
         "description": json.dumps(config["industry"], ensure_ascii=False), "source_url": "",
         "limitations": "Fixed online capacity; daily average load bounds are not thermally validated sustained operating capability. No shutdown/restart."},
        {"source_id": "SCENARIO_CASTING", "kind": "assumption",
         "description": f"Additional casting electricity {config['industry']['casting_mwh_per_t_assumed']} MWh/t",
         "source_url": "", "limitations": "Unverified incremental energy; smelting AC and DC are never added together."},
        {"source_id": "SCENARIO_ECONOMICS", "kind": "assumption",
         "description": json.dumps(config["economics"], ensure_ascii=False), "source_url": "",
         "limitations": "Illustrative prices, warehouse costs and interfaces; not actual site tariff, market settlement or grid access entitlement."},
        {"source_id": "MODEL_BOUNDARY", "kind": "model_definition",
         "description": "One reservoir, one solid-product factory, a lossless common electrical bus and external trade; common fixed deliveries and terminal states",
         "source_url": "", "limitations": "Perfect foresight operating-cost comparison; excludes capex, actual transmission topology, taxes, game theory and endogenous water opportunity-cost charges."},
    ]


def _check_config(config: dict[str, Any]) -> None:
    if config.get("schema_version") != 1:
        raise InputError("Unsupported config schema_version")
    hydro, industry, economics = (config[key] for key in ("hydro", "industry", "economics"))
    if hydro["scale"] <= 0 or not np.isfinite(hydro["scale"]):
        raise InputError("hydro.scale must be positive and finite")
    for key in ("initial_active_fraction", "terminal_active_fraction"):
        if not 0 <= hydro[key] <= 1:
            raise InputError(f"hydro.{key} must lie between 0 and 1")
    if not 0 <= industry["minimum_load_fraction"] <= industry["baseline_utilization"] <= 1:
        raise InputError("Require 0 <= minimum_load_fraction <= baseline_utilization <= 1")
    if industry["rated_t_per_day"] <= 0 or industry["extra_inventory_days"] < 0:
        raise InputError("Rated capacity must be positive; extra inventory days must be nonnegative")
    if industry["smelting_ac_mwh_per_t"] <= 0 or industry["casting_mwh_per_t_assumed"] < 0:
        raise InputError("Specific energy inputs are invalid")
    if industry["delivery_schedule"] not in {"daily", "week_end", "month_end"}:
        raise InputError("delivery_schedule must be daily, week_end, or month_end")
    if industry["delivery_schedule"] != "daily" and industry["inventory_accounting"] != "end_delivery":
        raise InputError("Batch week/month-end deliveries require end_delivery accounting in prepared daily cases")
    if any(month not in range(1, 13) for month in economics["wet_months"]):
        raise InputError("wet_months must contain calendar month numbers")


def prepare_cases(config_path: str | Path, destination: str | Path,
                  years: list[int] | None = None) -> dict[str, Path]:
    path, out = Path(config_path).resolve(), Path(destination)
    config = json.loads(path.read_text(encoding="utf-8"))
    _check_config(config)
    files = {key: (path.parent / value).resolve() for key, value in config["data"].items()}
    reservoir = json.loads(files["reservoir_json"].read_text(encoding="utf-8"))
    provenance = json.loads(files["source_manifest"].read_text(encoding="utf-8"))
    flow = pd.read_csv(files["inflow_csv"], parse_dates=["date"], float_precision="round_trip")
    if set(flow.columns) != {"date", "inflow_m3"} or flow["date"].duplicated().any():
        raise InputError("Source inflow must have unique date,inflow_m3 columns")
    if (flow["inflow_m3"] < 0).any() or not np.isfinite(flow["inflow_m3"]).all():
        raise InputError("Source inflow has invalid or negative volume")
    selected = {str(year): int(year) for year in years} if years else reservoir["selected_years"]
    h, i, e = (config[key] for key in ("hydro", "industry", "economics"))
    sources = _sources(config, provenance)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "resolved_config.json", config)
    records: dict[str, Path] = {}
    for category, year in selected.items():
        dates = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
        subset = flow.loc[flow["date"].dt.year == year].copy()
        if list(subset["date"]) != list(dates):
            raise InputError(f"Source must contain a complete chronological calendar year: {year}")
        n = len(dates)
        baseline = np.full(n, i["rated_t_per_day"] * i["baseline_utilization"])
        deliveries = np.zeros(n)
        if i["delivery_schedule"] == "daily":
            deliveries[:] = baseline
        else:
            frequency = "M" if i["delivery_schedule"] == "month_end" else "W-SUN"
            groups = dates.to_period(frequency)
            for group in groups.unique():
                positions = np.flatnonzero(groups == group)
                deliveries[positions[-1]] = baseline[positions].sum()
        baseline_stock = np.r_[0.0, np.cumsum(baseline - deliveries)]
        normal_capacity = float(np.max(baseline_stock))
        if i["inventory_accounting"] == "end_delivery":
            normal_capacity = max(normal_capacity, float(np.max(baseline_stock[:-1] + baseline)))
        average_delivery = float(deliveries.sum() / n)
        extra_capacity = i["extra_inventory_days"] * average_delivery
        active_capacity = reservoir["active_capacity_m3"] * h["scale"]
        wet = np.isin(dates.month, e["wet_months"])
        metadata = {
            "classification": config["classification"], "hydrological_category": category,
            "hydrological_year": year, "hydro_scale": h["scale"],
            "raw_reservoir_name": reservoir["name"],
            "source_repository_commit": provenance["source_repository"]["commit"],
            "source_data_sha256": {key: sha256_file(value) for key, value in files.items()},
            "rated_t_per_day": i["rated_t_per_day"], "minimum_load_fraction": i["minimum_load_fraction"],
            "baseline_utilization": i["baseline_utilization"],
            "normal_inventory_capacity_t": normal_capacity, "extra_inventory_capacity_t": extra_capacity,
            "average_delivery_t_per_day": average_delivery, "delivery_schedule": i["delivery_schedule"],
            "notes": config["notes"],
            "year_selection": provenance["annual_selection"]["method"] if not years else "Explicit user-selected complete hydrological year(s)",
        }
        case = CaseData(
            name=f"{config['name']}_{category}_{year}", time_labels=dates.strftime("%Y-%m-%d").tolist(),
            duration_hours=24, inflow_m3=subset["inflow_m3"].to_numpy() * h["scale"],
            delivery_t=deliveries, baseline_production_t=baseline,
            production_min_t=i["rated_t_per_day"] * i["minimum_load_fraction"],
            production_max_t=i["rated_t_per_day"], water_capacity_m3=active_capacity,
            initial_water_m3=active_capacity * h["initial_active_fraction"],
            terminal_water_m3=active_capacity * h["terminal_active_fraction"],
            inventory_capacity_t=normal_capacity + extra_capacity,
            initial_inventory_t=0, terminal_inventory_t=0,
            water_consumption_m3_per_kwh=reservoir["water_consumption_m3_per_kwh"],
            hydro_capacity_mw=reservoir["power_capacity_mw"] * h["scale"],
            electricity_mwh_per_t=i["smelting_ac_mwh_per_t"] + i["casting_mwh_per_t_assumed"],
            buy_price_cny_per_mwh=np.where(wet, e["wet_buy_cny_per_mwh"], e["dry_buy_cny_per_mwh"]),
            sell_price_cny_per_mwh=np.where(wet, e["wet_sell_cny_per_mwh"], e["dry_sell_cny_per_mwh"]),
            import_limit_mw=e["import_limit_mw"], export_limit_mw=e["export_limit_mw"],
            other_load_mwh=e["other_load_mw"] * 24,
            holding_cost_cny_per_t_day=e["holding_cost_cny_per_t_day"],
            production_cost_cny_per_t=e["production_cost_cny_per_t"],
            hydro_cost_cny_per_mwh=e["hydro_cost_cny_per_mwh"],
            evaporation_m3=h["evaporation_m3_per_day"], min_release_m3=h["min_release_m3_per_day"],
            inventory_accounting=i["inventory_accounting"], metadata=metadata,
        )
        destination_case = out / category
        write_input_tables(case, destination_case, sources)
        records[category] = destination_case
    write_json(out / "prepared_cases.json", {key: str(value.name) for key, value in records.items()})
    return records
