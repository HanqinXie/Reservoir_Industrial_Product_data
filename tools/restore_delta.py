#!/usr/bin/env python3
"""Verify and apply the incremental Release after snapshot-20261027 (Python 3.10+)."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tarfile
import tempfile
import unicodedata
from urllib.error import URLError
from http.client import HTTPException

import zstandard
import restore_snapshot as snapshot

RestoreError = snapshot.RestoreError
BASE_TAG = "snapshot-20261027"
BASE_SOURCE_SHA256 = "e28bf34756a0785712ddbe432c20e9c374b482eaa23fbf012b1170a5c9a1b7fe"
BASE_URL = "https://github.com/HanqinXie/Reservoir_Industrial_Product_data/releases/download/local-update-20261027-run01"
MAX_PART_BYTES = 350_000_000
D01_EXTRACTED = "dataset/D01_Nature_Energy_Industrial_Overcapacity/extracted/"
CHUNK = snapshot.CHUNK


def json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RestoreError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path, expected_sha256: str | None = None) -> dict:
    if path.stat().st_size > snapshot.MANIFEST_LIMIT:
        raise RestoreError(f"Manifest too large: {path.name}")
    data = path.read_bytes()
    if expected_sha256 is not None and hashlib.sha256(data).hexdigest() != expected_sha256:
        raise RestoreError(f"Manifest SHA256 mismatch: {path.name}")
    value = json.loads(data.decode("utf-8-sig"), object_pairs_hook=json_object)
    if not isinstance(value, dict):
        raise RestoreError(f"Manifest must be an object: {path.name}")
    return value


def fingerprint(entry: dict, prefix: str = "") -> tuple[int, str]:
    size, digest = entry[prefix + "bytes"], entry[prefix + "sha256"]
    if type(size) is not int or size < 0 or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise RestoreError("Invalid file size or SHA256")
    return size, digest


def alias(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def file_map(entries: list[dict]) -> dict[str, dict]:
    if not isinstance(entries, list):
        raise RestoreError("Missing file/operation list")
    result, aliases = {}, set()
    for entry in entries:
        name = snapshot.safe_path(entry["path"])
        fingerprint(entry)
        if alias(name) in aliases:
            raise RestoreError(f"Duplicate or aliased path: {name}")
        aliases.add(alias(name))
        result[name] = entry
    return result


def allowed_deletion(name: str, entry: dict, payload: dict[str, dict]) -> bool:
    if not name.startswith(D01_EXTRACTED):
        return False
    path = PurePosixPath(name)
    if "__MACOSX" in path.parts or path.name.startswith("._") or path.name == ".DS_Store":
        return True
    if path.suffix.lower() not in {".shp", ".shx", ".dbf", ".prj", ".cpg", ".sbn", ".sbx", ".xml"}:
        return False
    # The old snapshot decoded UTF-8 ZIP names as CP437. A corrected copy must
    # be present with identical bytes before the old GIS filename can be removed.
    try:
        corrected = name.encode("cp437", "strict").decode("utf-8", "strict")
    except UnicodeError:
        return False
    return corrected != name and corrected in payload and fingerprint(payload[corrected]) == fingerprint(entry)


def load_update(archive_path: Path, source_path: Path, changes_path: Path, base_path: Path, *, expected_base_sha256: str = BASE_SOURCE_SHA256) -> dict:
    """Load authenticated metadata. The base override is for Python fixture tests only."""
    archive = read_json(archive_path)
    source = read_json(source_path, archive["source_manifest_sha256"])
    changes = read_json(changes_path, archive["changes_manifest_sha256"])
    base = read_json(base_path, expected_base_sha256)
    if archive.get("archive_format") != "tar+zstd":
        raise RestoreError("Unsupported archive format")
    if source.get("schema_version") != 1 or changes.get("schema_version") != 1 or base.get("schema_version") != 1:
        raise RestoreError("Unsupported manifest schema")
    if source.get("path_basis") != "workspace-relative POSIX paths":
        raise RestoreError("Unexpected payload path basis")
    for value in (archive, changes):
        if value.get("base_snapshot_tag") != BASE_TAG or value.get("base_source_manifest_sha256") != expected_base_sha256:
            raise RestoreError("Wrong base snapshot or base source manifest digest")
    if snapshot.asset_name(archive["source_manifest"]) != source_path.name or snapshot.asset_name(archive["changes_manifest"]) != changes_path.name:
        raise RestoreError("Manifest filenames differ from archive manifest")
    parts = archive.get("parts")
    if not isinstance(parts, list) or not parts:
        raise RestoreError("Missing archive parts")
    names = set()
    for part in parts:
        name = snapshot.asset_name(part["name"])
        size, _ = fingerprint(part)
        if not 0 < size <= MAX_PART_BYTES or alias(name) in names:
            raise RestoreError(f"Invalid or duplicate part: {name}")
        names.add(alias(name))
    if archive.get("compressed_bytes") != sum(p["bytes"] for p in parts):
        raise RestoreError("Compressed byte count mismatch")
    payload = file_map(source["files"])
    base_files = file_map(base["files"])
    base_aliases = {alias(n) for n in base_files}
    operations = {op: file_map(changes.get(op)) for op in ("added", "changed", "deleted")}
    op_aliases = set()
    for op, entries in operations.items():
        for name, entry in entries.items():
            if alias(name) in op_aliases:
                raise RestoreError(f"Path occurs in multiple operations: {name}")
            op_aliases.add(alias(name))
            if op == "added":
                if alias(name) in base_aliases:
                    raise RestoreError(f"Added path already belongs to base: {name}")
            elif name not in base_files:
                raise RestoreError(f"Changed/deleted path is absent from base manifest: {name}")
            elif fingerprint(entry, "old_" if op == "changed" else "") != fingerprint(base_files[name]):
                raise RestoreError(f"Old file fingerprint differs from pinned base: {name}")
            if op == "deleted" and not allowed_deletion(name, entry, payload):
                raise RestoreError(f"Deletion is outside the D01 allowlist: {name}")
    required_payload = operations["added"] | operations["changed"]
    if payload.keys() != required_payload.keys() or any(fingerprint(entry) != fingerprint(required_payload[name]) for name, entry in payload.items()):
        raise RestoreError("Payload must exactly equal added + changed files")
    source_count, source_bytes = len(payload), sum(p["bytes"] for p in payload.values())
    for value in (archive, source):
        if value.get("source_file_count") != source_count or value.get("source_bytes") != source_bytes:
            raise RestoreError("Payload count/bytes mismatch")
    final_paths = (base_files.keys() - operations["deleted"].keys()) | payload.keys()
    folded = {alias(n) for n in final_paths}
    if len(folded) != len(final_paths):
        raise RestoreError("Final file tree has case/Unicode aliases")
    for name in final_paths:
        if any(alias(str(p)) in folded for p in PurePosixPath(name).parents if str(p) != "."):
            raise RestoreError(f"File/directory path collision: {name}")
    return {"archive": archive, "source": source, "changes": changes, "payload": payload, "operations": operations, "archive_sha256": snapshot.sha256_file(archive_path), "base_source_manifest_sha256": expected_base_sha256}


def guarded_path(root: Path, name: str) -> Path:
    target = snapshot.target_path(root, name)
    current = target
    while True:
        if os.path.lexists(current):
            metadata = current.lstat()
            if current.is_symlink() or getattr(metadata, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise RestoreError(f"Symlink/reparse point in destination: {name}")
            if current != target and not current.is_dir():
                raise RestoreError(f"Destination parent is a file: {name}")
        if current == root:
            break
        current = current.parent
    return target


def reject_reparse_chain(path: Path) -> None:
    """Keep lexical paths until every existing ancestor has been inspected."""
    current = path.absolute()
    while True:
        if os.path.lexists(current):
            metadata = current.lstat()
            if current.is_symlink() or getattr(metadata, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise RestoreError(f"Symlink/reparse point in path: {current}")
        if current.parent == current:
            return
        current = current.parent


def file_state(root: Path, name: str, op: str, entry: dict) -> str:
    path = guarded_path(root, name)
    if not path.exists():
        if op == "changed":
            raise RestoreError(f"Changed file is missing; restore the base first: {name}")
        return "absent"
    if not path.is_file():
        raise RestoreError(f"Destination is not a regular file: {name}")
    actual = path.stat().st_size, snapshot.sha256_file(path)
    if op != "deleted" and actual == fingerprint(entry):
        return "new"
    if op != "added" and actual == fingerprint(entry, "old_" if op == "changed" else ""):
        return "old"
    raise RestoreError(f"Unknown user content; refusing overwrite/delete: {name}")


def preflight(root: Path, plan: dict) -> dict[str, str]:
    return {name: file_state(root, name, op, entry) for op, entries in plan["operations"].items() for name, entry in entries.items()}


class VerifiedZstdReader(io.RawIOBase):
    """A single zstd frame, with explicit EOF/checksum and no ignored trailing data."""

    def __init__(self, compressed, maximum_output: int):
        super().__init__()
        self.compressed = compressed
        self.decoder = zstandard.ZstdDecompressor().decompressobj()
        self.pending = b""
        self.finished = False
        self.output_bytes = 0
        self.maximum_output = maximum_output

    def readable(self):
        return True

    def readinto(self, buffer):
        while not self.pending and not self.finished:
            block = self.compressed.read(16 * 1024)
            if not block:
                raise RestoreError("Incomplete zstd frame: EOF/checksum not reached")
            self.pending = self.decoder.decompress(block)
            self.output_bytes += len(self.pending)
            if self.output_bytes > self.maximum_output:
                raise RestoreError("Decompressed stream exceeds payload/header bound")
            if self.decoder.eof:
                if self.decoder.unused_data or self.compressed.read(1):
                    raise RestoreError("Unexpected bytes or additional frame after zstd EOF")
                self.finished = True
        count = min(len(buffer), len(self.pending))
        buffer[:count] = self.pending[:count]
        self.pending = self.pending[count:]
        return count


def stage_payload(paths: list[Path], plan: dict, stage: Path) -> None:
    expected = plan["payload"]
    directories = {str(p) for name in expected for p in PurePosixPath(name).parents if str(p) != "."}
    seen, seen_dirs = set(), set()
    bound = plan["source"]["source_bytes"] + 1_048_576 + 65_536 * (len(expected) + len(directories))
    with io.BufferedReader(snapshot.ConcatenatedParts(paths), CHUNK) as compressed:
        with io.BufferedReader(VerifiedZstdReader(compressed, bound), CHUNK) as decompressed:
            with tarfile.open(fileobj=decompressed, mode="r|", ignore_zeros=True) as archive:
                for member in archive:
                    name = snapshot.safe_path(member.name, directory=member.isdir())
                    if member.isdir():
                        if name not in directories or name in seen_dirs:
                            raise RestoreError(f"Unexpected/duplicate tar directory: {name}")
                        seen_dirs.add(name)
                        continue
                    if member.type not in (tarfile.REGTYPE, tarfile.AREGTYPE) or member.issparse():
                        raise RestoreError(f"Unsafe tar member type: {name}")
                    if name not in expected or name in seen:
                        raise RestoreError(f"Unexpected/duplicate tar file: {name}")
                    seen.add(name)
                    entry = expected[name]
                    if member.size != entry["bytes"]:
                        raise RestoreError(f"Tar member size mismatch: {name}")
                    target = snapshot.target_path(stage, name)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source = archive.extractfile(member)
                    if source is None:
                        raise RestoreError(f"Cannot read tar member: {name}")
                    with source, target.open("xb") as output:
                        for block in iter(lambda: source.read(CHUNK), b""):
                            output.write(block)
                    snapshot.check_file(target, entry["bytes"], entry["sha256"])
            while decompressed.read(CHUNK):
                pass  # Must reach validated frame EOF even after tar end/padding.
    if seen != expected.keys():
        raise RestoreError(f"Missing {len(expected.keys() - seen)} payload members")


def restore_delta(paths: list[Path], plan: dict, root: Path, staging_parent: Path, *, dry_run: bool = False) -> dict:
    reject_reparse_chain(root)
    reject_reparse_chain(staging_parent)
    root = root.resolve()
    staging_parent = staging_parent.resolve()
    if root == staging_parent or root.is_relative_to(staging_parent) or staging_parent.is_relative_to(root):
        raise RestoreError("Destination and staging must be separate, non-nested directories")
    if len(paths) != len(plan["archive"]["parts"]):
        raise RestoreError("Wrong number of archive parts")
    for path, part in zip(paths, plan["archive"]["parts"]):
        if path.name != part["name"]:
            raise RestoreError("Archive parts are not in manifest order")
        snapshot.check_file(path, part["bytes"], part["sha256"])
    preflight(root, plan)
    staging_parent.mkdir(parents=True, exist_ok=True)
    written = deleted = skipped = 0
    with tempfile.TemporaryDirectory(prefix="verified-delta-", dir=staging_parent) as temporary_directory:
        stage = Path(temporary_directory).resolve()
        stage_payload(paths, plan, stage)
        states = preflight(root, plan)  # Recheck all user files after staging, before any mutation.
        if dry_run:
            return {"dry_run": True, "verified_payload_files": len(plan["payload"]), "would_write": sum(states[n] != "new" for n in plan["payload"]), "would_delete": sum(states[n] == "old" for n in plan["operations"]["deleted"]), "written": 0, "deleted": 0}
        for op in ("added", "changed"):
            for name, entry in plan["operations"][op].items():
                if file_state(root, name, op, entry) == "new":
                    skipped += 1
                    continue
                target = guarded_path(root, name)
                target.parent.mkdir(parents=True, exist_ok=True)
                handle, temp_name = tempfile.mkstemp(prefix=".delta-", suffix=".tmp", dir=target.parent)
                temp_path = Path(temp_name)
                try:
                    with os.fdopen(handle, "wb") as output, (stage / name).open("rb") as source:
                        for block in iter(lambda: source.read(CHUNK), b""):
                            output.write(block)
                    snapshot.check_file(temp_path, entry["bytes"], entry["sha256"])
                    state = file_state(root, name, op, entry)
                    if state == "new":
                        skipped += 1
                    else:
                        os.replace(temp_path, guarded_path(root, name))
                        written += 1
                finally:
                    temp_path.unlink(missing_ok=True)
        # Never remove old names/metadata before all new payload files are verified.
        for name, entry in plan["payload"].items():
            snapshot.check_file(guarded_path(root, name), entry["bytes"], entry["sha256"])
        for name, entry in plan["operations"]["deleted"].items():
            if file_state(root, name, "deleted", entry) == "old":
                guarded_path(root, name).unlink()  # Exactly one allowlisted, SHA-matching file.
                deleted += 1
    return {"dry_run": False, "verified_payload_files": len(plan["payload"]), "written": written, "skipped": skipped, "deleted": deleted}


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--archive-manifest", type=Path, default=repository / "updates/local-data-20261027/update_archive_manifest.json", help="Trusted Git-tracked archive manifest; downloaded copy must match its SHA256")
    parser.add_argument("--base-source-manifest", type=Path, default=repository / "SOURCE_FILES_SHA256.json", help="Original source manifest, whose SHA256 is fixed in this tool")
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--offline", action="store_true", help="Use existing cache only; never download")
    parser.add_argument("--dry-run", action="store_true", help="Verify metadata, parts and full staged payload; do not change destination")
    args = parser.parse_args()
    try:
        destination, cache_argument = args.destination.expanduser().absolute(), args.cache_dir.expanduser().absolute()
        reject_reparse_chain(destination)
        reject_reparse_chain(cache_argument)
        root, cache = destination.resolve(), cache_argument.resolve()
        if root == cache or root.is_relative_to(cache) or cache.is_relative_to(root):
            raise RestoreError("Destination and cache must be separate, non-nested directories")
        trusted_archive = args.archive_manifest.expanduser().resolve()
        base_manifest = args.base_source_manifest.expanduser().resolve()
        if not args.offline and (trusted_archive.is_relative_to(cache) or base_manifest.is_relative_to(cache)):
            raise RestoreError("Trusted archive/base manifests must be outside the online download cache")
        trusted_sha = snapshot.sha256_file(trusted_archive)
        archive = read_json(trusted_archive)
        # Verify all metadata before downloading any potentially large part.
        cache.mkdir(parents=True, exist_ok=True)
        reject_reparse_chain(cache / snapshot.asset_name(trusted_archive.name))
        reject_reparse_chain(cache / (trusted_archive.name + ".download"))
        if not args.offline:
            snapshot.read_json_asset(args.base_url, trusted_archive.name, cache)
        read_json(cache / trusted_archive.name, trusted_sha)
        for key in ("source_manifest", "changes_manifest"):
            name = snapshot.asset_name(archive[key])
            reject_reparse_chain(cache / name)
            reject_reparse_chain(cache / (name + ".download"))
            if not args.offline:
                snapshot.read_json_asset(args.base_url, name, cache)
        plan = load_update(cache / trusted_archive.name, cache / archive["source_manifest"], cache / archive["changes_manifest"], base_manifest)
        preflight(root, plan)
        paths = []
        for part in archive["parts"]:
            reject_reparse_chain(cache / part["name"])
            reject_reparse_chain(cache / (part["name"] + ".download"))
            if args.offline:
                path = cache / part["name"]
                snapshot.check_file(path, part["bytes"], part["sha256"])
            else:
                path = snapshot.download_part(args.base_url, part, cache)
            paths.append(path)
        result = restore_delta(paths, plan, destination, cache / "staging", dry_run=args.dry_run)
        result.update({"status": "DRY_RUN_VERIFIED" if args.dry_run else "UPDATE_APPLIED", "archive_manifest_sha256": trusted_sha, "base_source_manifest_sha256": BASE_SOURCE_SHA256})
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (RestoreError, OSError, ValueError, KeyError, TypeError, tarfile.TarError, zstandard.ZstdError, URLError, HTTPException) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted; verified final files and downloaded parts are retained; rerun safely.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf8")
    raise SystemExit(main())
