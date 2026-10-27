"""Scientific regression tests for the independent reservoir/inventory LP.

Run with ``python -m unittest discover -s tests -v`` from the model directory.
The tiny numerical systems below are constructed verification examples. They do
not assert that any particular aluminum plant can operate at these load levels.
"""

from dataclasses import replace
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reservoir_inventory.model import (  # noqa: E402
    CaseData,
    InputError,
    OptimizationError,
    solve,
    solve_comparison,
)


def period_values(value, count):
    """Expand an input only for the independent accounting assertions."""
    array = np.asarray(value, dtype=float)
    if array.ndim == 0:
        return np.full(count, float(array))
    return array


def toy_case(**changes):
    """Original repository's hand-checkable two-period regression case."""
    values = dict(
        name="constructed-two-period",
        time_labels=["first", "second"],
        duration_hours=[24.0, 24.0],
        inflow_m3=[6.0, 0.0],
        delivery_t=[1.0, 5.0],
        baseline_production_t=[1.0, 5.0],
        production_min_t=0.0,
        production_max_t=[3.0, 5.0],
        water_capacity_m3=3.0,
        initial_water_m3=0.0,
        terminal_water_m3=0.0,
        inventory_capacity_t=2.0,
        initial_inventory_t=0.0,
        terminal_inventory_t=0.0,
        water_consumption_m3_per_kwh=0.001,
        hydro_capacity_mw=1.0,
        electricity_mwh_per_t=1.0,
        buy_price_cny_per_mwh=[1.0, 3.0],
        sell_price_cny_per_mwh=0.0,
        holding_cost_cny_per_t_day=0.2,
        inventory_accounting="boundary",
        export_limit_mw=0.0,
    )
    values.update(changes)
    return CaseData(**values)


