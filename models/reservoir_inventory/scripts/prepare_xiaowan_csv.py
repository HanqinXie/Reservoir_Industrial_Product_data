#!/usr/bin/env python3
"""Convert the fixed, hash-verified D01 Xiaowan inputs into model-safe CSV/JSON.

This optional preparation script requires pandas and numpy. The optimization
model only reads the resulting CSV/JSON and never needs to unpickle data.
No network requests or downloaded code are executed here. Obtain the original
members from the cited Zenodo archive before running this script.

Example:
    python scripts/prepare_xiaowan_csv.py --raw-dir /path/to/data/hydro
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import io
import json
import pickle
import pickletools
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


REPOSITORY = "HanqinXie/Reservoir_Industrial_Product_data"
SOURCE_COMMIT = "cc1e9da360ef0ec6c557b3401d0bfcdab2a07913"
ZENODO_URL = "https://zenodo.org/records/19600477"
ARCHIVE_URL = "https://zenodo.org/api/records/19600477/files/data.zip/content"
ARCHIVE_SHA256_REPORTED = (
    "18a4b3861a5efd0cf2e4be619b28a6af8317b9fea7d971731a2aff12c87adf3f"
)
EXPECTED_HASHES = {
    "daily_hydro_inflow_per_dam_1979_2016_m3.pickle":
        "651e5dcd5b6a0d17fd62a77c56695b48c9cb9eb482c67721b8eec96e5489e74f",
    "dams_large.csv":
        "dae5126eb859ffcb83a3fa4c5a8a63a82906f2e515137b86d7fe3e1c9ff0ef1f",
    "reservoir_effective_capacity.pickle":
        "058f6d2ee6c703c2d71d3dbf18f066bfda9dc2550a5300053e96ea1f7d15c1ae",
    "reservoir_initial_capacity.pickle":
        "8484cc3c643a24edf0e0cba8f48da21a4b093a0194c607b324288360da68fb28",
}

# The hashes are checked before this restricted deserializer is called.
# This allow-list handles the exact, older pandas/numpy objects in D01 only.
ALLOWED_GLOBALS = {
    ("pandas.core.frame", "DataFrame"),
    ("pandas.core.series", "Series"),
    ("pandas.core.internals", "BlockManager"),
    ("pandas.core.internals", "SingleBlockManager"),
    ("pandas.core.indexes.base", "_new_Index"),
    ("pandas.core.indexes.base", "Index"),
    ("pandas.core.indexes.range", "RangeIndex"),
    ("pandas.core.indexes.numeric", "Int64Index"),
    ("pandas.core.indexes.datetimes", "_new_DatetimeIndex"),
    ("pandas.core.indexes.datetimes", "DatetimeIndex"),
    ("numpy.core.multiarray", "_reconstruct"),
    ("numpy", "ndarray"),
    ("numpy", "dtype"),
    ("pandas.tseries.offsets", "Day"),
    ("datetime", "timedelta"),
    ("builtins", "slice"),
}


class FixedSourceUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str):
        if (module, name) not in ALLOWED_GLOBALS:
            raise pickle.UnpicklingError(f"Disallowed pickle global: {module}.{name}")
        if (module, name) == ("pandas.core.indexes.numeric", "Int64Index"):
            return pd.Index
        if (module, name) == ("pandas.tseries.offsets", "Day"):
            return pd.offsets.Day
        return getattr(importlib.import_module(module), name)

    def persistent_load(self, pid):
        raise pickle.UnpicklingError("Persistent pickle references are not allowed")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_verified_members(raw_dir: Path) -> dict[str, bytes]:
    members = {}
    for name, expected_hash in EXPECTED_HASHES.items():
        raw = (raw_dir / name).read_bytes()
        actual = sha256_bytes(raw)
        if actual != expected_hash:
            raise ValueError(f"Refusing changed/unverified source {name}: {actual}")
        members[name] = raw
    return members


def deserialize_verified(raw: bytes):
    # Inspect without executing: protocol extension and persistent-reference
    # opcodes are unnecessary for these exact sources and are rejected.
    blocked = {"EXT1", "EXT2", "EXT4", "PERSID", "BINPERSID"}
    for opcode, _, _ in pickletools.genops(raw):
        if opcode.name in blocked:
            raise pickle.UnpicklingError(f"Disallowed pickle opcode: {opcode.name}")
    return FixedSourceUnpickler(io.BytesIO(raw)).load()


def write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def select_years(annual: pd.DataFrame) -> dict:
    """Nearest observed calendar-year volume to linear empirical quantiles.

    Ties use the earlier year. All 365/366 days are retained. Selection uses
    annual total volume, not a 365-day normalization or a seasonal drought
    index. Hence these labels characterize annual volume only.
    """
    selected = {}
    used = set()
    for regime, quantile in (("dry", 0.2), ("normal", 0.5), ("wet", 0.8)):
        target = float(annual["total_inflow_m3"].quantile(quantile, interpolation="linear"))
        candidates = annual.loc[~annual["year"].isin(used)].copy()
        candidates["distance"] = (candidates["total_inflow_m3"] - target).abs()
        row = candidates.sort_values(["distance", "year"]).iloc[0]
        year = int(row["year"])
        used.add(year)
        selected[regime] = {
            "quantile": quantile,
            "target_total_inflow_m3": target,
            "year": year,
            "days": int(row["days"]),
            "total_inflow_m3": float(row["total_inflow_m3"]),
            "distance_from_quantile_m3": float(row["distance"]),
        }
    return selected


def prepare(raw_dir: Path, output_dir: Path) -> dict:
    members = read_verified_members(raw_dir)
    inflows = deserialize_verified(
        members["daily_hydro_inflow_per_dam_1979_2016_m3.pickle"]
    )
    dams = pd.read_csv(io.BytesIO(members["dams_large.csv"]))
    effective = deserialize_verified(members["reservoir_effective_capacity.pickle"])
    original_initial = deserialize_verified(members["reservoir_initial_capacity.pickle"])

    expected_dates = pd.date_range("1979-01-01", "2016-12-31", freq="D")
    if not isinstance(inflows, pd.DataFrame) or inflows.shape != (13880, 43):
        raise ValueError("Unexpected D01 inflow shape")
    if not inflows.index.equals(expected_dates):
        raise ValueError("D01 date index has gaps, duplicates, or unexpected bounds")
    if list(inflows.columns) != dams["Dam_names"].tolist():
        raise ValueError("Dam metadata order does not match the inflow columns")
    xiaowan_idx = dams.index[dams["Dam_names"].eq("Xiaowan")].tolist()
    if len(xiaowan_idx) != 1:
        raise ValueError("Expected exactly one Xiaowan metadata record")
    k = xiaowan_idx[0]
    dam = dams.loc[k]
    series = inflows["Xiaowan"]
    if not np.isfinite(series.to_numpy()).all() or (series < 0).any():
        raise ValueError("Xiaowan inflow contains nonfinite or negative values")
    if (series == 100000.0).any():
        raise ValueError("Unexpected 100000 m3/day floor value in Xiaowan")

    active_capacity = float(effective.iloc[k])
    power_capacity = float(dam["installed_capacity_10MW"]) * 10.0
    consumption = float(dam["Water_consumption_factor_avg"])
    if (active_capacity, power_capacity, consumption) != (1e10, 4200.0, 1.85):
        raise ValueError("Xiaowan metadata no longer matches the selected baseline")

    daily = pd.DataFrame({
        "date": expected_dates.strftime("%Y-%m-%d"),
        "inflow_m3": series.to_numpy(),
    })
    annual = series.groupby(series.index.year).agg(["size", "sum", "mean"])
    annual = annual.rename(columns={
        "size": "days", "sum": "total_inflow_m3", "mean": "mean_daily_inflow_m3"
    }).rename_axis("year").reset_index()
    annual["mean_flow_m3_per_s"] = annual["mean_daily_inflow_m3"] / 86400.0
    annual["volume_rank_ascending"] = (
        annual["total_inflow_m3"].rank(method="first").astype(int)
    )
    for row in annual.itertuples(index=False):
        expected_days = len(pd.date_range(f"{row.year}-01-01", f"{row.year}-12-31"))
        if row.days != expected_days:
            raise ValueError(f"Incomplete calendar year: {row.year}")
    selected = select_years(annual)
    regime_by_year = {value["year"]: key for key, value in selected.items()}
    annual["category"] = annual["year"].map(regime_by_year).fillna("")

    reservoir = {
        "name": "Xiaowan",
        "name_zh": "小湾水库",
        "case_type": "literature_input_supported_representative_system",
        "active_capacity_m3": active_capacity,
        "power_capacity_mw": power_capacity,
        "water_consumption_m3_per_kwh": consumption,
        "selected_years": {regime: item["year"] for regime, item in selected.items()},
        "raw_data_scaled": False,
        "electric_energy_mwh_per_m3": 1.0 / (1000.0 * consumption),
        "latitude": float(dam["Lat"]),
        "longitude": float(dam["Lon"]),
        "river_in_source": str(dam["River"]),
        "province_in_source": str(dam["Province"]),
        "initial_active_storage_rule": "scenario_defined",
        "terminal_active_storage_rule": "scenario_defined_and_common_across_strategies",
        "unused_original_initial_absolute_capacity_m3": float(original_initial.iloc[k]),
        "notes_zh": [
            "模型状态为0至有效调节库容之间的活动水量；初末活动水量由同一情景给定。",
            "原始initial文件的小湾数值为11885000000 m³，未直接用作活动水量，也未自动推定死库容。",
            "采用dams_large.csv的平均耗水系数1.85 m³/kWh；它是固定系数近似，不是可变水头机组模型。",
            "原始GWh来水文件隐含1.90 m³/kWh；本数据使用原始m³来水，自行按1.85换算发电，未混用GWh文件。",
            "有效库容、装机与耗水系数取自原论文输入，尚非经工程文件逐项验证的现行调度参数。",
        ],
        "source_commit": SOURCE_COMMIT,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    daily_name = "xiaowan_inflow_1979_2016.csv"
    annual_name = "annual_hydrology.csv"
    reservoir_name = "xiaowan_reservoir.json"
    daily.to_csv(output_dir / daily_name, index=False, float_format="%.17g", lineterminator="\n")
    annual.to_csv(output_dir / annual_name, index=False, float_format="%.17g", lineterminator="\n")
    write_json(output_dir / reservoir_name, reservoir)

    # Round-trip validation: prove the deliverable retains every original value.
    reread = pd.read_csv(output_dir / daily_name, float_precision="round_trip")
    if not np.array_equal(reread["inflow_m3"].to_numpy(), series.to_numpy()):
        raise ValueError("CSV round-trip changed original inflow values")
    if reread["date"].tolist() != daily["date"].tolist():
        raise ValueError("CSV round-trip changed original dates")

    source_manifest = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Reproducible Xiaowan inputs for the preliminary reservoir-industrial-inventory model",
        "source_repository": {
            "name": REPOSITORY,
            "commit": SOURCE_COMMIT,
            "D01_manifest_path": "dataset/D01_Nature_Energy_Industrial_Overcapacity/manifest.json",
            "D01_readme_path": "dataset/D01_Nature_Energy_Industrial_Overcapacity/extracted/data/data/README.md",
        },
        "D01_source": {
            "title": "Industrial overcapacity can enable seasonal flexibility in electricity use: Supplementary Data",
            "record_url": ZENODO_URL,
            "doi": "10.5281/zenodo.19600477",
            "archive_url": ARCHIVE_URL,
            "archive_name": "data.zip",
            "archive_byte_size_reported": 106509944,
            "archive_sha256_reported_by_source_repository": ARCHIVE_SHA256_REPORTED,
            "archive_whole_file_hash_recomputed_by_this_script": False,
            "members": [
                {"archive_member": f"data/hydro/{name}", "sha256": sha256_bytes(raw),
                 "byte_size": len(raw), "verified_against_fixed_repository_manifest": True}
                for name, raw in members.items()
            ],
            "license": {
                "id": "CC-BY-4.0",
                "url": "https://creativecommons.org/licenses/by/4.0/",
                "evidence": "D01 manifest.json files[0].license.id=cc-by-4.0 at the pinned source commit",
                "attribution": "Lyu, Ruike; Li, Anna; Wang, Jianxiao; Luo, Hongxi; Shen, Yan; Guo, Hongye; Du, Ershun; Kang, Chongqing; Jenkins, Jesse (2026). Supplementary Data. Zenodo. DOI: 10.5281/zenodo.19600477.",
            },
        },
        "daily_series": {
            "output": daily_name,
            "source_column": "Xiaowan",
            "first_date": "1979-01-01",
            "last_date": "2016-12-31",
            "rows": len(daily),
            "unit": "m3 per calendar day (volume, not m3/s)",
            "mean_flow_conversion": "inflow_m3 / 86400 gives that day's mean m3/s",
            "transformations": ["select Xiaowan column", "serialize dates and original float64 values as CSV"],
            "scaling_factor": 1.0,
            "resampling": None,
            "missing_value_filling": None,
            "source_values_preserved_exactly_on_round_trip": True,
            "leap_days_retained": True,
            "missing_dates": 0,
            "duplicate_dates": 0,
            "missing_values": 0,
            "negative_values": 0,
            "days_equal_to_100000_m3": 0,
        },
        "annual_selection": {
            "output": annual_name,
            "method": "Sum every complete calendar year's daily volumes; calculate 0.20/0.50/0.80 empirical quantiles using linear interpolation; choose the nearest observed total, breaking ties by earlier year; selected years must be distinct.",
            "volume_not_365_day_normalized": True,
            "all_38_years_kept_in_daily_file": True,
            "labels_mean_annual_volume_only": True,
            "selected_years": selected,
        },
        "IAI_reference_parameter": {
            "value_mwh_per_tonne_liquid_aluminium": 13.203,
            "source_value_kwh_per_tonne": 13203,
            "year": 2025,
            "region": "China",
            "series": "Total Energy (AC)",
            "official_page": "https://international-aluminium.org/statistics/primary-aluminium-smelting-energy-intensity/",
            "api_url": "https://alvis.international-aluminium.org/api/publication/?publication=primary-aluminium-smelting-energy-intensity",
            "source_repository_path": "dataset/D17_IAI原铝冶炼能耗强度/primary-aluminium-smelting-energy-intensity_当前官网API完整响应.json",
            "source_git_blob_sha": "7fb2b202f6f043ea44bdca5341c1669ac9aaaee3",
            "sha256_reported_in_D17_provenance": "eacc7a275aaca8158534a339d0ee5745dd04e9e91655ce9d76c77c3d5e0b306b",
            "official_export_csv_sha256_reported_in_D17_provenance": "c915f5b1868b8b1efbd4b095fdadabc192d0e48d31ca54dccc89a81f68a27727",
            "value_location": "data.publication.charts.data with period.name='2025', data['3']['30'].value; row 3=Total Energy (AC), column 30=China",
            "boundary_zh": "截至电解槽铝液出槽，包括交流整流和正常冶炼辅助设施电耗（含污染控制）；不含铸造与炭素厂。",
            "casting_extra_energy_status": "Separate explicit scenario assumption; not included in 13.203 MWh/t and not supplied by this IAI series.",
            "regional_parameter_not_plant_measurement": True,
            "license_status": "not_verified",
            "license_note": "IAI data remain subject to IAI source terms; the Zenodo CC-BY license is not asserted for this separate parameter source.",
        },
        "limitations_zh": [
            "来水为原论文能源系统模型输入，未认定为小湾电站实测入库流量；无缺值不代表已完成实测验证。",
            "1979—2016是模型输入的历史水文年份，不是小湾建成后的38年运行历史。",
            "数据止于2016，不能用于声称还原2022年等近期实际干旱事件。",
            "单库代表性算例未还原上游梯级运行、区间入流、输电拓扑或某铝厂与小湾的真实直供关系。",
            "原始初始绝对库容未转换为活动水量；初末状态必须在各对照策略中使用同一明确情景。",
            "固定平均耗水系数未体现可变水头、尾水位和效率变化；发电量不是可直接相加的额外天然水源。",
            "枯、平、丰标签按全年总入流选择，不能代替季节性干旱或连续干旱指标。",
            "用2025行业能耗参数和1979—2016来水构成统一参数的历史来水情景，不是同期企业财务还原。",
            "IAI的AC参数止于铝液出槽；若库存对象为固态铝锭，铸造电耗及相关费用须另行显式建模。",
        ],
        "outputs": [
            {"path": name, "sha256": sha256_bytes((output_dir / name).read_bytes()),
             "byte_size": (output_dir / name).stat().st_size}
            for name in (daily_name, annual_name, reservoir_name)
        ],
        "preparation": {
            "script": "scripts/prepare_xiaowan_csv.py",
            "script_sha256": sha256_bytes(Path(__file__).read_bytes()),
            "pandas_version": pd.__version__,
            "numpy_version": np.__version__,
            "network_access": False,
            "model_reads_pickle": False,
        },
    }
    write_json(output_dir / "source_manifest.json", source_manifest)
    return source_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True,
                        help="Directory with the four original, hash-whitelisted D01 hydro members")
    parser.add_argument("--output-dir", type=Path,
                        default=Path(__file__).resolve().parents[1] / "data")
    args = parser.parse_args()
    manifest = prepare(args.raw_dir, args.output_dir)
    print(json.dumps({
        "output_dir": str(args.output_dir.resolve()),
        "rows": manifest["daily_series"]["rows"],
        "selected_years": manifest["annual_selection"]["selected_years"],
        "outputs": manifest["outputs"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
