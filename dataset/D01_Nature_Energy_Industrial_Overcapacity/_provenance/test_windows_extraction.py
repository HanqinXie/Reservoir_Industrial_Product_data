"""Offline regression checks against the real extraction function."""
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import pathlib
import re
import stat
import struct
import sys
import tempfile
import unittest
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DATASET = Path(__file__).resolve().parents[2]

def load_extractor(root):
    # Isolate the real standard-library-only extraction function from the
    # downloader's unused requests dependency; no network/download code runs.
    source = Path(os.environ.get("D01_EXTRACTOR_SOURCE", str(DATASET / "_provenance/download_scientific.py")))
    tree = ast.parse(source.read_text(encoding="utf-8-sig"))
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {"extract_zip", "_zip_utf8_name", "_is_macos_metadata"}]
    env = {"pathlib": pathlib, "hashlib": hashlib, "stat": stat, "zipfile": zipfile, "re": re, "ROOT": root}
    exec(compile(ast.Module(body=functions, type_ignores=[]), "download_scientific.py", "exec"), env)
    return env["extract_zip"]

def zip_with_missing_utf8_flag(path, entries):
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)
    body = bytearray(path.read_bytes())
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            pos = member.header_offset + 6
            struct.pack_into("<H", body, pos, struct.unpack_from("<H", body, pos)[0] & ~0x800)
        pos = archive.start_dir
        for member in archive.infolist():
            assert body[pos:pos+4] == b"PK\x01\x02"
            struct.pack_into("<H", body, pos+8, struct.unpack_from("<H", body, pos+8)[0] & ~0x800)
            n, x, c = struct.unpack_from("<HHH", body, pos+28)
            pos += 46+n+x+c
    path.write_bytes(body)

class WindowsExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="d01-offline-check-")
        self.root = Path(self.temp.name).resolve()
        self.folder = self.root / "D01_fixture"
        self.folder.mkdir()
        self.archive = self.folder / "data.zip"
        self.dest = self.folder / "extracted/data"
        self.extract = load_extractor(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_recovers_all_chinese_shapefile_component_names_without_changing_bytes(self):
        entries = [("data/国界线"+ext, ("science"+ext).encode()) for ext in (".shp", ".shx", ".dbf", ".prj", ".sbn", ".sbx")]
        zip_with_missing_utf8_flag(self.archive, entries)
        record = self.extract(self.archive, self.dest)
        self.assertEqual({p.name for p in (self.dest / "data").iterdir()}, {"国界线"+ext for ext in (".shp", ".shx", ".dbf", ".prj", ".sbn", ".sbx")})
        for name, data in entries:
            self.assertEqual((self.dest / name).read_bytes(), data)
        self.assertEqual(record["member_count"], 6)

    def test_skips_only_mac_metadata_and_records_its_archive_hashes(self):
        entries = [("data/input.csv", b"value\n1\n"), ("__MACOSX/data/._input.csv", b"metadata"), ("data/.DS_Store", b"finder"), ("data/.science", b"keep")]
        zip_with_missing_utf8_flag(self.archive, entries)
        record = self.extract(self.archive, self.dest)
        self.assertFalse((self.dest / "__MACOSX").exists())
        self.assertFalse((self.dest / "data/.DS_Store").exists())
        self.assertEqual((self.dest / "data/.science").read_bytes(), b"keep")
        self.assertEqual(record["member_count"], 2)
        self.assertEqual(record["skipped_member_count"], 2)
        self.assertEqual({x["sha256"] for x in record["skipped_members"]}, {hashlib.sha256(b"metadata").hexdigest(), hashlib.sha256(b"finder").hexdigest()})

    def test_other_sources_retain_the_original_extraction_policy(self):
        folder = self.root / "D05_fixture"
        folder.mkdir()
        archive = folder / "data.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("__MACOSX/._file", b"unchanged")
        dest = folder / "extracted/data"
        self.assertEqual(self.extract(archive, dest)["member_count"], 1)
        self.assertEqual((dest / "__MACOSX/._file").read_bytes(), b"unchanged")

    def test_path_traversal_still_rejected(self):
        with zipfile.ZipFile(self.archive, "w") as z:
            z.writestr("../escape.csv", b"bad")
        with self.assertRaises(ValueError):
            self.extract(self.archive, self.dest)
        self.assertFalse((self.root / "escape.csv").exists())

    def test_existing_windows_invalid_colon_mapping_is_preserved(self):
        with zipfile.ZipFile(self.archive, "w") as z:
            z.writestr("data/DH_city:town_2020.csv", b"original")
        self.extract(self.archive, self.dest)
        self.assertEqual((self.dest / "data/DH_city_town_2020.csv").read_bytes(), b"original")

if __name__ == "__main__":
    unittest.main(verbosity=2)
