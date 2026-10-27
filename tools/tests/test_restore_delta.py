"""Small local fixtures: no public Release downloads or research-data mutation."""
import copy
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

import zstandard

sys.dont_write_bytecode = True
TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
D01 = "dataset/D01_Nature_Energy_Industrial_Overcapacity/extracted/"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def entry(path, data):
    return {"path": path, "bytes": len(data), "sha256": digest(data)}


class DeltaTests(unittest.TestCase):
    def setUp(self):
        module_path = TOOLS / "restore_delta.py"
        self.assertTrue(module_path.exists(), "restore_delta.py feature is not implemented")
        spec = importlib.util.spec_from_file_location("restore_delta", module_path)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.tmp = tempfile.TemporaryDirectory(prefix="delta-fixture-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.root = self.home / "destination"
        self.root.mkdir()
        self.meta = self.home / "metadata"
        self.meta.mkdir()
        self.old_name = "dataset/D01_Nature_Energy_Industrial_Overcapacity/_provenance/check.json"
        self.add_name = "dataset/D02_test/new.nc"
        self.del_name = D01 + "data/__MACOSX/data/._x"
        self.old = {self.old_name: b"old record", self.del_name: b"apple metadata", "dataset/D24_test/keep.zip": b"keep"}
        self.payload = {self.old_name: b"new record", self.add_name: b"new payload"}
        for name, data in self.old.items():
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        self.base = {"schema_version": 1, "files": [entry(n, d) for n, d in self.old.items()]}
        self.changes = {"schema_version": 1, "base_snapshot_tag": "snapshot-20261027", "added": [entry(self.add_name, self.payload[self.add_name])], "changed": [{**entry(self.old_name, self.payload[self.old_name]), "old_bytes": len(self.old[self.old_name]), "old_sha256": digest(self.old[self.old_name])}], "deleted": [entry(self.del_name, self.old[self.del_name])]}
        self.write_manifests()

    def write_json(self, name, value):
        path = self.meta / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf8")
        return path

    def write_manifests(self, members=None, *, trailing=b"", truncate=0):
        self.base_path = self.write_json("SOURCE_FILES_SHA256.json", self.base)
        self.base_sha = digest(self.base_path.read_bytes())
        self.changes["base_source_manifest_sha256"] = self.base_sha
        self.source = {"schema_version": 1, "path_basis": "workspace-relative POSIX paths", "files": [entry(n, d) for n, d in self.payload.items()], "source_file_count": len(self.payload), "source_bytes": sum(map(len, self.payload.values()))}
        self.source_path = self.write_json("UPDATE_FILES_SHA256.json", self.source)
        self.changes_path = self.write_json("UPDATE_CHANGES.json", self.changes)
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for name, data, kind in members if members is not None else [(n, d, tarfile.REGTYPE) for n, d in self.payload.items()]:
                info = tarfile.TarInfo(name)
                info.type = kind
                info.size = len(data) if kind == tarfile.REGTYPE else 0
                info.linkname = "outside" if kind == tarfile.SYMTYPE else ""
                tar.addfile(info, io.BytesIO(data) if kind == tarfile.REGTYPE else None)
        compressed = zstandard.ZstdCompressor(write_checksum=True).compress(stream.getvalue())
        compressed = compressed[:-truncate] if truncate else compressed
        compressed += trailing
        # Deliberately split inside the zstd stream, independent of tar members.
        pivot = max(1, len(compressed) // 2)
        self.parts = []
        parts_meta = []
        for i, data in enumerate((compressed[:pivot], compressed[pivot:]), 1):
            p = self.meta / f"update.tar.zst.part{i:03d}"
            p.write_bytes(data)
            self.parts.append(p)
            parts_meta.append({"name": p.name, "bytes": len(data), "sha256": digest(data)})
        self.archive = {"archive_format": "tar+zstd", "parts": parts_meta, "compressed_bytes": len(compressed), "source_manifest": self.source_path.name, "source_manifest_sha256": digest(self.source_path.read_bytes()), "changes_manifest": self.changes_path.name, "changes_manifest_sha256": digest(self.changes_path.read_bytes()), "source_file_count": self.source["source_file_count"], "source_bytes": self.source["source_bytes"], "base_snapshot_tag": "snapshot-20261027", "base_source_manifest_sha256": self.base_sha}
        self.archive_path = self.write_json("update_archive_manifest.json", self.archive)

    def plan(self, *, fixed_base=False):
        kwargs = {} if fixed_base else {"expected_base_sha256": self.base_sha}
        return self.mod.load_update(self.archive_path, self.source_path, self.changes_path, self.base_path, **kwargs)

    def restore(self, *, dry_run=False):
        return self.mod.restore_delta(self.parts, self.plan(), self.root, self.home / "staging", dry_run=dry_run)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def test_applies_added_changed_deleted_and_is_idempotent(self):
        result = self.restore()
        self.assertEqual(result["written"], 2)
        self.assertEqual(result["deleted"], 1)
        self.assertFalse((self.root / self.del_name).exists())
        for n, d in self.payload.items():
            self.assertEqual((self.root / n).read_bytes(), d)
        self.assertEqual(self.restore()["written"], 0)

    def test_dry_run_verifies_payload_without_destination_changes(self):
        before = self.snapshot()
        result = self.restore(dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertEqual(self.snapshot(), before)

    def test_unknown_existing_added_file_refuses_all_changes(self):
        p = self.root / self.add_name
        p.parent.mkdir(parents=True)
        p.write_bytes(b"user work")
        before = self.snapshot()
        with self.assertRaises(self.mod.RestoreError):
            self.restore()
        self.assertEqual(self.snapshot(), before)

    def test_user_modified_changed_or_deleted_file_is_preserved(self):
        for name in (self.old_name, self.del_name):
            with self.subTest(name=name):
                p = self.root / name
                original = p.read_bytes()
                p.write_bytes(b"user edit")
                before = self.snapshot()
                with self.assertRaises(self.mod.RestoreError):
                    self.restore()
                self.assertEqual(self.snapshot(), before)
                p.write_bytes(original)

    def test_missing_changed_file_is_not_treated_as_added(self):
        (self.root / self.old_name).unlink()
        with self.assertRaises(self.mod.RestoreError):
            self.restore()

    def test_base_digest_is_pinned_by_default(self):
        with self.assertRaises(self.mod.RestoreError):
            self.plan(fixed_base=True)

    def test_source_and_changes_manifest_digest_are_checked(self):
        for path in (self.source_path, self.changes_path):
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            with self.assertRaises(self.mod.RestoreError):
                self.plan()
            path.write_bytes(original)

    def test_forged_old_sha_and_outside_deletion_are_rejected(self):
        for mode in ("oldsha", "outside"):
            old_changes = copy.deepcopy(self.changes)
            if mode == "oldsha":
                self.changes["changed"][0]["old_sha256"] = "0" * 64
            else:
                self.changes["deleted"] = [entry("dataset/D24_test/keep.zip", b"keep")]
            self.write_manifests()
            with self.assertRaises(self.mod.RestoreError):
                self.plan()
            self.changes = old_changes

    def test_mojibake_gis_delete_requires_identical_corrected_payload(self):
        correct = D01 + "data/province_shapes/CHN_adm/中国地州界.shp"
        old = correct.encode("utf8").decode("cp437")
        data = b"shape bytes"
        self.base["files"].append(entry(old, data))
        self.old[old] = data
        p = self.root / old
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        self.changes["deleted"].append(entry(old, data))
        self.write_manifests()
        with self.assertRaises(self.mod.RestoreError):
            self.plan()
        self.payload[correct] = data
        self.changes["added"].append(entry(correct, data))
        self.write_manifests()
        self.restore()
        self.assertFalse(p.exists())
        self.assertEqual((self.root / correct).read_bytes(), data)

    def test_bad_payload_or_missing_late_member_never_mutates_destination(self):
        cases = [[(self.old_name, self.payload[self.old_name], tarfile.REGTYPE)], [(self.old_name, b"BAD", tarfile.REGTYPE), (self.add_name, self.payload[self.add_name], tarfile.REGTYPE)]]
        for members in cases:
            self.write_manifests(members)
            before = self.snapshot()
            with self.assertRaises((self.mod.RestoreError, zstandard.ZstdError, tarfile.TarError)):
                self.restore()
            self.assertEqual(self.snapshot(), before)

    def test_truncated_frame_and_trailing_garbage_are_rejected_before_apply(self):
        for options in ({"truncate": 5}, {"trailing": b"not another zstd frame"}):
            self.write_manifests(**options)
            before = self.snapshot()
            with self.assertRaises((self.mod.RestoreError, zstandard.ZstdError, tarfile.TarError)):
                self.restore()
            self.assertEqual(self.snapshot(), before)

    def test_duplicate_unexpected_and_symlink_tar_members_are_rejected(self):
        first = (self.old_name, self.payload[self.old_name], tarfile.REGTYPE)
        for extra in (first, ("dataset/unexpected", b"extra", tarfile.REGTYPE), (self.add_name, b"", tarfile.SYMTYPE), ("../escape", b"bad", tarfile.REGTYPE)):
            self.write_manifests([first, extra])
            before = self.snapshot()
            with self.assertRaises(self.mod.RestoreError):
                self.restore()
            self.assertEqual(self.snapshot(), before)

    def test_part_corruption_and_oversize_are_rejected(self):
        self.parts[1].write_bytes(self.parts[1].read_bytes() + b"bad")
        before = self.snapshot()
        with self.assertRaises(self.mod.RestoreError):
            self.restore()
        self.assertEqual(self.snapshot(), before)
        self.archive["parts"][0]["bytes"] = 350_000_001
        self.write_json("update_archive_manifest.json", self.archive)
        with self.assertRaises(self.mod.RestoreError):
            self.plan()

    def test_payload_changes_mismatch_and_case_alias_are_rejected(self):
        self.changes["added"][0]["sha256"] = "0" * 64
        self.write_manifests()
        with self.assertRaises(self.mod.RestoreError):
            self.plan()
        self.changes["added"][0]["sha256"] = digest(self.payload[self.add_name])
        alias = self.add_name.upper()
        self.payload[alias] = b"alias"
        self.changes["added"].append(entry(alias, b"alias"))
        self.write_manifests()
        with self.assertRaises(self.mod.RestoreError):
            self.plan()

    def test_archive_manifest_digest_is_checked_against_trusted_git_copy(self):
        trusted = self.home / "trusted" / self.archive_path.name
        trusted.parent.mkdir()
        trusted.write_bytes(self.archive_path.read_bytes())
        self.archive_path.write_bytes(self.archive_path.read_bytes() + b" ")
        stderr = io.StringIO()
        argv = ["restore_delta.py", "--destination", str(self.root), "--cache-dir", str(self.meta), "--archive-manifest", str(trusted), "--base-source-manifest", str(self.base_path), "--offline", "--dry-run"]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stderr(stderr):
            self.assertEqual(self.mod.main(), 1)
        self.assertIn("Manifest SHA256 mismatch: update_archive_manifest.json", stderr.getvalue())

    def test_online_cache_cannot_overwrite_trusted_manifest(self):
        argv = ["restore_delta.py", "--destination", str(self.root), "--cache-dir", str(self.meta), "--archive-manifest", str(self.archive_path), "--base-source-manifest", str(self.base_path)]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(self.mod.snapshot, "read_json_asset", return_value={}) as downloader, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.mod.main(), 1)
        self.assertEqual(downloader.call_count, 0, "Do not download over a trusted manifest inside cache")

    def test_cli_defaults_to_tracked_update_subdirectory(self):
        argv = ["restore_delta.py", "--destination", str(self.root), "--cache-dir", str(self.home / "cache"), "--offline"]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(self.mod.snapshot, "sha256_file", return_value="0" * 64), mock.patch.object(self.mod, "read_json", side_effect=self.mod.RestoreError("stop after default path")) as reader, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.mod.main(), 1)
        self.assertEqual(reader.call_args.args[0], TOOLS.parent / "updates/local-data-20261027/update_archive_manifest.json")

    def test_apply_failure_keeps_deletions_for_last_and_can_resume(self):
        original_replace = self.mod.os.replace
        calls = 0

        def fail_second(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated disk error")
            return original_replace(source, target)

        with mock.patch.object(self.mod.os, "replace", side_effect=fail_second):
            with self.assertRaises(OSError):
                self.restore()
        self.assertEqual((self.root / self.del_name).read_bytes(), self.old[self.del_name])
        self.assertEqual(self.restore()["deleted"], 1)

    @unittest.skipUnless(os.name == "nt", "Windows junction integration")
    def test_cli_rejects_junction_in_destination_ancestor_before_resolve(self):
        real = self.home / "real"
        real.mkdir()
        link = self.home / "junction"
        created = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(real)], capture_output=True)
        self.assertEqual(created.returncode, 0)
        stderr = io.StringIO()
        argv = ["restore_delta.py", "--destination", str(link / "nested"), "--cache-dir", str(self.meta), "--archive-manifest", str(self.archive_path), "--base-source-manifest", str(self.base_path), "--offline"]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stderr(stderr):
            self.assertEqual(self.mod.main(), 1)
        self.assertIn("reparse", stderr.getvalue().lower())


if __name__ == "__main__":
    unittest.main()
