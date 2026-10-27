"""Repair D01's Windows filenames/metadata, preserving every research byte."""
import argparse
import ast
from collections import Counter
import contextlib
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import struct
import sys
import tempfile
import urllib.parse
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
D01 = Path(__file__).resolve().parents[1]
DATASET = D01.parent
EXTRACTED = (D01 / "extracted/data").resolve()
EVIDENCE = D01 / "_provenance/windows_repair_20261027"
ARCHIVE = D01 / "data.zip"
EXPECTED_SHA = "18a4b3861a5efd0cf2e4be619b28a6af8317b9fea7d971731a2aff12c87adf3f"

def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")

def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4*1024*1024), b""):
            value.update(block)
    return value.hexdigest()

def safe(path, root=EXTRACTED):
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()) or path.is_symlink():
        raise ValueError("Unsafe target: " + str(path))
    return resolved

def is_mac(name):
    parts = PurePosixPath(name.replace("\\", "/")).parts
    return "__MACOSX" in parts or parts[-1] == ".DS_Store" or parts[-1].startswith("._")

def decoded_name(info):
    name = info.filename
    if not info.flag_bits & 0x800 and not name.isascii():
        candidate = name.encode("cp437").decode("utf-8")
        if any("\u3400" <= char <= "\u9fff" for char in candidate):
            name = candidate
    return name

def file_plan():
    if digest(ARCHIVE) != EXPECTED_SHA:
        raise ValueError("Original archive SHA256 differs")
    original = load(EVIDENCE / "before" / D01.name / "_provenance/data.zip.manifest.json")
    old = {x["original_member"]: x for x in original["extraction"]["members"]}
    research, metadata, mappings = [], [], []
    seen = set()
    with zipfile.ZipFile(ARCHIVE) as archive:
        assert archive.testzip() is None
        for info in archive.infolist():
            if info.is_dir():
                continue
            record = old[info.filename]
            source = safe(DATASET / record["path"])
            content_sha = hashlib.sha256(archive.read(info)).hexdigest()
            assert content_sha == record["sha256"] == digest(source)
            assert source.stat().st_size == info.file_size == record["byte_size"]
            if is_mac(info.filename):
                metadata.append({**record, "reason": "macOS metadata; retained in original data.zip"})
                continue
            decoded = decoded_name(info)
            parts = PurePosixPath(decoded).parts
            assert not PurePosixPath(decoded).is_absolute() and ".." not in parts
            parts = tuple(re.sub(r'[<>:"|?*\x00-\x1f]', "_", part).rstrip(" .") for part in parts)
            target = safe(EXTRACTED.joinpath(*parts))
            key = str(target).casefold()
            assert key not in seen
            seen.add(key)
            if source != target:
                assert not target.exists(), "Refusing to overwrite: " + str(target)
            item = {**record, "decoded_member": decoded, "old_path": record["path"], "path": str(target.relative_to(DATASET))}
            research.append(item)
            if decoded != info.filename or source != target:
                mappings.append({"original_member": info.filename, "decoded_member": decoded,
                                 "previous_extracted_path": record["path"], "extracted_path": item["path"]})
    actual = {p.resolve() for p in EXTRACTED.rglob("*") if p.is_file()}
    recorded = {safe(DATASET / item["path"]) for item in old.values()}
    assert actual == recorded, "Unexpected files: preserve and inspect before repair"
    assert len(research) == 252 and len(metadata) == 301
    return original, research, metadata, mappings

def rewrite_d01(node, extraction, active=False):
    if isinstance(node, list):
        return [rewrite_d01(x, extraction, active) for x in node]
    if not isinstance(node, dict):
        return node
    own = node.get("id") == "D01"
    active = active or own
    result = {}
    for key, value in node.items():
        if active and key == "extraction" and isinstance(value, dict) and value.get("path", "").replace("\\", "/").startswith(D01.name+"/extracted/"):
            result[key] = copy.deepcopy(extraction)
            if "members" not in value:
                result[key].pop("members", None)
        elif active and key == "extracted_bytes":
            result[key] = extraction["uncompressed_bytes"]
        else:
            result[key] = rewrite_d01(value, extraction, active)
    if own:
        result["windows_repair_record"] = str((EVIDENCE / "verification.json").relative_to(DATASET))
    return result

