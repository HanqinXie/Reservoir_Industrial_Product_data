"""Independent read-back audit; never changes model inputs, outputs or code."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
from PIL import Image
from scipy.optimize._highspy import _core as highs

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TOL = {"water_m3": 1e-4, "energy_mwh": 1e-7, "product_t": 1e-7,
       "cost_cny": 1e-3, "example_cost_cny": 1e-2, "toy_cost_cny": 1e-7}

def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))

def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def csv(path):
    return pd.read_csv(path, float_precision="round_trip")

def maxabs(values):
    return float(np.max(np.abs(np.asarray(values))))

def require(condition, message):
    if not condition:
        raise AssertionError(message)

def main():
    baseline = load(ROOT / "examples/validation_record.json")
    report = {"recorded_at_utc": datetime.now(timezone.utc).isoformat(), "absolute_tolerances_rtol_zero": TOL,
              "highs_version": ".".join(str(getattr(highs, "HIGHS_VERSION_" + x)) for x in ("MAJOR", "MINOR", "PATCH")),
              "annual_cases": [], "toy_cases": {}, "file_readability": {}}
    counts = Counter()
    files = []
    for path in sorted((ROOT / "outputs").rglob("*")):
        if not path.is_file():
            continue
        counts[path.suffix] += 1
        info = {"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)}
        if path.suffix == ".json":
            load(path)
        elif path.suffix == ".csv":
            frame = csv(path)
            info["rows"] = len(frame)
            info["columns"] = len(frame.columns)
        elif path.suffix == ".png":
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                image.load()
                info["dimensions"] = list(image.size)
        files.append(info)
    report["file_readability"] = {"all_readable": True, "extension_counts": dict(counts), "files": files}
    source_hashes = {}
    manifest = load(ROOT / "data/source_manifest.json")
    for item in manifest["outputs"]:
        value = sha(ROOT / "data" / item["path"])
        require(value == item["sha256"], "data hash mismatch: " + item["path"])
        source_hashes[item["path"]] = value
    report["source_data_manifest_hashes_match"] = source_hashes
    raw = csv(ROOT / "data/xiaowan_inflow_1979_2016.csv")
    require(len(raw) == 13880, "source row count")
    require(list(raw.date) == pd.date_range("1979-01-01", "2016-12-31").strftime("%Y-%m-%d").tolist(), "source calendar")
    for expected in baseline["annual_cases"]:
        category = expected["category"]
        out = ROOT / "outputs/demo" / category
        inputs = ROOT / "outputs/demo/inputs" / category
        summary = load(out / "comparison_summary.json")
        run = load(out / "run_manifest.json")
        for name, value in run["output_sha256"].items():
            require(sha(out / name) == value, "output manifest hash mismatch")
        for name, value in run["input_file_sha256"].items():
            require(sha(inputs / name) == value, "input hash mismatch")
        require(run["python_source_sha256"] == baseline["python_source_sha256"], "source code hashes")
        require(run["source_data_sha256"] == baseline["source_data_sha256"], "source data hashes")
        require(summary["input_fingerprint"] == expected["input_fingerprint"], "physical fingerprint")
        require(summary["periods"] == expected["days"], "calendar days")
        inflow = csv(inputs / "inflow.csv")
        industry = csv(inputs / "industry.csv")
        economics = csv(inputs / "economics.csv")
        reservoir = csv(inputs / "reservoir.csv").set_index("name").value.to_dict()
        case_record = {"category": category, "year": expected["hydrological_year"], "days": summary["periods"],
                       "input_fingerprint_matches_example": True, "scenarios": {}, "example_deltas": {},
                       "input_fingerprint": summary["input_fingerprint"]}
        dispatch = {}
        for scenario in ("M0", "M1", "M2"):
            d = csv(out / f"{scenario}_dispatch.csv")
            dispatch[scenario] = d
            require(list(d.period) == list(inflow.date), "dispatch calendar")
            require(list(d.period) == pd.date_range(f"{case_record['year']}-01-01", f"{case_record['year']}-12-31").strftime("%Y-%m-%d").tolist(), "complete year")
            water = d.water_end_m3 - d.water_start_m3 - inflow.inflow_m3 + inflow.evaporation_m3 + d.turbine_water_m3 + d.spill_m3
            energy = d.hydro_mwh + d.grid_purchase_mwh - d.grid_sale_mwh - industry.electricity_mwh_per_t*d.production_t - economics.other_load_mwh
            product = d.inventory_end_t - d.inventory_start_t - d.production_t + industry.delivery_t
            water_error, energy_error, product_error = maxabs(water), maxabs(energy), maxabs(product)
            require(water_error <= TOL["water_m3"], "water balance")
            require(energy_error <= TOL["energy_mwh"], "energy balance")
            require(product_error <= TOL["product_t"], "product balance")
            require(maxabs(d.water_start_m3.iloc[1:].to_numpy()-d.water_end_m3.iloc[:-1].to_numpy()) <= TOL["water_m3"], "water state continuity")
            require(maxabs(d.inventory_start_t.iloc[1:].to_numpy()-d.inventory_end_t.iloc[:-1].to_numpy()) <= TOL["product_t"], "inventory state continuity")
            boundary_errors = {
                "initial_water_m3": abs(float(d.water_start_m3.iloc[0])-reservoir["initial_water_m3"]),
                "terminal_water_m3": abs(float(d.water_end_m3.iloc[-1])-reservoir["terminal_water_m3"]),
                "initial_inventory_t": abs(float(d.inventory_start_t.iloc[0])-reservoir["initial_inventory_t"]),
                "terminal_inventory_t": abs(float(d.inventory_end_t.iloc[-1])-reservoir["terminal_inventory_t"]),
            }
            for key, value in boundary_errors.items():
                require(value <= TOL["water_m3" if "water" in key else "product_t"], "boundary state")
            require(np.all(d.production_t >= industry.production_min_t-TOL["product_t"]), "minimum production")
            require(np.all(d.production_t <= industry.production_max_t+TOL["product_t"]), "maximum production")
            require(np.all(d.water_end_m3 >= inflow.water_min_m3-TOL["water_m3"]), "water minimum")
            require(np.all(d.water_end_m3 <= inflow.water_max_m3+TOL["water_m3"]), "water maximum")
            require(np.all(d.pre_delivery_inventory_t <= industry.inventory_capacity_t+TOL["product_t"]), "pre-delivery warehouse")
            require(float(d.inventory_start_t.min()) >= -TOL["product_t"] and float(d.inventory_end_t.min()) >= -TOL["product_t"], "inventory nonnegative")
            require(maxabs(d.hydro_mwh-d.turbine_water_m3/(1000*reservoir["water_consumption_m3_per_kwh"])) <= TOL["energy_mwh"], "hydro conversion")
            require(np.all(d.hydro_mwh <= reservoir["hydro_capacity_mw"]*d.duration_hours+TOL["energy_mwh"]), "hydro capacity")
            require(maxabs(d.grid_net_mwh-d.grid_purchase_mwh+d.grid_sale_mwh) <= TOL["energy_mwh"], "exchange split")
            for bound, qty in (("import_limit_mw", d.grid_purchase_mwh), ("export_limit_mw", d.grid_sale_mwh)):
                finite = economics[bound].notna()
                require(np.all(qty[finite] <= economics.loc[finite, bound]*d.loc[finite, "duration_hours"]+TOL["energy_mwh"]), "grid interface")
            held = d.inventory_start_t+d.production_t/2
            require(maxabs(d.charged_inventory_t-held) <= TOL["product_t"], "charged stock")
            cost = d.grid_purchase_mwh*economics.buy_price_cny_per_mwh-d.grid_sale_mwh*economics.sell_price_cny_per_mwh + held*economics.holding_cost_cny_per_t_day*d.duration_hours/24 + d.production_t*economics.production_cost_cny_per_t+d.hydro_mwh*economics.hydro_cost_cny_per_mwh
            cost_error = abs(float(cost.sum())-summary["costs_cny"][scenario])
            require(cost_error <= TOL["cost_cny"], "cost reconstruction")
            require(summary["audits"][scenario]["passed"] and summary["audits"][scenario]["solver_status"] == 0, "solver status")
            delta = summary["costs_cny"][scenario] - expected[f"{scenario}_cost_cny"]
            require(abs(delta) <= TOL["example_cost_cny"], "example cost comparison")
            case_record["example_deltas"][f"{scenario}_cost_cny"] = delta
            case_record["scenarios"][scenario] = {"cost_cny": summary["costs_cny"][scenario], "max_water_balance_residual_m3": water_error,
                "max_energy_balance_residual_mwh": energy_error, "max_product_balance_residual_t": product_error,
                "cost_reconstruction_error_cny": cost_error, "boundary_errors": boundary_errors,
                "warehouse_peak_t": float(d.pre_delivery_inventory_t.max()), "max_post_delivery_inventory_t": float(d.post_delivery_inventory_t.max()),
                "inventory_tonne_days": float(np.dot(held, d.duration_hours/24)), "solver_audit": summary["audits"][scenario]}
        require(maxabs(dispatch["M0"].production_t-industry.baseline_production_t) <= TOL["product_t"], "M0 baseline")
        frozen = max(maxabs(dispatch["M1"][col]-dispatch["M0"][col]) for col in ("water_start_m3", "water_end_m3", "turbine_water_m3", "spill_m3"))
        require(frozen <= TOL["water_m3"], "M1 frozen M0 water plan")
        case_record["M1_max_frozen_difference_m3"] = frozen
        for key in ("inventory_savings_with_fixed_hydro_cny", "additional_hydro_coordination_savings_cny", "total_savings_cny"):
            case_record[key] = summary[key]
            delta = summary[key]-expected[key]
            case_record["example_deltas"][key] = delta
            require(abs(delta) <= TOL["example_cost_cny"], "savings comparison")
        costs = summary["costs_cny"]
        require(costs["M0"]+TOL["cost_cny"] >= costs["M1"] and costs["M1"]+TOL["cost_cny"] >= costs["M2"], "cost nesting")
        m2 = dispatch["M2"]
        delivered = m2.loc[m2.delivery_t > 0, ["period", "delivery_t", "post_delivery_inventory_t"]]
        require(len(delivered) == 12, "12 month-end deliveries")
        require(all(pd.to_datetime(delivered.period).dt.is_month_end), "month-end delivery dates")
        case_record["M2_month_end_inventory"] = delivered.to_dict(orient="records")
        monthly = m2.assign(month=pd.to_datetime(m2.period).dt.month).groupby("month").agg(
            production_t=("production_t", "sum"), delivery_t=("delivery_t", "sum"),
            post_delivery_inventory_t=("post_delivery_inventory_t", "max"))
        monthly["production_minus_delivery_t"] = monthly.production_t-monthly.delivery_t
        case_record["M2_monthly_production"] = monthly.reset_index().to_dict(orient="records")
        for metric, actual in (("M2_max_post_delivery_inventory_t", float(m2.post_delivery_inventory_t.max())), ("M2_peak_warehouse_inventory_t", float(m2.pre_delivery_inventory_t.max()))):
            require(abs(actual-expected[metric]) <= TOL["product_t"], "inventory example comparison")
            case_record[metric] = actual
        report["annual_cases"].append(case_record)
    for name, expected in baseline["repository_toy"].items():
        path = ROOT / "outputs/toy" / name
        summary = load(path / "comparison_summary.json")
        for scenario, value in expected.items():
            require(abs(summary["costs_cny"][scenario]-value) <= TOL["toy_cost_cny"], "toy cost")
            require(summary["audits"][scenario]["passed"], "toy audit")
        report["toy_cases"][name] = {"costs_cny": summary["costs_cny"], "additional_coordination_cny": summary["additional_hydro_coordination_savings_cny"], "audits": summary["audits"], "weekly_aggregation": summary["weekly_aggregation"]}
    sweep = csv(ROOT / "outputs/sweep/sensitivity.csv")
    reference = csv(ROOT / "examples/sensitivity_normal.csv")
    require(len(sweep) == 22, "22 sensitivity points")
    require(sweep.status.value_counts().to_dict() == {"optimal": 20, "invalid_input": 2}, "sweep statuses")
    require(list(sweep.parameter) == list(reference.parameter), "sweep parameter families")
    require(list(sweep.status) == list(reference.status), "sweep example statuses")
    require(list(sweep.reason.fillna("")) == list(reference.reason.fillna("")), "sweep invalid reasons")
    require(list(sweep.input_fingerprint.fillna("")) == list(reference.input_fingerprint.fillna("")), "sweep fingerprints")
    differences = {}
    for column in sweep.select_dtypes(include=[np.number]).columns:
        actual = sweep[column].to_numpy()
        ref = reference[column].to_numpy()
        require(np.array_equal(np.isnan(actual), np.isnan(ref)), "missing sensitivity metrics")
        valid = ~np.isnan(actual)
        difference = maxabs(actual[valid]-ref[valid])
        tolerance = TOL["example_cost_cny"] if "cny" in column else (TOL["water_m3"] if "m3" in column else TOL["product_t"])
        require(difference <= tolerance, "sweep numeric example comparison: " + column)
        differences[column] = difference
    report["sensitivity"] = {"points": len(sweep), "status_counts": sweep.status.value_counts().to_dict(),
        "family_counts": sweep.parameter.value_counts().to_dict(),
        "invalid_points": sweep.loc[sweep.status != "optimal", ["parameter", "value", "status", "reason"]].to_dict(orient="records"),
        "max_absolute_differences_vs_example_by_column": differences}
    require(sha(ROOT / "configs/xiaowan_demo.json") == baseline["config_sha256"], "default config hash")
    report["default_config_sha256_matches_example"] = True
    report["sensitivity_csv_identical_after_newline_normalization"] = (ROOT / "outputs/sweep/sensitivity.csv").read_text(encoding="utf-8") == (ROOT / "examples/sensitivity_normal.csv").read_text(encoding="utf-8")
    require(report["sensitivity_csv_identical_after_newline_normalization"], "sensitivity full text")
    statuses = load(ROOT / "logs/command_statuses.json")
    require(len(statuses) == 5 and all(x["exit_code"] == 0 for x in statuses), "commands completed")
    test_log = (ROOT / "logs/01_unittest.log").read_text(encoding="utf-8")
    require("Ran 19 tests" in test_log and "\nOK\n" in test_log and test_log.count(" ... ok") == 19, "test count")
    report["unit_and_io_tests"] = {"passed": 19, "failed": 0}
    require(subprocess.run(["git", "diff", "--exit-code", "HEAD"], cwd=ROOT, capture_output=True).returncode == 0, "tracked files unchanged")
    report["tracked_files_unchanged"] = True
    report["passed"] = True
    save(ROOT / "logs/result_audit.json", report)
    rows = []
    for item in report["annual_cases"]:
        rows.append({"category": item["category"], "year": item["year"], "days": item["days"],
            **{f"{key}_cost_cny": value["cost_cny"] for key, value in item["scenarios"].items()},
            **{key: item[key] for key in ("inventory_savings_with_fixed_hydro_cny", "additional_hydro_coordination_savings_cny", "total_savings_cny", "M2_max_post_delivery_inventory_t", "M2_peak_warehouse_inventory_t")},
            **{key: max(x[key] for x in item["scenarios"].values()) for key in ("max_water_balance_residual_m3", "max_energy_balance_residual_mwh", "max_product_balance_residual_t")}})
    pd.DataFrame(rows).to_csv(ROOT / "logs/annual_checked_summary.csv", index=False, float_format="%.17g")
    print(json.dumps({"passed": True, "highs_version": report["highs_version"], "readable_outputs": dict(counts), "annual_summary": rows, "sweep": report["sensitivity"]}, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
