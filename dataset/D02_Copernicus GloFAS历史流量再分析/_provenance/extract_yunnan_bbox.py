"""Lossless bounding-box subset of the downloaded GloFAS NetCDF file."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "data_0.nc"
OUTPUT = "yunnan_bbox_2015_glofas_v4.nc"
TEMP = "yunnan_bbox_2015_glofas_v4.partial.nc"
BOUNDS = {"north": 29.0, "south": 21.0, "west": 97.0, "east": 107.0}
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def sha256(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b""):
            value.update(block)
    return value.hexdigest()

def main(source_sha256):
    # netCDF4's native library on this host cannot open Unicode path strings.
    # Python handles chdir; the native library receives ASCII filenames only.
    os.chdir(ROOT)
    assert not Path(OUTPUT).exists() and not Path(TEMP).exists(), "Refusing to overwrite an existing derived file"
    source_stat = Path(SOURCE).stat()
    created = datetime.now(timezone.utc).isoformat()
    verification = {"all_values_equal": True, "rtol": 0, "atol": 0, "nan_positions_preserved": True}
    stats = {"finite_values": 0, "nan_values": 0, "zero_values": 0, "min_m3_s": None, "max_m3_s": None}
    with netCDF4.Dataset(SOURCE, "r") as src:
        src.set_auto_maskandscale(False)
        lat, lon = src["latitude"][:], src["longitude"][:]
        assert np.all(np.diff(lat) < 0) and np.all(np.diff(lon) > 0)
        iy = np.flatnonzero((lat >= BOUNDS["south"]) & (lat <= BOUNDS["north"]))
        ix = np.flatnonzero((lon >= BOUNDS["west"]) & (lon <= BOUNDS["east"]))
        assert len(iy) and len(ix) and np.all(np.diff(iy) == 1) and np.all(np.diff(ix) == 1)
        selections = {"latitude": slice(int(iy[0]), int(iy[-1])+1), "longitude": slice(int(ix[0]), int(ix[-1])+1)}
        sizes = {name: len(dim) for name, dim in src.dimensions.items()}
        sizes.update(latitude=len(iy), longitude=len(ix))
        assert sizes == {"valid_time": 365, "latitude": 160, "longitude": 200}
        actual_bounds = {"latitude_min": float(lat[iy].min()), "latitude_max": float(lat[iy].max()),
                         "longitude_min": float(lon[ix].min()), "longitude_max": float(lon[ix].max())}
        source_grid_attributes = {k: src["avg_dis"].getncattr(k) for k in src["avg_dis"].ncattrs() if k.startswith("GRIB_")}
        with netCDF4.Dataset(TEMP, "w", format="NETCDF4") as dst:
            dst.setncatts({k: src.getncattr(k) for k in src.ncattrs()})
            dst.setncatts({"title": "GloFAS v4.0 2015 request: Yunnan vicinity bounding-box subset",
                "source_file": SOURCE, "source_sha256": source_sha256,
                "history": created+" lossless geographic subset; no temporal aggregation, interpolation, rescaling or province mask",
                "spatial_subset_type": "latitude_longitude_bounding_box",
                "province_boundary_mask_applied": "false",
                **{"requested_bbox_"+k: v for k,v in BOUNDS.items()},
                **{"geospatial_"+k: v for k,v in actual_bounds.items()}})
            for name, size in sizes.items():
                dst.createDimension(name, size)
            for name, variable in src.variables.items():
                attrs = {k: variable.getncattr(k) for k in variable.ncattrs() if k != "_FillValue"}
                kwargs = {}
                if "_FillValue" in variable.ncattrs():
                    kwargs["fill_value"] = variable.getncattr("_FillValue")
                if name == "avg_dis":
                    kwargs.update(zlib=True, complevel=4, shuffle=True, chunksizes=(29, len(iy), len(ix)))
                    attrs.update(GRIB_Nx=len(ix), GRIB_Ny=len(iy), GRIB_numberOfPoints=len(ix)*len(iy),
                        GRIB_latitudeOfFirstGridPointInDegrees=float(lat[iy[0]]),
                        GRIB_latitudeOfLastGridPointInDegrees=float(lat[iy[-1]]),
                        GRIB_longitudeOfFirstGridPointInDegrees=float(lon[ix[0]]),
                        GRIB_longitudeOfLastGridPointInDegrees=float(lon[ix[-1]]))
                target = dst.createVariable(name, variable.dtype, variable.dimensions, **kwargs)
                target.setncatts(attrs)
                target.set_auto_maskandscale(False)
                if name == "avg_dis":
                    for start in range(0, sizes["valid_time"], 29):
                        stop = min(start+29, sizes["valid_time"])
                        data = variable[start:stop, selections["latitude"], selections["longitude"]]
                        target[start:stop, :, :] = data
                else:
                    index = tuple(selections.get(dim, slice(None)) for dim in variable.dimensions)
                    target[...] = variable[index] if index else variable[...]
        with netCDF4.Dataset(TEMP, "r") as check:
            check.set_auto_maskandscale(False)
            for name in ("valid_time", "latitude", "longitude", "surface"):
                var = src[name]
                index = tuple(selections.get(dim, slice(None)) for dim in var.dimensions)
                expected = var[index] if index else var[...]
                assert np.array_equal(check[name][...], expected, equal_nan=True), name
            assert check["avg_dis"].dtype == src["avg_dis"].dtype
            assert check["avg_dis"].units == src["avg_dis"].units
            for start in range(0, sizes["valid_time"], 29):
                stop = min(start+29, sizes["valid_time"])
                expected = src["avg_dis"][start:stop, selections["latitude"], selections["longitude"]]
                actual = check["avg_dis"][start:stop, :, :]
                assert np.array_equal(expected, actual, equal_nan=True), (start, stop)
                finite = actual[np.isfinite(actual)]
                stats["finite_values"] += int(finite.size)
                stats["nan_values"] += int(np.isnan(actual).sum())
                stats["zero_values"] += int((actual == 0).sum())
                if finite.size:
                    lo, hi = float(finite.min()), float(finite.max())
                    stats["min_m3_s"] = lo if stats["min_m3_s"] is None else min(lo, stats["min_m3_s"])
                    stats["max_m3_s"] = hi if stats["max_m3_s"] is None else max(hi, stats["max_m3_s"])
            time = check["valid_time"]
            dates = netCDF4.num2date(time[[0,-1]], time.units, calendar=time.calendar)
            labels = [str(x) for x in dates]
            memory_bytes = int(check["avg_dis"].size*check["avg_dis"].dtype.itemsize)
        final_stat = Path(SOURCE).stat()
        # Reading may update Windows access time; only content-related fields
        # establish whether the source was replaced or written during extraction.
        stable_fields = ("st_size", "st_mtime_ns", "st_ctime_ns", "st_ino")
        assert all(getattr(final_stat,k) == getattr(source_stat,k) for k in stable_fields), "Source content metadata changed during read"
    Path(TEMP).rename(OUTPUT)
    record = {"created_at_utc": created, "source_file": SOURCE, "source_bytes": source_stat.st_size,
        "source_sha256": source_sha256, "source_stat_unchanged_during_read": True,
        "source_stat_fields_checked": list(stable_fields),
        "output_file": OUTPUT, "output_bytes": Path(OUTPUT).stat().st_size, "output_sha256": sha256(Path(OUTPUT)),
        "requested_bbox_degrees": BOUNDS, "actual_grid_center_bounds_degrees": actual_bounds,
        "province_boundary_mask_applied": False, "selection": "Inclusive coordinate bounds; rectangular Yunnan vicinity, including adjacent regions",
        "dimensions": sizes, "variable": "avg_dis", "dtype": "float32", "units": "m**3 s**-1",
        "time_labels_first_last": labels, "time_shifted": False, "uncompressed_main_variable_bytes": memory_bytes,
        "compression": {"zlib": True, "complevel": 4, "shuffle": True, "lossless": True},
        "source_variable_GRIB_attributes": {k: (v.item() if isinstance(v,np.generic) else v) for k,v in source_grid_attributes.items()},
        "verification": verification, "data_statistics": stats,
        "runtime": {"python": sys.version.split()[0], "netCDF4": netCDF4.__version__, "numpy": np.__version__},
        "script": "_provenance/extract_yunnan_bbox.py", "script_sha256": sha256(Path(__file__))}
    destination = ROOT / "_provenance/yunnan_bbox_2015_manifest.json"
    destination.write_text(json.dumps(record, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    (ROOT / "yunnan_bbox_2015_README.txt").write_text(
        "云南附近矩形区域 GloFAS v4.0 日均河流流量\r\n"
        "文件：yunnan_bbox_2015_glofas_v4.nc\r\n"
        "筛选范围：北纬21—29度、东经97—107度，网格0.05度。\r\n"
        "这是矩形子集，包含云南省及邻近地区；未按省界精确掩膜，也不是完整上游流域裁剪。\r\n"
        "变量avg_dis，单位m³/s；365个时间步×160纬度格点×200经度格点。\r\n"
        "保留原文件全部时间标签：2015-01-02 00:00至2016-01-01 00:00，没有移动或删除日期。\r\n"
        "主变量展开为46,720,000字节，磁盘文件采用无损压缩，大小见manifest。\r\n"
        "未插值、未重采样、未改数值、未将缺失值填0；全部格点值和NaN位置已与原文件对应区域核对一致。\r\n"
        "来源data_0.nc保留原样，详细校验及SHA-256见_provenance/yunnan_bbox_2015_manifest.json。\r\n",
        encoding="utf-8-sig")
    print(json.dumps({k:v for k,v in record.items() if k not in ("source_variable_GRIB_attributes",)}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha256", required=True)
    main(parser.parse_args().source_sha256)
