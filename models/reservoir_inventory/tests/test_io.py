"""Small integration checks for real-source preparation and editable inputs.

No annual optimization is run here. All prepared or edited files are temporary.
"""

import calendar
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reservoir_inventory.cases import DEFAULT_CONFIG, prepare_cases  # noqa: E402
from reservoir_inventory.io import TABLE_NAMES, load_input_tables, write_input_tables  # noqa: E402
from reservoir_inventory.model import InputError  # noqa: E402


class InputPreparationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="reservoir-input-check-")
        cls.root = Path(cls.temporary.name)
        cls.config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
        cls.data_files = {
            key: (DEFAULT_CONFIG.parent / value).resolve()
            for key, value in cls.config["data"].items()
        }
        cls.reservoir = json.loads(cls.data_files["reservoir_json"].read_text(encoding="utf-8"))
        cls.raw_inflow = pd.read_csv(
            cls.data_files["inflow_csv"], parse_dates=["date"], float_precision="round_trip",
        )
        cls.paths = prepare_cases(DEFAULT_CONFIG, cls.root / "prepared")
        cls.cases = {key: load_input_tables(path) for key, path in cls.paths.items()}

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_three_source_years_keep_calendar_and_scale_inflow_capacity_and_power(self):
        self.assertEqual(set(self.cases), {"dry", "normal", "wet"})
        scale = self.config["hydro"]["scale"]
        self.assertEqual(self.reservoir["selected_years"]["normal"], 1988)
        for category, year in self.reservoir["selected_years"].items():
            with self.subTest(category=category, year=year):
                case = self.cases[category]
                expected_dates = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
                expected_count = 366 if calendar.isleap(year) else 365
                self.assertEqual(len(case.time_labels), expected_count)
                self.assertEqual(list(case.time_labels), expected_dates.strftime("%Y-%m-%d").tolist())
                self.assertEqual(float(case.duration_hours.sum()), 24.0 * expected_count)
                raw = self.raw_inflow.loc[self.raw_inflow["date"].dt.year == year, "inflow_m3"]
                np.testing.assert_array_equal(case.inflow_m3, raw.to_numpy() * scale)
                np.testing.assert_array_equal(
                    case.water_capacity_m3,
                    np.full(expected_count + 1, self.reservoir["active_capacity_m3"] * scale),
                )
                np.testing.assert_array_equal(
                    case.hydro_capacity_mw,
                    np.full(expected_count, self.reservoir["power_capacity_mw"] * scale),
                )
                self.assertEqual(case.water_consumption_m3_per_kwh,
                                 self.reservoir["water_consumption_m3_per_kwh"])
        self.assertIn("1988-02-29", self.cases["normal"].time_labels)
        self.assertEqual(len(self.cases["normal"].time_labels), 366)

    def test_five_table_write_load_round_trip_preserves_physical_fingerprint(self):
        for category, case in self.cases.items():
            with self.subTest(category=category):
                metadata = json.loads((self.paths[category] / "case.json").read_text(encoding="utf-8"))
                self.assertEqual(case.fingerprint(), metadata["generated_input_fingerprint"])
                sources = pd.read_csv(self.paths[category] / "sources.csv", keep_default_na=False)
                destination = self.root / "roundtrip" / category
                write_input_tables(case, destination, sources.to_dict(orient="records"))
                self.assertEqual({file.name for file in destination.glob("*.csv")}, set(TABLE_NAMES))
                reloaded = load_input_tables(destination)
                self.assertEqual(reloaded.fingerprint(), case.fingerprint())
                self.assertEqual(reloaded.metadata["source_repository_commit"],
                                 case.metadata["source_repository_commit"])

    def test_month_end_warehouse_contains_normal_turnover_and_minimum_uses_rated_capacity(self):
        case = self.cases["normal"]
        industry = self.config["industry"]
        self.assertEqual(industry["delivery_schedule"], "month_end")
        self.assertEqual(case.inventory_accounting, "end_delivery")
        rated = industry["rated_t_per_day"]
        baseline = rated * industry["baseline_utilization"]
        expected_delivery = np.zeros(len(case.time_labels))
        dates = pd.to_datetime(case.time_labels)
        for month in range(1, 13):
            days_in_month = calendar.monthrange(1988, month)[1]
            end_position = np.flatnonzero((dates.month == month) & (dates.day == days_in_month))
            self.assertEqual(len(end_position), 1)
            expected_delivery[end_position[0]] = baseline * days_in_month
        np.testing.assert_array_equal(case.delivery_t, expected_delivery)
        np.testing.assert_array_equal(case.baseline_production_t, np.full(len(dates), baseline))
        np.testing.assert_array_equal(
            case.production_min_t, np.full(len(dates), rated * industry["minimum_load_fraction"]),
        )
        self.assertFalse(np.allclose(
            case.production_min_t, baseline * industry["minimum_load_fraction"],
        ))
        # With uniform daily output and month-end dispatch, the pre-delivery
        # normal warehouse peak is 31 days of baseline output, not 30 days.
        normal_peak = 31.0 * baseline
        extra = industry["extra_inventory_days"] * baseline
        self.assertAlmostEqual(case.metadata["normal_inventory_capacity_t"], normal_peak)
        self.assertAlmostEqual(case.metadata["extra_inventory_capacity_t"], extra)
        np.testing.assert_array_equal(
            case.inventory_capacity_t, np.full(len(dates) + 1, normal_peak + extra),
        )
        self.assertAlmostEqual(float(case.delivery_t.sum()), 366.0 * baseline)

    def test_reordered_dates_and_unregistered_sources_are_rejected(self):
        original = self.paths["normal"]
        for failure in ("one_table_order", "all_tables_reverse", "unknown_source"):
            with self.subTest(failure=failure):
                target = self.root / "invalid" / failure
                shutil.copytree(original, target)
                if failure == "one_table_order":
                    frame = pd.read_csv(target / "industry.csv", float_precision="round_trip")
                    frame.iloc[[1, 0] + list(range(2, len(frame)))].to_csv(target / "industry.csv", index=False)
                elif failure == "all_tables_reverse":
                    for filename in ("inflow.csv", "industry.csv", "economics.csv"):
                        frame = pd.read_csv(target / filename, float_precision="round_trip")
                        frame.iloc[::-1].to_csv(target / filename, index=False)
                else:
                    frame = pd.read_csv(target / "economics.csv", float_precision="round_trip")
                    frame.loc[0, "source_id"] = "UNREGISTERED_TEST_SOURCE"
                    frame.to_csv(target / "economics.csv", index=False)
                with self.assertRaises(InputError):
                    load_input_tables(target)


if __name__ == "__main__":
    unittest.main()