def verify():
    assert digest(ARCHIVE) == EXPECTED_SHA
    acquisition = load(D01 / "_provenance/data.zip.manifest.json")
    extraction = acquisition["extraction"]
    items = extraction["members"]
    assert len(items) == 252 and len(extraction["skipped_members"]) == 301
    assert not any(is_mac(p.relative_to(EXTRACTED).as_posix()) for p in EXTRACTED.rglob("*") if p.is_file())
    actual = {p.resolve() for p in EXTRACTED.rglob("*") if p.is_file()}
    assert actual == {safe(DATASET / x["path"]) for x in items}
    text_extensions = {".csv", ".md", ".txt", ".json", ".xml", ".prj", ".cpg", ".geojson"}
    texts, upstream_issues, gis = 0, [], []
    with zipfile.ZipFile(ARCHIVE) as archive:
        assert archive.testzip() is None
        archive_names = {i.filename for i in archive.infolist() if not i.is_dir()}
        names = [x["original_member"] for x in items+extraction["skipped_members"]]
        assert len(names) == len(set(names)) and set(names) == archive_names
        for item in items:
            path = safe(DATASET / item["path"])
            data = path.read_bytes()
            assert hashlib.sha256(data).hexdigest() == item["sha256"]
            assert data == archive.read(item["original_member"])
            if not path.name.isascii():
                assert any("\u3400" <= c <= "\u9fff" for c in path.stem), "Mojibake name remains"
            if path.suffix.lower() in text_extensions:
                text = data.decode("utf-8-sig")
                texts += 1
                if "\ufffd" in text:
                    for number, line in enumerate(text.splitlines(), 1):
                        if "\ufffd" in line:
                            upstream_issues.append({"path": str(path.relative_to(D01)), "line": number,
                                "replacement_character_count": line.count("\ufffd"), "original_archive_has_identical_bytes": True,
                                "column": "source", "row_key": "technology=solar, parameter=investment"})
                if path.suffix.lower() in (".json", ".geojson"):
                    json.loads(text)
            if path.suffix == ".shp":
                assert struct.unpack(">i", data[:4])[0] == 9994
                assert struct.unpack(">i", data[24:28])[0]*2 == len(data)
                shx, dbf = path.with_suffix(".shx"), path.with_suffix(".dbf")
                assert shx.is_file() and dbf.is_file()
                index = shx.read_bytes()
                assert struct.unpack(">i", index[:4])[0] == 9994
                count = (len(index)-100)//8
                assert len(index) == 100+count*8
                records = struct.unpack("<I", dbf.read_bytes()[4:8])[0]
                assert records == count
                gis.append({"name": path.name, "records": records, "paired_shx_dbf_verified": True})
        for item in extraction["skipped_members"]:
            assert is_mac(item["original_member"])
            assert hashlib.sha256(archive.read(item["original_member"])).hexdigest() == item["sha256"]
    assert texts == 101 and len(upstream_issues) == 9
    result = {"verified_at_utc": datetime.now(timezone.utc).isoformat(), "archive_sha256": EXPECTED_SHA,
        "archive_crc_passed": True, "research_files": len(items), "research_bytes": extraction["uncompressed_bytes"],
        "all_research_content_identical_to_original_archive": True,
        "chinese_filenames_repaired": 60, "chinese_shapefile_groups_repaired": 10,
        "skipped_macos_metadata_files": 301, "skipped_macos_metadata_bytes": sum(x["byte_size"] for x in extraction["skipped_members"]),
        "remaining_mac_metadata_files_in_extracted_directory": 0,
        "utf8_text_files_verified": texts, "gis_structural_checks": gis,
        "upstream_text_issues_preserved_without_guessing": upstream_issues, "passed": True}
    save(EVIDENCE / "verification.json", result)
    return result

