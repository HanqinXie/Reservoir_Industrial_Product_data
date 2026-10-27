"""Sparse LP with physical period quantities and audited M0/M1/M2 comparisons.

Public units: m3, MWh, tonnes, hours, CNY. No implicit representative-day
weights. Water variables alone are scaled internally for conditioning.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
import hashlib
import json
from typing import Any, Sequence

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.sparse import coo_matrix


class InputError(ValueError):
    """Invalid, inconsistent or unsupported model inputs."""


class OptimizationError(RuntimeError):
    """Solver failure; never replaced by a fabricated feasible dispatch."""


def _array(value: Any, size: int, name: str, *, unlimited: bool = False) -> np.ndarray:
    if value is None:
        if not unlimited:
            raise InputError(f"{name}: missing value")
        return np.full(size, np.inf)
    try:
        arr = np.asarray(value, dtype=float)
    except (ValueError, TypeError) as exc:
        raise InputError(f"{name}: must contain numbers") from exc
    if arr.ndim == 0:
        arr = np.full(size, float(arr))
    if arr.shape != (size,):
        raise InputError(f"{name}: expected scalar or {size} values, got {arr.shape}")
    if np.isnan(arr).any() or np.isneginf(arr).any() or (not unlimited and np.isposinf(arr).any()):
        raise InputError(f"{name}: invalid non-finite value")
    return arr.copy()


@dataclass(frozen=True)
class CaseData:
    name: str
    time_labels: Sequence[str]
    duration_hours: Any
    inflow_m3: Any
    delivery_t: Any
    baseline_production_t: Any
    production_min_t: Any
    production_max_t: Any
    water_capacity_m3: Any
    initial_water_m3: float
    terminal_water_m3: float
    inventory_capacity_t: Any
    initial_inventory_t: float
    terminal_inventory_t: float
    water_consumption_m3_per_kwh: float
    hydro_capacity_mw: Any
    electricity_mwh_per_t: Any
    buy_price_cny_per_mwh: Any
    sell_price_cny_per_mwh: Any
    holding_cost_cny_per_t_day: Any
    inventory_accounting: str = "uniform"
    water_min_m3: Any = 0.0
    evaporation_m3: Any = 0.0
    min_release_m3: Any = 0.0
    max_release_m3: Any = None
    import_limit_mw: Any = None
    export_limit_mw: Any = None
    other_load_mwh: Any = 0.0
    production_cost_cny_per_t: Any = 0.0
    hydro_cost_cny_per_mwh: Any = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> "CaseData":
        """Validate all cases against the same feasible conventional production plan."""
        labels = tuple(str(label) for label in self.time_labels)
        n = len(labels)
        if n == 0 or len(set(labels)) != n:
            raise InputError("time_labels must be nonempty and unique")
        if self.inventory_accounting not in {"boundary", "uniform", "end_delivery"}:
            raise InputError("inventory_accounting must be boundary, uniform, or end_delivery")
        period_names = (
            "duration_hours", "inflow_m3", "delivery_t", "baseline_production_t",
            "production_min_t", "production_max_t", "hydro_capacity_mw",
            "electricity_mwh_per_t", "buy_price_cny_per_mwh", "sell_price_cny_per_mwh",
            "holding_cost_cny_per_t_day", "evaporation_m3", "min_release_m3",
            "other_load_mwh", "production_cost_cny_per_t", "hydro_cost_cny_per_mwh",
        )
        values = {key: _array(getattr(self, key), n, key) for key in period_names}
        for key in ("water_capacity_m3", "water_min_m3", "inventory_capacity_t"):
            values[key] = _array(getattr(self, key), n + 1, key)
        for key in ("max_release_m3", "import_limit_mw", "export_limit_mw"):
            values[key] = _array(getattr(self, key), n, key, unlimited=True)
        nonnegative = set(values) - {"buy_price_cny_per_mwh", "sell_price_cny_per_mwh"}
        for key in nonnegative:
            if (values[key] < 0).any():
                raise InputError(f"{key}: negative values are not allowed")
        if (values["duration_hours"] <= 0).any() or (values["electricity_mwh_per_t"] <= 0).any():
            raise InputError("durations and specific electricity use must be positive")
        for key in ("initial_water_m3", "terminal_water_m3", "initial_inventory_t", "terminal_inventory_t"):
            value = float(getattr(self, key))
            if not np.isfinite(value) or value < 0:
                raise InputError(f"{key}: must be a finite nonnegative number")
            values[key] = value
        c = float(self.water_consumption_m3_per_kwh)
        if not np.isfinite(c) or c <= 0:
            raise InputError("water_consumption_m3_per_kwh must be positive")
        values["water_consumption_m3_per_kwh"] = c
        if (values["buy_price_cny_per_mwh"] < values["sell_price_cny_per_mwh"]).any():
            raise InputError("buy_price must be >= sell_price in every period for convex net trading")
        for lower, upper in (("water_min_m3", "water_capacity_m3"),
                             ("production_min_t", "production_max_t"),
                             ("min_release_m3", "max_release_m3")):
            if (values[lower] > values[upper]).any():
                raise InputError(f"{lower} exceeds {upper}")
        for index, key in ((0, "initial_water_m3"), (-1, "terminal_water_m3")):
            if not values["water_min_m3"][index] <= values[key] <= values["water_capacity_m3"][index]:
                raise InputError(f"{key} lies outside the storage bounds; do not reset it during capacity sweeps")
        for index, key in ((0, "initial_inventory_t"), (-1, "terminal_inventory_t")):
            if values[key] > values["inventory_capacity_t"][index]:
                raise InputError(f"{key} exceeds inventory capacity")
        production = values["baseline_production_t"]
        tolerance = 1e-7 * max(1.0, float(np.max(production)))
        if ((production < values["production_min_t"] - tolerance).any()
                or (production > values["production_max_t"] + tolerance).any()):
            raise InputError("baseline production violates the same physical production bounds used in M1/M2")
        stock = np.r_[values["initial_inventory_t"],
                      values["initial_inventory_t"] + np.cumsum(production - values["delivery_t"])]
        if (stock < -tolerance).any() or (stock > values["inventory_capacity_t"] + tolerance).any():
            raise InputError("baseline production/delivery does not fit the inventory bounds")
        if abs(stock[-1] - values["terminal_inventory_t"]) > tolerance:
            raise InputError("baseline production does not satisfy the common terminal inventory target")
        if self.inventory_accounting == "end_delivery":
            # Capacity during a period is the lower of its endpoint limits.
            peak_limit = np.minimum(values["inventory_capacity_t"][:-1], values["inventory_capacity_t"][1:])
            if (stock[:-1] + production > peak_limit + tolerance).any():
                raise InputError("baseline pre-delivery inventory exceeds warehouse capacity")
        return replace(self, time_labels=labels, metadata=dict(self.metadata), **values)

    def fingerprint(self) -> str:
        canonical = self.normalized()
        payload = {}
        for item in fields(self):
            if item.name in {"metadata", "name"}:
                continue
            value = getattr(canonical, item.name)
            if isinstance(value, np.ndarray):
                value = [None if np.isinf(x) else float(x) for x in value]
            payload[item.name] = value
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class Solution:
    scenario: str
    objective_cny: float
    water_state_m3: np.ndarray
    turbine_water_m3: np.ndarray
    spill_m3: np.ndarray
    production_t: np.ndarray
    inventory_state_t: np.ndarray
    grid_net_mwh: np.ndarray
    hydro_mwh: np.ndarray
    dispatch: pd.DataFrame
    audit: dict[str, Any]
    summary: dict[str, Any]
    input_fingerprint: str


class _Rows:
    def __init__(self, columns: int):
        self.columns = columns
        self.row: list[int] = []
        self.col: list[int] = []
        self.data: list[float] = []
        self.rhs: list[float] = []

    def add(self, terms: dict[int, float], rhs: float) -> None:
        row = len(self.rhs)
        for col, value in terms.items():
            if value:
                self.row.append(row)
                self.col.append(col)
                self.data.append(value)
        self.rhs.append(float(rhs))

    def matrix(self):
        return coo_matrix((self.data, (self.row, self.col)),
                          shape=(len(self.rhs), self.columns)).tocsr()


def _holding_inventory(case: CaseData, inventory: np.ndarray, production: np.ndarray) -> np.ndarray:
    if case.inventory_accounting == "boundary":
        return inventory[1:]
    if case.inventory_accounting == "uniform":
        return 0.5 * (inventory[:-1] + inventory[1:])
    return inventory[:-1] + 0.5 * production


def solve(case: CaseData, scenario: str = "M2", fixed_hydro: Solution | None = None,
          *, time_limit_seconds: float = 60.0) -> Solution:
    """Optimize one model. M1 requires the complete M0 solution of identical inputs."""
    d = case.normalized()
    fingerprint = d.fingerprint()
    if scenario not in {"M0", "M1", "M2"}:
        raise InputError("scenario must be M0, M1, or M2")
    if scenario == "M1":
        if fixed_hydro is None or fixed_hydro.scenario != "M0":
            raise InputError("M1 requires a complete M0 solution")
        if fixed_hydro.input_fingerprint != fingerprint:
            raise InputError("M1 and its M0 hydro plan must use identical input data")
    elif fixed_hydro is not None:
        raise InputError("fixed_hydro is valid only for M1")

    n = len(d.time_labels)
    water_scale = max(1.0, float(max(np.max(d.water_capacity_m3), np.max(d.inflow_m3))) / 1000.0)
    energy_per_scaled_water = water_scale / (1000.0 * d.water_consumption_m3_per_kwh)
    index: dict[str, np.ndarray] = {}
    offset = 0
    for key, count in (("water", n + 1), ("inventory", n + 1), ("turbine", n),
                       ("spill", n), ("production", n), ("net", n), ("grid_cost", n)):
        index[key] = np.arange(offset, offset + count)
        offset += count
    nv = offset
    lower = np.zeros(nv)
    upper = np.full(nv, np.inf)
    w, inv, tur, spill, prod, net, gc = (index[key] for key in
                                       ("water", "inventory", "turbine", "spill", "production", "net", "grid_cost"))
    lower[w], upper[w] = d.water_min_m3 / water_scale, d.water_capacity_m3 / water_scale
    lower[w[0]] = upper[w[0]] = d.initial_water_m3 / water_scale
    lower[w[-1]] = upper[w[-1]] = d.terminal_water_m3 / water_scale
    upper[inv] = d.inventory_capacity_t
    lower[inv[0]] = upper[inv[0]] = d.initial_inventory_t
    lower[inv[-1]] = upper[inv[-1]] = d.terminal_inventory_t
    upper[tur] = d.hydro_capacity_mw * d.duration_hours / energy_per_scaled_water
    lower[prod], upper[prod] = d.production_min_t, d.production_max_t
    lower[net], upper[net] = -d.export_limit_mw * d.duration_hours, d.import_limit_mw * d.duration_hours
    lower[gc] = -np.inf  # Net sales revenue must be allowed to make this negative.
    if scenario == "M0":
        lower[prod] = upper[prod] = d.baseline_production_t
    if scenario == "M1":
        for indices, physical in ((w, fixed_hydro.water_state_m3),
                                  (tur, fixed_hydro.turbine_water_m3),
                                  (spill, fixed_hydro.spill_m3)):
            lower[indices] = upper[indices] = physical / water_scale

    objective = np.zeros(nv)
    objective[gc] = 1.0
    objective[prod] += d.production_cost_cny_per_t
    objective[tur] += d.hydro_cost_cny_per_mwh * energy_per_scaled_water
    hold = d.holding_cost_cny_per_t_day * d.duration_hours / 24.0
    if d.inventory_accounting == "boundary":
        objective[inv[1:]] += hold
    elif d.inventory_accounting == "uniform":
        objective[inv[:-1]] += hold / 2.0
        objective[inv[1:]] += hold / 2.0
    else:
        objective[inv[:-1]] += hold
        objective[prod] += hold / 2.0

    eq, ub = _Rows(nv), _Rows(nv)
    for t in range(n):
        eq.add({w[t + 1]: 1.0, w[t]: -1.0, tur[t]: 1.0, spill[t]: 1.0},
               (d.inflow_m3[t] - d.evaporation_m3[t]) / water_scale)
        eq.add({inv[t + 1]: 1.0, inv[t]: -1.0, prod[t]: -1.0}, -d.delivery_t[t])
        eq.add({tur[t]: energy_per_scaled_water, net[t]: 1.0,
                prod[t]: -d.electricity_mwh_per_t[t]}, d.other_load_mwh[t])
        for price in (d.buy_price_cny_per_mwh[t], d.sell_price_cny_per_mwh[t]):
            ub.add({net[t]: price, gc[t]: -1.0}, 0.0)
        if d.min_release_m3[t] > 0:
            ub.add({tur[t]: -1.0, spill[t]: -1.0}, -d.min_release_m3[t] / water_scale)
        if np.isfinite(d.max_release_m3[t]):
            ub.add({tur[t]: 1.0, spill[t]: 1.0}, d.max_release_m3[t] / water_scale)
        if d.inventory_accounting == "end_delivery":
            cap = min(d.inventory_capacity_t[t], d.inventory_capacity_t[t + 1])
            ub.add({inv[t]: 1.0, prod[t]: 1.0}, cap)

    aeq, aub = eq.matrix(), ub.matrix()
    beq, bub = np.asarray(eq.rhs), np.asarray(ub.rhs)
    result = linprog(objective, A_ub=aub, b_ub=bub, A_eq=aeq, b_eq=beq,
                     bounds=list(zip(lower, upper)), method="highs",
                     options={"time_limit": float(time_limit_seconds),
                              "primal_feasibility_tolerance": 1e-8,
                              "dual_feasibility_tolerance": 1e-8})
    if not result.success or result.status != 0 or result.x is None:
        raise OptimizationError(f"{d.name}/{scenario}: HiGHS status={result.status}: {result.message}")
    x = result.x
    states = x[w] * water_scale
    turbine, spill_water = x[tur] * water_scale, x[spill] * water_scale
    stock, production, exchange = x[inv].copy(), x[prod].copy(), x[net].copy()
    generation = turbine / (1000.0 * d.water_consumption_m3_per_kwh)
    purchase, sale = np.maximum(exchange, 0.0), np.maximum(-exchange, 0.0)
    grid_cost = purchase * d.buy_price_cny_per_mwh - sale * d.sell_price_cny_per_mwh
    held_stock = _holding_inventory(d, stock, production)
    holding_cost = held_stock * hold
    production_cost = production * d.production_cost_cny_per_t
    hydro_cost = generation * d.hydro_cost_cny_per_mwh
    total_cost = grid_cost + holding_cost + production_cost + hydro_cost

    matrix_violation = max(float(np.max(np.abs(aeq @ x - beq))),
                           float(np.max(np.maximum(aub @ x - bub, 0.0))),
                           float(np.max(np.maximum(lower - x, 0.0))),
                           float(np.max(np.maximum(x - upper, 0.0))))
    water_residual = states[1:] - states[:-1] - d.inflow_m3 + d.evaporation_m3 + turbine + spill_water
    product_residual = stock[1:] - stock[:-1] - production + d.delivery_t
    power_residual = generation + exchange - production * d.electricity_mwh_per_t - d.other_load_mwh
    audit: dict[str, Any] = {
        "passed": True, "max_lp_violation_internal_units": matrix_violation,
        "max_water_balance_residual_m3": float(np.max(np.abs(water_residual))),
        "max_product_balance_residual_t": float(np.max(np.abs(product_residual))),
        "max_energy_balance_residual_mwh": float(np.max(np.abs(power_residual))),
        "cost_reconstruction_error_cny": abs(float(total_cost.sum()) - float(result.fun)),
        "terminal_water_error_m3": float(states[-1] - d.terminal_water_m3),
        "terminal_inventory_error_t": float(stock[-1] - d.terminal_inventory_t),
        "water_variable_scale_m3": water_scale,
        "solver_status": int(result.status), "solver_message": str(result.message),
        "lp_variables": nv, "lp_equalities": len(eq.rhs), "lp_inequalities": len(ub.rhs),
    }
    if scenario == "M1":
        audit["max_frozen_hydro_difference_m3"] = float(max(
            np.max(np.abs(states - fixed_hydro.water_state_m3)),
            np.max(np.abs(turbine - fixed_hydro.turbine_water_m3)),
            np.max(np.abs(spill_water - fixed_hydro.spill_m3))))
    cost_tolerance = 1e-5 + 1e-8 * float(np.abs(total_cost).sum())
    if matrix_violation > 1e-5 or audit["cost_reconstruction_error_cny"] > cost_tolerance:
        audit["passed"] = False
        raise OptimizationError(f"{d.name}/{scenario}: post-solve audit failed: {audit}")

    frame = pd.DataFrame({
        "period": d.time_labels, "duration_hours": d.duration_hours,
        "inflow_m3": d.inflow_m3, "evaporation_m3": d.evaporation_m3,
        "water_start_m3": states[:-1], "water_end_m3": states[1:],
        "turbine_water_m3": turbine, "spill_m3": spill_water,
        "hydro_mwh": generation, "hydro_average_mw": generation / d.duration_hours,
        "production_t": production, "delivery_t": d.delivery_t,
        "inventory_start_t": stock[:-1], "inventory_end_t": stock[1:],
        "is_delivery_period": d.delivery_t > 0,
        "post_delivery_inventory_t": np.where(d.delivery_t > 0, stock[1:], np.nan),
        "pre_delivery_inventory_t": stock[:-1] + production if d.inventory_accounting == "end_delivery" else np.nan,
        "charged_inventory_t": held_stock,
        "industrial_electricity_mwh": production * d.electricity_mwh_per_t,
        "other_load_mwh": d.other_load_mwh, "grid_net_mwh": exchange,
        "grid_purchase_mwh": purchase, "grid_sale_mwh": sale,
        "buy_price_cny_per_mwh": d.buy_price_cny_per_mwh,
        "sell_price_cny_per_mwh": d.sell_price_cny_per_mwh,
        "grid_cost_cny": grid_cost, "holding_cost_cny": holding_cost,
        "production_cost_cny": production_cost, "hydro_cost_cny": hydro_cost,
        "total_cost_cny": total_cost,
    })
    peak_stock = float(np.max(stock))
    if d.inventory_accounting == "end_delivery":
        peak_stock = max(peak_stock, float(np.max(stock[:-1] + production)))
    summary = {
        "case_name": d.name, "scenario": scenario, "periods": n,
        "total_hours": float(d.duration_hours.sum()), "objective_cny": float(total_cost.sum()),
        "grid_cost_cny": float(grid_cost.sum()), "holding_cost_cny": float(holding_cost.sum()),
        "production_cost_cny": float(production_cost.sum()), "hydro_cost_cny": float(hydro_cost.sum()),
        "generation_mwh": float(generation.sum()), "purchase_mwh": float(purchase.sum()),
        "sale_mwh": float(sale.sum()), "spill_m3": float(spill_water.sum()),
        "production_t": float(production.sum()), "delivery_t": float(d.delivery_t.sum()),
        "peak_inventory_t": peak_stock, "inventory_tonne_days": float(np.dot(held_stock, d.duration_hours / 24.0)),
        "peak_end_period_inventory_t": float(np.max(stock[1:])),
        "max_post_delivery_inventory_t": float(np.max(stock[1:][d.delivery_t > 0])) if (d.delivery_t > 0).any() else None,
        "inventory_accounting": d.inventory_accounting, "solver": "scipy.optimize.linprog / HiGHS",
        "input_fingerprint": fingerprint, "audit_passed": True,
    }
    return Solution(scenario, float(total_cost.sum()), states, turbine, spill_water,
                    production, stock, exchange, generation, frame, audit, summary, fingerprint)


def solve_comparison(case: CaseData) -> dict[str, Solution]:
    """Nested feasible sets: C(M0) >= C(M1) >= C(M2), subject to numerical tolerance."""
    m0 = solve(case, "M0")
    m1 = solve(case, "M1", fixed_hydro=m0)
    m2 = solve(case, "M2")
    tolerance = max(1e-6, 1e-8 * max(abs(s.objective_cny) for s in (m0, m1, m2)))
    if m1.objective_cny > m0.objective_cny + tolerance or m2.objective_cny > m1.objective_cny + tolerance:
        raise OptimizationError("M0/M1/M2 cost ordering failed; review model consistency")
    return {"M0": m0, "M1": m1, "M2": m2}


def comparison_metrics(results: dict[str, Solution]) -> dict[str, Any]:
    costs = {key: value.objective_cny for key, value in results.items()}
    return {
        "costs_cny": costs,
        "inventory_savings_with_fixed_hydro_cny": costs["M0"] - costs["M1"],
        "additional_hydro_coordination_savings_cny": costs["M1"] - costs["M2"],
        "total_savings_cny": costs["M0"] - costs["M2"],
        "attribution": "M1 is conditional on the particular optimal M0 hydro plan returned by HiGHS; not a unique causal allocation.",
        "information_assumption": "All models use the same full-horizon perfect foresight.",
        "water_trajectory_max_change_M2_vs_M0_m3": float(np.max(np.abs(results["M2"].water_state_m3 - results["M0"].water_state_m3))),
        "hydro_energy_max_period_change_M2_vs_M0_mwh": float(np.max(np.abs(results["M2"].hydro_mwh - results["M0"].hydro_mwh))),
        "audits": {key: value.audit for key, value in results.items()},
    }
