"""Package only the lightweight model closure, then extract and verify it."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT.parents[2]
DEST = CODE / "_delivery_check" / "Reservoir_Inventory_Run01"
ARCHIVE = ROOT / "Reservoir_Inventory_Run01.zip"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
EXCLUDE = {".venv", ".git", "__pycache__", ".cache", ".pytest_cache", ".mypy_cache", ".ruff_cache"}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    if ARCHIVE.exists() or DEST.exists():
        raise RuntimeError("Refusing to overwrite an existing delivery archive/extraction")
    require = ["RUN_REPORT.md", "pyproject.toml", "README.md"]
    files = [ROOT / name for name in require]
    for folder in ("src", "tests", "configs", "docs", "scripts", "data", "examples", "logs"):
        files += [p for p in (ROOT / folder).rglob("*") if p.is_file() and not any(x in EXCLUDE or x.endswith(".egg-info") for x in p.relative_to(ROOT).parts) and p.suffix not in (".pyc", ".pyo")]
    for folder in ("toy", "demo", "sweep"):
        files += [p for p in (ROOT / "outputs" / folder).rglob("*") if p.is_file()]
    files = sorted(set(files))
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, encoding="utf-8").strip()
    if subprocess.run(["git", "diff", "--exit-code", "HEAD"], cwd=ROOT, capture_output=True).returncode:
        raise RuntimeError("Tracked model files changed")
    manifest = {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": head, "model_tracked_files_changed": False,
        "archive_root": "models/reservoir_inventory contents (no enclosing directory)",
        "excluded": [".venv", ".git", "caches", "egg-info", "complete raw archives", "third-party dependencies"],
        "manifest_self_hash_omitted_to_avoid_self_reference": True,
        "files": [{"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)} for p in files]}
    manifest_path = ROOT / "PACKAGE_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for p in files+[manifest_path]:
            archive.write(p, p.relative_to(ROOT).as_posix())
    if ARCHIVE.stat().st_size > 400000000:
        raise RuntimeError("Archive exceeds 400,000,000 bytes")
    # Resolve before extraction and reject absolute/traversal member names.
    destination = DEST.resolve()
    if not destination.is_relative_to(CODE.resolve()):
        raise RuntimeError("Extraction target escaped code directory")
    with zipfile.ZipFile(ARCHIVE) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError("CRC failed: " + bad)
        expected = {p.relative_to(ROOT).as_posix() for p in files+[manifest_path]}
        if set(archive.namelist()) != expected:
            raise RuntimeError("Archive membership mismatch")
        for name in archive.namelist():
            target = (destination / name).resolve()
            if not target.is_relative_to(destination):
                raise RuntimeError("Unsafe member: " + name)
        archive.extractall(destination)
    count = Counter()
    for p in files+[manifest_path]:
        rel = p.relative_to(ROOT)
        extracted = destination / rel
        if sha(p) != sha(extracted) or p.stat().st_size != extracted.stat().st_size:
            raise RuntimeError("Extracted member mismatch: " + str(rel))
        count[p.suffix] += 1
        if p.suffix == ".json":
            json.loads(extracted.read_text(encoding="utf-8-sig"), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
        elif p.suffix == ".csv":
            pd.read_csv(extracted, float_precision="round_trip")
        elif p.suffix == ".png":
            with Image.open(extracted) as picture:
                picture.verify()
            with Image.open(extracted) as picture:
                picture.load()
        elif p.suffix in (".py", ".md", ".toml", ".txt", ".log"):
            extracted.read_text(encoding="utf-8-sig")
            if p.suffix == ".py":
                compile(extracted.read_text(encoding="utf-8-sig"), str(rel), "exec")
    required_roots = {"src", "tests", "configs", "docs", "scripts", "data", "examples", "logs", "outputs"}
    if not all((destination / folder).is_dir() for folder in required_roots):
        raise RuntimeError("Missing closure folder")
    receipt = {"archive": str(ARCHIVE), "git_commit": head, "archive_bytes": ARCHIVE.stat().st_size,
        "under_400000000_bytes": True, "sha256": sha(ARCHIVE), "member_count": len(files)+1,
        "uncompressed_bytes": sum(p.stat().st_size for p in files+[manifest_path]),
        "crc_passed": True, "actual_extraction_directory": str(destination),
        "all_members_size_and_sha256_match": True, "all_csv_json_png_and_text_readable": True,
        "all_python_sources_compile": True, "extensions": dict(count),
        "verified_at_utc": datetime.now(timezone.utc).isoformat(), "passed": True}
    ARCHIVE.with_suffix(".zip.receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    ARCHIVE.with_suffix(".zip.sha256").write_text(receipt["sha256"]+"  "+ARCHIVE.name+"\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
