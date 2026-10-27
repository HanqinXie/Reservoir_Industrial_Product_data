"""Exercise actual D01 extraction/audit offline, with scoped temporary files."""
import ast
import contextlib
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import pathlib
import re
import stat
import subprocess
import sys
import tempfile
import urllib.parse
import zipfile

from repair_windows import D01, DATASET, EVIDENCE, EXPECTED_SHA, digest, load, save, verify

PROJECT = DATASET.parent
MODEL = PROJECT / "code/Reservoir_Industrial_Product_data/models/reservoir_inventory"
TESTS = D01 / "_provenance/test_windows_extraction.py"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def execute(name, argv, cwd, expected=0, extra_env=None):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(extra_env or {})
    started = datetime.now(timezone.utc).isoformat()
    with (EVIDENCE / (name+".log")).open("wb") as stream:
        result = subprocess.run(argv, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT)
    status = {"argv": list(map(str, argv)), "cwd": str(cwd), "start_utc": started,
              "end_utc": datetime.now(timezone.utc).isoformat(), "exit_code": result.returncode,
              "expected_exit_code": expected, "passed": result.returncode == expected}
    save(EVIDENCE / (name+".status.json"), status)
    assert status["passed"], (EVIDENCE / (name+".log")).read_text(encoding="utf-8")
    return status

def main():
    before = EVIDENCE / "before/_provenance/download_scientific.py"
    red = execute("regression_before", [sys.executable, str(TESTS)], DATASET,
                  expected=1, extra_env={"D01_EXTRACTOR_SOURCE": str(before)})
    assert "FAILED (failures=2)" in (EVIDENCE / "regression_before.log").read_text(encoding="utf-8")
    green = execute("regression_after", [sys.executable, str(TESTS)], DATASET)
    extraction_tree = ast.parse((DATASET / "_provenance/download_scientific.py").read_text(encoding="utf-8-sig"))
    extraction_functions = [x for x in extraction_tree.body if isinstance(x, ast.FunctionDef) and x.name in {"extract_zip", "_zip_utf8_name", "_is_macos_metadata"}]
    audit_tree = ast.parse((DATASET / "_provenance/audit_scientific.py").read_text(encoding="utf-8-sig"))
    audit_functions = [x for x in audit_tree.body if isinstance(x, ast.FunctionDef)]
    coverage = next(ast.literal_eval(x.value) for x in audit_tree.body if isinstance(x, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "COVERAGE" for t in x.targets))
    tasks = [x for x in load(DATASET / "_provenance/scientific_tasks_final.json") if x["id"] == "D01"]
    assert len(tasks) == 1
    # The target is explicitly resolved inside D01 before TemporaryDirectory
    # can perform its recursive cleanup. Hard links are never written to.
    temporary = tempfile.TemporaryDirectory(prefix="workflow_check_", dir=EVIDENCE)
    temporary_root = Path(temporary.name).resolve()
    assert temporary_root.is_relative_to(EVIDENCE.resolve())
    try:
        folder = temporary_root / D01.name
        folder.mkdir()
        archive = folder / "data.zip"
        archive.hardlink_to(D01 / "data.zip")
        env = {"pathlib": pathlib, "hashlib": hashlib, "stat": stat, "zipfile": zipfile, "re": re, "ROOT": temporary_root}
        exec(compile(ast.Module(body=extraction_functions, type_ignores=[]), "download_scientific.py", "exec"), env)
        fresh = env["extract_zip"](archive, folder / "extracted/data")
        assert fresh["member_count"] == 252 and fresh["skipped_member_count"] == 301
        assert fresh["renamed_member_count"] == 62
        current = load(D01 / "_provenance/data.zip.manifest.json")
        current_map = {x["original_member"]: (x["path"], x["sha256"]) for x in current["extraction"]["members"]}
        fresh_map = {x["original_member"]: (x["path"], x["sha256"]) for x in fresh["members"]}
        assert current_map == fresh_map, "Fresh extraction differs from repaired directory"
        record = copy.deepcopy(current)
        record["extraction"] = fresh
        save(folder / "_provenance/data.zip.manifest.json", record)
        (temporary_root / "_provenance").mkdir()
        audit_env = {"hashlib": hashlib, "json": json, "pathlib": pathlib, "sys": sys,
            "urllib": urllib, "zipfile": zipfile, "datetime": datetime, "timezone": timezone,
            "ROOT": temporary_root, "TASKS": tasks, "COVERAGE": coverage}
        exec(compile(ast.Module(body=audit_functions, type_ignores=[]), "audit_scientific.py", "exec"), audit_env)
        with (EVIDENCE / "original_audit_workflow.log").open("w", encoding="utf-8") as stream:
            with contextlib.redirect_stdout(stream):
                audit_env["main"]()
        audit = load(temporary_root / "_provenance/scientific_verification.json")
        assert audit["status"] == "complete" and len(audit["checks"]) == 1 and not audit["checks"][0]["issues"]
        audit["scope_note"] = "D01 only; actual extractor and original audit functions run in isolated temporary dataset. No other dataset was re-audited or modified."
        save(EVIDENCE / "original_audit_workflow.json", audit)
    finally:
        assert temporary_root.is_relative_to(EVIDENCE.resolve())
        temporary.cleanup()
    compatibility = execute("model_19_checks", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], MODEL)
    assert "Ran 19 tests" in (EVIDENCE / "model_19_checks.log").read_text(encoding="utf-8")
    final = verify()
    receipt = load(MODEL / "Reservoir_Inventory_Run01.zip.receipt.json")
    assert digest(MODEL / "Reservoir_Inventory_Run01.zip") == receipt["sha256"]
    result = {"verified_at_utc": datetime.now(timezone.utc).isoformat(), "passed": True,
        "regression_before": red, "regression_after": green,
        "regression_checks": 5, "original_defects_reproduced": 2,
        "fresh_actual_archive_extraction_files": 252, "fresh_skipped_metadata_files": 301,
        "fresh_extraction_matches_repaired_directory": True,
        "original_audit_workflow_for_D01_passed": True,
        "model_compatibility": compatibility, "model_checks_passed": 19,
        "original_run01_zip_unchanged": True, "archive_sha256": EXPECTED_SHA}
    save(EVIDENCE / "workflow_verification.json", result)
    report = D01 / "ENCODING_REPAIR.md"
    text = report.read_text(encoding="utf-8-sig")
    section = "\n## 修复后原流程复核\n\n- 离线回归5项通过；用备份旧脚本重现2项原缺陷，当前脚本均通过。\n- 对原始data.zip在限定临时目录实际重新解压：252个科研文件、301个明确跳过的苹果元数据，62项映射（60个中文名+2个冒号映射）；新解压科研文件路径及SHA-256与修复目录完全一致。\n- 原audit_scientific审计函数对D01的隔离复核通过，原包文件由252个保留成员与301个有哈希的元数据成员完整分区；临时解压目录已清理。\n- 模型原有19项检查再次全部通过；此前Run01 ZIP的SHA-256保持一致。\n- 完整日志与状态见`_provenance/windows_repair_20261027/workflow_verification.json`及同目录日志。\n"
    if "## 修复后原流程复核" not in text:
        report.write_text(text+section, encoding="utf-8-sig")
    print(json.dumps({k:v for k,v in result.items() if k not in ("regression_before", "regression_after", "model_compatibility")}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