class ModelScientificTests(unittest.TestCase):
    def assert_accounting(self, case, solution):
        """Recompute physical balances and the objective from public outputs.

        This deliberately does not trust Solution.audit or Solution.summary.
        """
        count = len(case.time_labels)
        period = lambda value: period_values(value, count)
        hours = period(case.duration_hours)
        days = hours / 24.0
        water = np.asarray(solution.water_state_m3)
        turbine = np.asarray(solution.turbine_water_m3)
        spill = np.asarray(solution.spill_m3)
        product = np.asarray(solution.production_t)
        stock = np.asarray(solution.inventory_state_t)
        hydro = np.asarray(solution.hydro_mwh)
        grid = np.asarray(solution.grid_net_mwh)

        self.assertEqual(water.shape, (count + 1,))
        self.assertEqual(stock.shape, (count + 1,))
        np.testing.assert_allclose(
            water[1:],
            water[:-1] + period(case.inflow_m3) - turbine - spill
            - period(case.evaporation_m3),
            rtol=1e-8, atol=1e-7,
        )
        np.testing.assert_allclose(
            stock[1:], stock[:-1] + product - period(case.delivery_t),
            rtol=1e-8, atol=1e-8,
        )
        np.testing.assert_allclose(
            hydro, turbine / (1000.0 * period(case.water_consumption_m3_per_kwh)),
            rtol=1e-8, atol=1e-8,
        )
        np.testing.assert_allclose(
            hydro + grid,
            product * period(case.electricity_mwh_per_t) + period(case.other_load_mwh),
            rtol=1e-8, atol=1e-8,
        )
        self.assertAlmostEqual(water[0], case.initial_water_m3, places=7)
        self.assertAlmostEqual(water[-1], case.terminal_water_m3, places=7)
        self.assertAlmostEqual(stock[0], case.initial_inventory_t, places=7)
        self.assertAlmostEqual(stock[-1], case.terminal_inventory_t, places=7)
        water_upper = period_values(case.water_capacity_m3, count + 1)
        water_lower = period_values(case.water_min_m3, count + 1)
        inventory_upper = period_values(case.inventory_capacity_t, count + 1)
        self.assertTrue(np.all(water <= water_upper + 1e-7))
        self.assertTrue(np.all(water >= water_lower - 1e-7))
        self.assertTrue(np.all(stock <= inventory_upper + 1e-8))
        self.assertTrue(np.all(stock >= -1e-8))
        self.assertTrue(np.all(product >= period(case.production_min_t) - 1e-8))
        self.assertTrue(np.all(product <= period(case.production_max_t) + 1e-8))
        self.assertTrue(np.all(hydro <= period(case.hydro_capacity_mw) * hours + 1e-8))
        self.assertTrue(np.all(turbine >= -1e-8))
        self.assertTrue(np.all(spill >= -1e-8))
        self.assertTrue(np.all(turbine + spill >= period(case.min_release_m3) - 1e-8))
        if case.max_release_m3 is not None:
            self.assertTrue(np.all(turbine + spill <= period(case.max_release_m3) + 1e-8))
        if case.import_limit_mw is not None:
            self.assertTrue(np.all(grid <= period(case.import_limit_mw) * hours + 1e-8))
        if case.export_limit_mw is not None:
            self.assertTrue(np.all(grid >= -period(case.export_limit_mw) * hours - 1e-8))

        if case.inventory_accounting == "boundary":
            charged_stock = stock[1:]
        elif case.inventory_accounting == "uniform":
            charged_stock = 0.5 * (stock[:-1] + stock[1:])
        elif case.inventory_accounting == "end_delivery":
            charged_stock = stock[:-1] + 0.5 * product
        else:
            self.fail("Unrecognized inventory accounting in verification helper")
        grid_cost = np.where(
            grid >= 0.0,
            period(case.buy_price_cny_per_mwh) * grid,
            period(case.sell_price_cny_per_mwh) * grid,
        ).sum()
        expected_cost = (
            grid_cost
            + np.sum(period(case.holding_cost_cny_per_t_day) * charged_stock * days)
            + np.sum(period(case.production_cost_cny_per_t) * product)
            + np.sum(period(case.hydro_cost_cny_per_mwh) * hydro)
        )
        self.assertAlmostEqual(solution.objective_cny, expected_cost, places=6)

    def test_original_two_period_export_prohibited(self):
        case = toy_case()
        results = solve_comparison(case)
        for key, expected in {"M0": 6.0, "M1": 2.4, "M2": 0.4}.items():
            self.assertAlmostEqual(results[key].objective_cny, expected, places=7)
            self.assert_accounting(case, results[key])
        np.testing.assert_allclose(results["M0"].production_t, [1.0, 5.0], atol=1e-8)
        np.testing.assert_allclose(results["M1"].production_t, [3.0, 3.0], atol=1e-8)
        np.testing.assert_allclose(results["M2"].production_t, [3.0, 3.0], atol=1e-8)
        for attribute in ("water_state_m3", "turbine_water_m3", "spill_m3"):
            np.testing.assert_allclose(
                getattr(results["M0"], attribute), getattr(results["M1"], attribute),
                atol=1e-8,
            )

    def test_unlimited_symmetric_trading_removes_additional_hydro_value(self):
        case = toy_case(export_limit_mw=None, sell_price_cny_per_mwh=[1.0, 3.0])
        results = solve_comparison(case)
        for key, expected in {"M0": 4.0, "M1": 0.4, "M2": 0.4}.items():
            self.assertAlmostEqual(results[key].objective_cny, expected, places=7)
            self.assert_accounting(case, results[key])

    def test_fixed_production_has_no_inventory_or_coordination_savings(self):
        case = toy_case(production_min_t=[1.0, 5.0], production_max_t=[1.0, 5.0])
        results = solve_comparison(case)
        for solution in results.values():
            self.assertAlmostEqual(solution.objective_cny, 6.0, places=7)
            self.assert_accounting(case, solution)

    def test_zero_inventory_under_uniform_delivery_prevents_shifting(self):
        case = toy_case(inventory_accounting="uniform", inventory_capacity_t=0.0)
        for solution in solve_comparison(case).values():
            self.assertAlmostEqual(solution.objective_cny, 6.0, places=7)
            np.testing.assert_allclose(solution.production_t, [1.0, 5.0], atol=1e-8)
            self.assert_accounting(case, solution)

    def test_initial_water_and_products_cannot_be_consumed_at_horizon_end(self):
        case = toy_case(
            time_labels=["only"], duration_hours=[24.0], inflow_m3=[0.0],
            delivery_t=[1.0], baseline_production_t=[1.0],
            production_max_t=[2.0],
            water_capacity_m3=1.0, initial_water_m3=1.0, terminal_water_m3=1.0,
            inventory_capacity_t=3.0, initial_inventory_t=1.0, terminal_inventory_t=1.0,
            buy_price_cny_per_mwh=[3.0], holding_cost_cny_per_t_day=0.0,
            inventory_accounting="uniform",
        )
        solution = solve(case)
        self.assertAlmostEqual(solution.objective_cny, 3.0, places=7)
        np.testing.assert_allclose(solution.production_t, [1.0], atol=1e-8)
        np.testing.assert_allclose(solution.hydro_mwh, [0.0], atol=1e-8)
        self.assert_accounting(case, solution)

    def test_uniform_stock_cost_scales_with_days_but_energy_cost_does_not(self):
        common = dict(
            water_capacity_m3=0.0, initial_water_m3=0.0, terminal_water_m3=0.0,
            inventory_capacity_t=2.0, initial_inventory_t=1.0, terminal_inventory_t=1.0,
            hydro_capacity_mw=0.0, buy_price_cny_per_mwh=3.0,
            holding_cost_cny_per_t_day=1.0, inventory_accounting="uniform",
        )
        one = toy_case(
            time_labels=["two-days"], duration_hours=[48.0], inflow_m3=[0.0],
            delivery_t=[1.0], baseline_production_t=[1.0],
            production_min_t=[1.0], production_max_t=[1.0], **common,
        )
        two = toy_case(
            time_labels=["day-1", "day-2"], duration_hours=[24.0, 24.0],
            inflow_m3=[0.0, 0.0], delivery_t=[0.5, 0.5],
            baseline_production_t=[0.5, 0.5],
            production_min_t=[0.5, 0.5], production_max_t=[0.5, 0.5], **common,
        )
        for case in (one, two):
            solution = solve(case)
            # 1 MWh * 3 CNY/MWh + 1 t * 2 days * 1 CNY/(t day).
            self.assertAlmostEqual(solution.objective_cny, 5.0, places=7)
            self.assert_accounting(case, solution)

    def test_end_delivery_charges_intra_period_stock_and_respects_peak(self):
        case = toy_case(
            time_labels=["two-days"], duration_hours=[48.0], inflow_m3=[0.0],
            delivery_t=[2.0], baseline_production_t=[2.0],
            production_min_t=[2.0], production_max_t=[2.0],
            water_capacity_m3=0.0, hydro_capacity_mw=0.0,
            inventory_capacity_t=2.0, buy_price_cny_per_mwh=[3.0],
            holding_cost_cny_per_t_day=1.0, inventory_accounting="end_delivery",
        )
        solution = solve(case)
        # Energy costs 6. Stock rises 0 -> 2 t over two days: holding costs 2.
        self.assertAlmostEqual(solution.objective_cny, 8.0, places=7)
        np.testing.assert_allclose(solution.inventory_state_t, [0.0, 0.0], atol=1e-8)
        self.assert_accounting(case, solution)
        # Endpoints alone would miss the required 2 t before delivery.
        with self.assertRaises((InputError, OptimizationError)):
            solve(replace(case, inventory_capacity_t=1.99))
        uniform = replace(case, inventory_accounting="uniform")
        self.assertAlmostEqual(solve(uniform).objective_cny, 6.0, places=7)

    def test_volume_scale_changes_do_not_change_energy_or_economic_results(self):
        original = toy_case()
        scaled = toy_case(
            inflow_m3=[6000.0, 0.0], water_capacity_m3=3000.0,
            water_consumption_m3_per_kwh=1.0,
        )
        first, second = solve(original), solve(scaled)
        self.assertAlmostEqual(first.objective_cny, second.objective_cny, places=7)
        for attribute in ("production_t", "inventory_state_t", "grid_net_mwh", "hydro_mwh"):
            np.testing.assert_allclose(getattr(first, attribute), getattr(second, attribute), atol=1e-8)
        for attribute in ("water_state_m3", "turbine_water_m3", "spill_m3"):
            np.testing.assert_allclose(np.asarray(getattr(first, attribute)) * 1000.0,
                                       getattr(second, attribute), atol=1e-6)
        self.assert_accounting(scaled, second)

    def test_export_revenue_may_make_objective_negative(self):
        case = toy_case(
            time_labels=["only"], duration_hours=[24.0], inflow_m3=[2.0],
            delivery_t=[1.0], baseline_production_t=[1.0],
            production_min_t=[1.0], production_max_t=[1.0],
            water_capacity_m3=2.0, inventory_capacity_t=0.0,
            buy_price_cny_per_mwh=[5.0], sell_price_cny_per_mwh=[3.0],
            holding_cost_cny_per_t_day=0.0, export_limit_mw=None,
        )
        solution = solve(case)
        self.assertAlmostEqual(solution.objective_cny, -3.0, places=7)
        np.testing.assert_allclose(solution.grid_net_mwh, [-1.0], atol=1e-8)
        self.assert_accounting(case, solution)

    def test_minimum_output_is_applied_to_the_supplied_rated_based_bound(self):
        # Purely constructed numbers: rated 11 t/period, minimum 90% => 9.9.
        # Delivering 10 in both periods permits only 0.1 t of forward shifting.
        case = toy_case(
            inflow_m3=[13.0, 7.0], delivery_t=[10.0, 10.0],
            baseline_production_t=[10.0, 10.0],
            production_min_t=0.9 * 11.0, production_max_t=11.0,
            water_capacity_m3=2.0, inventory_capacity_t=2.0,
            buy_price_cny_per_mwh=[1.0, 1.0], holding_cost_cny_per_t_day=0.1,
        )
        solution = solve(case)
        np.testing.assert_allclose(solution.production_t, [10.1, 9.9], atol=1e-8)
        self.assertAlmostEqual(solution.objective_cny, 0.91, places=7)
        self.assert_accounting(case, solution)

    def test_required_release_uses_turbine_water_and_losses_are_period_volumes(self):
        case = toy_case(
            time_labels=["two-days"], duration_hours=[48.0], inflow_m3=[3.0],
            evaporation_m3=[1.0], min_release_m3=[2.0], max_release_m3=[2.0],
            delivery_t=[2.0], baseline_production_t=[2.0],
            production_min_t=[2.0], production_max_t=[2.0],
            water_capacity_m3=3.0, inventory_capacity_t=0.0,
            buy_price_cny_per_mwh=[3.0], holding_cost_cny_per_t_day=0.0,
        )
        solution = solve(case)
        # The same 2 m3 generates 2 MWh and meets the 2 m3 downstream release.
        # Inflow and evaporation already denote totals over the 48-hour period.
        self.assertAlmostEqual(solution.objective_cny, 0.0, places=7)
        np.testing.assert_allclose(solution.turbine_water_m3, [2.0], atol=1e-8)
        np.testing.assert_allclose(solution.spill_m3, [0.0], atol=1e-8)
        self.assert_accounting(case, solution)

    def test_insufficient_water_raises_instead_of_relaxing_mandatory_release(self):
        case = toy_case(
            time_labels=["only"], duration_hours=[24.0], inflow_m3=[1.0],
            min_release_m3=[2.0],
            delivery_t=[1.0], baseline_production_t=[1.0],
            production_min_t=[1.0], production_max_t=[1.0],
            water_capacity_m3=2.0, inventory_capacity_t=0.0,
            buy_price_cny_per_mwh=[3.0], holding_cost_cny_per_t_day=0.0,
        )
        # Unlimited grid imports can meet electrical demand, but cannot create
        # the missing cubic metre or relax the common terminal water target.
        with self.assertRaises(OptimizationError):
            solve(case)

    def test_m0_degeneracy_does_not_imply_a_unique_m1_attribution(self):
        # M0 can release its one water unit in period 2 or 3 at equal cost 3.
        # Freezing those schedules yields M1 costs 2.4 and 2.2 respectively.
        # The test deliberately accepts the full range of optimal M0 selections.
        case = toy_case(
            time_labels=["early", "middle", "late"], duration_hours=24.0,
            inflow_m3=[1.0, 0.0, 0.0], delivery_t=[1.0, 1.0, 1.0],
            baseline_production_t=[1.0, 1.0, 1.0],
            production_max_t=[2.0, 1.0, 1.0], water_capacity_m3=1.0,
            inventory_capacity_t=1.0, buy_price_cny_per_mwh=[1.0, 2.0, 2.0],
        )
        results = solve_comparison(case)
        self.assertAlmostEqual(results["M0"].objective_cny, 3.0, places=7)
        self.assertAlmostEqual(results["M2"].objective_cny, 2.2, places=7)
        self.assertGreaterEqual(results["M1"].objective_cny, 2.2 - 1e-7)
        self.assertLessEqual(results["M1"].objective_cny, 2.4 + 1e-7)
        for solution in results.values():
            self.assert_accounting(case, solution)

    def test_nonconvex_buy_sell_price_order_is_rejected(self):
        with self.assertRaises(InputError):
            solve(toy_case(sell_price_cny_per_mwh=[2.0, 4.0]))

    def test_m1_rejects_hydro_plan_from_different_inputs(self):
        case = toy_case()
        fixed = solve(case, scenario="M0")
        changed = replace(case, buy_price_cny_per_mwh=[2.0, 3.0])
        with self.assertRaises(InputError):
            solve(changed, scenario="M1", fixed_hydro=fixed)


if __name__ == "__main__":
    unittest.main()
