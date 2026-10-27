"""Reproducible commands, with failed/infeasible cases reported explicitly."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

from .cases import DEFAULT_CONFIG, PROJECT_ROOT, prepare_cases, toy_case
from .io import load_input_tables, write_json
from .model import CaseData, InputError, OptimizationError, comparison_metrics, solve_comparison


def verify_toy(out: Path, *, plots: bool = True) -> dict[str, Any]:
    from .reporting import write_results

    expected = json.loads((PROJECT_ROOT / "data" / "repo_toy_expected.json").read_text(encoding="utf-8"))
    verification: dict[str, Any] = {"passed": True, "source": "data/repo_toy_expected.json", "cases": {}}
    for name, symmetric in (("export_prohibited", False), ("unlimited_symmetric_trading", True)):
        case = toy_case(symmetric_trade=symmetric)
        results = solve_comparison(case)
        reference = expected["results"][name]
        for scenario, result in results.items():
            if not np.isclose(result.objective_cny, reference[scenario]["cost"], atol=1e-7, rtol=0):
                raise OptimizationError(f"Toy {name}/{scenario} does not match repository expected cost")
        write_results(case, results, out / name, plots=plots)
        verification["cases"][name] = comparison_metrics(results)
    write_json(out / "verification.json", verification)
    return verification


def run_input_directory(inputs: Path, out: Path, *, plots: bool = True) -> dict[str, Any]:
    from .reporting import write_results

    case = load_input_tables(inputs)
    results = solve_comparison(case)
    summary = write_results(case, results, out, plots=plots)
    metrics = comparison_metrics(results)
    print(f"{case.name}: " + ", ".join(f"{key}={value.objective_cny:,.6f} CNY" for key, value in results.items()), flush=True)
    print(f"  fixed-hydro inventory savings={metrics['inventory_savings_with_fixed_hydro_cny']:,.6f}; "
          f"additional hydro coordination={metrics['additional_hydro_coordination_savings_cny']:,.6f} CNY", flush=True)
    return summary


def _normal_inventory_capacity(case: CaseData) -> float:
    stock = np.r_[case.initial_inventory_t,
                  case.initial_inventory_t + np.cumsum(case.baseline_production_t - case.delivery_t)]
    normal = float(np.max(stock))
    if case.inventory_accounting == "end_delivery":
        normal = max(normal, float(np.max(stock[:-1] + case.baseline_production_t)))
    return normal


def run_sweep(case: CaseData, out: Path) -> pd.DataFrame:
    """One-factor sweeps. Initial/terminal water and deliveries never increase with K."""
    d = case.normalized()
    minimum_load = d.metadata.get("minimum_load_fraction")
    if minimum_load is None:
        raise InputError("Capacity sweep requires metadata.minimum_load_fraction, relative to online rated capacity")
    minimum_load = float(minimum_load)
    if not 0 <= minimum_load <= 1:
        raise InputError("minimum_load_fraction must lie in [0,1]")
    baseline_rate = float(np.max(d.baseline_production_t * 24.0 / d.duration_hours))
    original_rated = float(np.max(d.production_max_t * 24.0 / d.duration_hours))
    if baseline_rate <= 0:
        raise InputError("Capacity sweep requires positive baseline production")
    total_days = float(d.duration_hours.sum() / 24.0)
    average_delivery = float(d.delivery_t.sum() / total_days)
    normal_capacity = _normal_inventory_capacity(d)
    variants: list[tuple[str, float, str, CaseData]] = []
    for multiplier in (0.25, 0.5, 0.75, 1.0, 1.5, 2.0):
        variants.append(("water_capacity_multiplier", multiplier, "fraction_of_input_capacity",
                         replace(d, water_capacity_m3=d.water_capacity_m3 * multiplier)))
    original_extra = max(0.0, float(np.max(d.inventory_capacity_t)) - normal_capacity) / max(average_delivery, 1e-12)
    for days in sorted(set((0.0, 7.0, 30.0, 60.0, 90.0, original_extra))):
        variants.append(("extra_inventory_days", days, "days_of_mean_delivery",
                         replace(d, inventory_capacity_t=normal_capacity + days * average_delivery)))
    for ratio in sorted(set((1.0, 1.025, 1.075, 1.10, 1.15, original_rated / baseline_rate))):
        rated = baseline_rate * ratio
        maximum = rated * d.duration_hours / 24.0
        variants.append(("rated_to_baseline_ratio", ratio, "rated_capacity_divided_by_peak_baseline_rate",
                         replace(d, production_max_t=maximum, production_min_t=minimum_load * maximum)))
    original_h = float(np.mean(d.holding_cost_cny_per_t_day))
    for rate in sorted(set((0.0, 1.0, 3.0, 10.0, 30.0, original_h))):
        variants.append(("holding_cost_cny_per_t_day", rate, "CNY/(t*day)",
                         replace(d, holding_cost_cny_per_t_day=rate)))
    records = []
    for parameter, value, unit, variant in variants:
        record: dict[str, Any] = {
            "parameter": parameter, "value": value, "unit": unit,
            "initial_water_m3": d.initial_water_m3, "terminal_water_m3": d.terminal_water_m3,
            "total_delivery_t": float(d.delivery_t.sum()),
        }
        try:
            results = solve_comparison(variant)
            metrics = comparison_metrics(results)
            record.update(status="optimal", reason="", input_fingerprint=variant.fingerprint())
            record.update({f"{key}_cost_cny": result.objective_cny for key, result in results.items()})
            for key in ("inventory_savings_with_fixed_hydro_cny", "additional_hydro_coordination_savings_cny", "total_savings_cny"):
                record[key] = metrics[key]
            record["M2_peak_inventory_t"] = results["M2"].summary["peak_inventory_t"]
            record["M2_spill_m3"] = results["M2"].summary["spill_m3"]
            record["water_trajectory_max_change_m3"] = metrics["water_trajectory_max_change_M2_vs_M0_m3"]
            record["max_water_balance_residual_m3"] = max(s.audit["max_water_balance_residual_m3"] for s in results.values())
        except InputError as exc:
            record.update(status="invalid_input", reason=str(exc))
        except OptimizationError as exc:
            record.update(status="solver_failure", reason=str(exc))
        records.append(record)
        print(f"{parameter}={value:.8g}: {record['status']}", flush=True)
    out.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(records)
    frame.to_csv(out / "sensitivity.csv", index=False, float_format="%.17g")
    write_json(out / "sensitivity_manifest.json", {
        "base_input_fingerprint": d.fingerprint(), "case_name": d.name,
        "method": "One parameter family at a time; same input hydrology, information, deliveries, absolute initial/terminal water and product states.",
        "normal_inventory_capacity_t": normal_capacity,
        "minimum_load_fraction_relative_to_rated_capacity": minimum_load,
        "notes": [
            "Water-capacity sweep changes K only, not inflow, power capacity, initial water or terminal water.",
            "Too-small K may invalidate the common initial/terminal state; marked invalid_input, never silently refilled or reset.",
            "Rated-capacity sweep updates both the maximum and the rated-based minimum; it may invalidate conventional production.",
            "Zero extra warehouse capacity preserves normal working inventory; this is not generally identical to zero production shifting.",
            "Each row re-optimizes M0; its M1 attribution remains conditional on the M0 plan selected by the solver.",
            "These are conditional operating-cost sensitivities, not a joint response surface or an investment NPV analysis.",
        ],
        "counts": {str(key): int(value) for key, value in frame["status"].value_counts().items()},
    })
    return frame


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Daily reservoir / industrial inventory M0/M1/M2 prototype")
    commands = parser.add_subparsers(dest="command", required=True)
    toy = commands.add_parser("verify-toy", help="Reproduce both existing repository two-period controls")
    toy.add_argument("--out", type=Path, default=Path("outputs/toy"))
    toy.add_argument("--no-plots", action="store_true")
    for command in ("prepare", "demo"):
        sub = commands.add_parser(command, help="Prepare five input tables" if command == "prepare" else "Prepare and run dry/normal/wet years")
        sub.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
        sub.add_argument("--out", type=Path, default=Path(f"outputs/{'inputs' if command == 'prepare' else 'demo'}"))
        sub.add_argument("--years", type=int, nargs="+", help="Optional explicit complete hydrological years (1979–2016)")
        if command == "demo":
            sub.add_argument("--no-plots", action="store_true")
    run = commands.add_parser("run", help="Run M0/M1/M2 on one directory of five input tables")
    run.add_argument("--inputs", type=Path, required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--no-plots", action="store_true")
    sweep = commands.add_parser("sweep", help="Four one-factor sensitivity families; infeasible cases are retained")
    sweep.add_argument("--inputs", type=Path, required=True)
    sweep.add_argument("--out", type=Path, default=Path("outputs/sweep"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "verify-toy":
            verify_toy(args.out, plots=not args.no_plots)
            print(f"Both repository toy controls passed; outputs: {args.out}")
        elif args.command == "prepare":
            cases = prepare_cases(args.config, args.out, years=args.years)
            for key, value in cases.items():
                print(f"{key}: {value}")
        elif args.command == "run":
            run_input_directory(args.inputs, args.out, plots=not args.no_plots)
        elif args.command == "demo":
            prepared = prepare_cases(args.config, args.out / "inputs", years=args.years)
            records = []
            for category, input_path in prepared.items():
                run_input_directory(input_path, args.out / category, plots=not args.no_plots)
                summary = json.loads((args.out / category / "comparison_summary.json").read_text(encoding="utf-8"))
                record = {"category": category}
                record.update({key: value for key, value in summary.items() if isinstance(value, (float, int, str))})
                costs = summary.get("costs_cny", {})
                record.update({f"{key}_cost_cny": value for key, value in costs.items()})
                records.append(record)
            pd.DataFrame(records).to_csv(args.out / "representative_years_summary.csv", index=False, float_format="%.17g")
            print(f"Completed {len(prepared)} complete hydrological years; outputs: {args.out}")
        elif args.command == "sweep":
            run_sweep(load_input_tables(args.inputs), args.out)
    except (InputError, OptimizationError, OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        if hasattr(args, "out"):
            try:
                write_json(args.out / "failure.json", {"command": args.command, "status": "failed", "reason": str(exc)})
            except OSError:
                pass
        return 2
    return 0