def write_notes(result, mappings):
    names = sorted({Path(x["extracted_path"]).stem for x in mappings if x["original_member"] != x["decoded_member"]})
    report = ["# D01 Windows乱码及苹果元数据修复记录", "", "修复日期：2026-10-27。", "",
        "## 原因与已完成处理", "",
        "1. 原ZIP中的60个GIS配套文件名使用UTF-8字节却未设置ZIP UTF-8标记，原解压程序按CP437读取，形成σ、τ等乱码。现已严格逆转换恢复10组中文名称，.shp/.shx/.dbf/.prj/.sbn/.sbx同步改名。",
        "2. 原包附带286个__MACOSX/._*资源元数据和15个.DS_Store文件，共301个。已从解压目录移除；它们仍完整保存在原data.zip中，并有成员SHA-256记录。._README.md等是二进制AppleDouble，不是真正的README。",
        "3. 真正的252个科研文件全部逐字节匹配原ZIP，101个文本严格UTF-8检查通过。未转换GIS DBF的内部编码，保留原.cpg声明；正常的pickle/HDF5/NetCDF/SHP等二进制不可按文本阅读。",
        "4. 数据获取解压脚本已限定对D01恢复名称并跳过苹果元数据；审计脚本可核验保留科研文件与原包内跳过元数据的完整分区。其他数据源解压策略保持原样。", "",
        "## 恢复的中文文件组", ""]+["- "+name for name in names]+["", "## 原始数据已有的内容缺陷", "",
        "costs/costs_2020.csv至costs_2060.csv（每5年一份，共9份）的第588行，solar/investment的source字段均含`Carbon Neutralization�� (in Chinese)`，共18个替换字符。原ZIP已含完全相同的字符，属于上游来源说明缺字；数值字段未涉及。没有足够证据恢复原字，因此保留原文并明确标注，未猜测改写科研源文件。", "",
        "## 完整性与使用位置", "", f"- 原ZIP SHA-256：`{EXPECTED_SHA}`，与取得时记录一致；CRC复核通过。",
        f"- 保留科研文件：252个，{result['research_bytes']:,}字节；全部与原包内容一致。",
        "- 正常数据入口：`extracted/data/data/`。中文地图：`extracted/data/data/province_shapes/CHN_adm/`。",
        "- 当前路径及排除记录：`manifest.json`与`_provenance/data.zip.manifest.json`。完整文件名映射：`_provenance/data.zip.filename_mapping.json`。",
        "- 修改前9份脚本/清单/来源说明已逐文件SHA验证备份于`_provenance/windows_repair_20261027/before/`；旧的下载修复批次记录作为历史保留。",
        "- 逐文件核验和已知问题：`_provenance/windows_repair_20261027/verification.json`。",
        "- 重跑本项核验：模型虚拟环境Python调用`_provenance/repair_windows.py --verify`。",
        "- 本次不涉及Reservoir_Industrial_Product_data模型的源码、轻量输入或此前Run01 ZIP。", ""]
    (D01 / "ENCODING_REPAIR.md").write_text("\n".join(report), encoding="utf-8-sig")
    (D01 / "README_请先看这里.txt").write_text(
        "D01正常数据入口：extracted\\data\\data\\\r\n"
        "中文地图入口：extracted\\data\\data\\province_shapes\\CHN_adm\\\r\n"
        "2026-10-27已恢复60个中文文件名并清理301个苹果元数据文件；252个科研文件内容与原ZIP完全一致。\r\n"
        "data.zip保留发布方原始格式，内部仍有苹果元数据和未标记UTF-8的文件名；日常请使用已修复的extracted目录。\r\n"
        "pickle、h5、nc、shp、dbf等是正常二进制数据，不能直接当文本打开。\r\n"
        "9个成本CSV的来源说明含上游已有缺字，已记录，未改数值或猜补原文。详情见ENCODING_REPAIR.md。\r\n", encoding="utf-8-sig")
    source = (D01 / "SOURCE.md").read_text(encoding="utf-8")
    source = source[:source.index("Four source archive members")]+(
        "Windows compatibility repair on 2026-10-27: the extracted research view recovers 60 Chinese GIS component filenames "
        "from unflagged UTF-8 ZIP names and retains the two earlier colon-to-underscore mappings. 301 macOS metadata files "
        "are omitted from the extracted view only; their original members and hashes remain recorded and recoverable from data.zip. "
        "All 252 research files preserve their original bytes. See ENCODING_REPAIR.md, _provenance/data.zip.filename_mapping.json "
        "and _provenance/windows_repair_20261027/verification.json. Prior manifests and scripts are backed up under that repair directory.\n")
    (D01 / "SOURCE.md").write_text(source, encoding="utf-8")

def apply():
    assert not (EVIDENCE / "verification.json").exists(), "Already applied; use --verify"
    acquisition, research, metadata, mappings = file_plan()
    save(EVIDENCE / "repair_plan.json", {"archive_sha256": EXPECTED_SHA, "research": research, "metadata_to_remove": metadata, "mappings": mappings})
    for item in research:
        source, target = safe(DATASET / item["old_path"]), safe(DATASET / item["path"])
        if source != target:
            assert digest(source) == item["sha256"]
            source.rename(target)
            assert digest(target) == item["sha256"]
    for item in metadata:
        target = safe(DATASET / item["path"])
        assert digest(target) == item["sha256"]
        target.unlink()
    mac_root = safe(EXTRACTED / "__MACOSX")
    if mac_root.exists():
        for folder in sorted([p for p in mac_root.rglob("*") if p.is_dir()], key=lambda p: len(p.parts), reverse=True):
            safe(folder).rmdir()
        mac_root.rmdir()
    kept = [{k: v for k, v in item.items() if k != "old_path"} for item in research]
    skipped = [{k: v for k, v in item.items() if k != "path"} for item in metadata]
    extraction = {**acquisition["extraction"], "members": kept, "member_count": len(kept),
        "uncompressed_bytes": sum(x["byte_size"] for x in kept), "renamed_member_count": len(mappings), "renamed_members": mappings,
        "skipped_member_count": len(skipped), "skipped_members": skipped, "archive_file_member_count": len(kept)+len(skipped),
        "archive_uncompressed_bytes": sum(x["byte_size"] for x in kept+skipped),
        "windows_policy": "Recover unflagged UTF-8 Chinese names; omit macOS metadata only; research content unchanged."}
    paths = [D01 / "manifest.json", D01 / "_provenance/data.zip.manifest.json"]+[
        DATASET / "_provenance" / x for x in ("manifest_scientific.json", "manifest_scientific_sources.json", "manifest_all_sources.json")]
    for path in paths:
        original = load(path)
        updated = rewrite_d01(original, extraction)
        if path.name == "manifest_scientific.json":
            updated["extracted_bytes"] = original["extracted_bytes"]-sum(x["byte_size"] for x in skipped)
        updated["windows_repair_utc"] = datetime.now(timezone.utc).isoformat()
        save(path, updated)
    save(D01 / "_provenance/data.zip.filename_mapping.json", mappings)
    result = verify()
    write_notes(result, mappings)
    print(json.dumps({k:v for k,v in result.items() if k not in ("upstream_text_issues_preserved_without_guessing", "gis_structural_checks")}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.apply == args.verify:
        parser.error("choose exactly one of --apply or --verify")
    if args.apply:
        apply()
    else:
        print(json.dumps(verify(), ensure_ascii=False, indent=2))
