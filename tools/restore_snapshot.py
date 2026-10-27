#!/usr/bin/env python3
"""Download, verify and safely restore the public split tar+zstd snapshot.

Python 3.10+; the only third-party dependency is zstandard.
"""
from __future__ import annotations

import argparse
import hashlib
from http.client import HTTPException
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile
import tempfile
import time
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import zstandard

BASE_URL = "https://github.com/HanqinXie/Reservoir_Industrial_Product_data/releases/download/snapshot-20261027"
CHUNK = 1024 * 1024
MAX_PART_BYTES = 640_000_000
MANIFEST_LIMIT = 128 * 1024 * 1024


class RestoreError(Exception):
    """An invalid snapshot or unsafe destination; do not continue."""


def safe_path(name: str, *, directory: bool = False) -> str:
    if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
        raise RestoreError(f"Unsafe path: {name!r}")
    if directory:
        name = name.rstrip("/")
    parts = name.split("/")
    if PurePosixPath(name).is_absolute() or any(p in ("", ".", "..") for p in parts):
        raise RestoreError(f"Unsafe path: {name!r}")
    reserved = {"CON", "PRN", "AUX", "NUL", "CLOCK$", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    for part in parts:
        if part.rstrip(" .") != part or any(ord(c) < 32 or c in '<>:"|?*' for c in part) or part.split(".")[0].upper() in reserved:
            raise RestoreError(f"Unsafe path: {name!r}")
    return name


def asset_name(name: str) -> str:
    if "/" in safe_path(name):
        raise RestoreError(f"Unsafe asset name: {name!r}")
    return name


def target_path(root: Path, name: str) -> Path:
    target = root.joinpath(*safe_path(name).split("/"))
    if not target.resolve().is_relative_to(root):
        raise RestoreError(f"Unsafe destination escape: {name!r}")
    current = target
    while current != root:
        if current.is_symlink():
            raise RestoreError(f"Unsafe destination symlink: {name!r}")
        current = current.parent
    return target


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def check_file(path: Path, size: int, digest: str) -> None:
    if not path.is_file() or path.stat().st_size != size:
        raise RestoreError(f"Size mismatch: {path.name}; expected {size} bytes")
    if sha256_file(path) != digest:
        raise RestoreError(f"SHA256 mismatch: {path.name}. Remove the damaged cache file to download again.")


def read_json_asset(base_url: str, name: str, cache: Path) -> dict:
    name = asset_name(name)
    request = Request(base_url.rstrip("/") + "/" + quote(name), headers={"User-Agent": "ReservoirSnapshotRestore/1.0"})
    with urlopen(request, timeout=60) as response:
        data = response.read(MANIFEST_LIMIT + 1)
    if len(data) > MANIFEST_LIMIT:
        raise RestoreError(f"Manifest too large: {name}")
    value = json.loads(data.decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise RestoreError(f"Manifest must be an object: {name}")
    temporary = cache / (name + ".download")
    temporary.write_bytes(data)
    os.replace(temporary, cache / name)
    return value


def download_part(base_url: str, part: dict, cache: Path) -> Path:
    name, size, digest = part["name"], part["bytes"], part["sha256"]
    final = cache / name
    if final.exists():
        check_file(final, size, digest)
        print(f"Verified cache: {name}", flush=True)
        return final
    temporary = cache / (name + ".download")
    for attempt in range(4):
        offset = temporary.stat().st_size if temporary.exists() else 0
        if offset > size:
            raise RestoreError(f"Oversized partial download: {temporary}")
        if offset == size:
            break
        headers = {"User-Agent": "ReservoirSnapshotRestore/1.0"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        request = Request(base_url.rstrip("/") + "/" + quote(name), headers=headers)
        try:
            with urlopen(request, timeout=60) as response:
                status = response.getcode()
                if status == 206:
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
                    if not match or int(match[1]) != offset or int(match[3]) != size:
                        raise RestoreError(f"Invalid Content-Range for {name}")
                elif status in (None, 200):
                    offset = 0  # A server without Range support safely restarts this part.
                else:
                    raise RestoreError(f"Unexpected HTTP status {status} for {name}")
                print(f"Downloading: {name} from byte {offset}/{size}", flush=True)
                with temporary.open("ab" if offset else "wb") as output:
                    while True:
                        block = response.read(CHUNK)
                        if not block:
                            break
                        offset += len(block)
                        if offset > size:
                            raise RestoreError(f"Download exceeds expected size: {name}")
                        output.write(block)
            if offset == size:
                break
            if attempt == 3:
                raise RestoreError(f"Incomplete download: {name}; partial cache retained")
        except (URLError, TimeoutError, ConnectionError, OSError, HTTPException) as error:
            if attempt == 3:
                raise RestoreError(f"Download failed: {name}; partial cache retained: {error}") from error
            print(f"Download interrupted; retrying {name}", file=sys.stderr, flush=True)
        time.sleep(min(2 ** attempt, 8))
    check_file(temporary, size, digest)
    os.replace(temporary, final)
    return final


def validate_manifest(archive: dict, source: dict) -> dict[str, dict]:
    if archive.get("archive_format") != "tar+zstd":
        raise RestoreError("Unsupported archive_format; expected tar+zstd")
    parts = archive.get("parts")
    if not isinstance(parts, list) or not parts:
        raise RestoreError("Missing archive parts")
    names = set()
    for part in parts:
        name = asset_name(part["name"])
        if name.casefold() in names:
            raise RestoreError(f"Duplicate part: {name}")
        names.add(name.casefold())
        if type(part["bytes"]) is not int or not 0 < part["bytes"] <= MAX_PART_BYTES:
            raise RestoreError(f"Invalid part size: {name}")
        if not re.fullmatch(r"[0-9a-f]{64}", part["sha256"]):
            raise RestoreError(f"Invalid part SHA256: {name}")
    if archive.get("compressed_bytes") != sum(p["bytes"] for p in parts):
        raise RestoreError("compressed_bytes differs from part sizes")
    files = source.get("files")
    if not isinstance(files, list):
        raise RestoreError("Missing source file list")
    expected = {}
    aliases = set()
    for entry in files:
        name = safe_path(entry["path"])
        if name.casefold() in aliases:
            raise RestoreError(f"Duplicate source path: {name}")
        aliases.add(name.casefold())
        if type(entry["bytes"]) is not int or entry["bytes"] < 0 or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise RestoreError(f"Invalid source size/SHA256: {name}")
        if type(entry.get("mtime_ns")) is not int:
            raise RestoreError(f"Invalid source mtime_ns: {name}")
        expected[name] = entry
    if archive.get("source_file_count") != len(expected) or archive.get("source_bytes") != sum(f["bytes"] for f in expected.values()):
        raise RestoreError("Source counts/bytes do not match archive manifest")
    for name in expected:
        if any(str(parent) in expected for parent in PurePosixPath(name).parents if str(parent) != "."):
            raise RestoreError(f"Source path is also a directory: {name}")
    return expected


class ConcatenatedParts(io.RawIOBase):
    """Read split compressed parts as one seek-free binary stream."""

    def __init__(self, paths: list[Path]):
        super().__init__()
        self.paths = iter(paths)
        self.current = None

    def readable(self):
        return True

    def readinto(self, buffer):
        while True:
            if self.current is None:
                path = next(self.paths, None)
                if path is None:
                    return 0
                self.current = path.open("rb")
            count = self.current.readinto(buffer)
            if count:
                return count
            self.current.close()
            self.current = None

    def close(self):
        if self.current is not None:
            self.current.close()
        super().close()


def restore(paths: list[Path], expected: dict[str, dict], root: Path, overwrite: bool) -> tuple[int, int]:
    skip = set()
    # Refuse conflicting existing files before writing any restored content.
    for name, entry in expected.items():
        target = target_path(root, name)
        if target.exists():
            if target.is_file() and target.stat().st_size == entry["bytes"] and sha256_file(target) == entry["sha256"]:
                skip.add(name)
            elif not overwrite or not target.is_file():
                raise RestoreError(f"Existing different file: {name}; use --overwrite to replace regular files")
    allowed_directories = {str(parent) for name in expected for parent in PurePosixPath(name).parents if str(parent) != "."}
    seen, seen_directories = set(), set()
    restored = skipped = 0
    root.mkdir(parents=True, exist_ok=True)
    with io.BufferedReader(ConcatenatedParts(paths), CHUNK) as compressed:
        with zstandard.ZstdDecompressor().stream_reader(compressed, read_across_frames=True) as decompressed:
            with tarfile.open(fileobj=decompressed, mode="r|", ignore_zeros=True) as archive:
                for member in archive:
                    name = safe_path(member.name, directory=member.isdir())
                    if member.isdir():
                        if name not in allowed_directories:
                            raise RestoreError(f"Unexpected directory: {name}")
                        if name in seen_directories:
                            raise RestoreError(f"Duplicate directory: {name}")
                        seen_directories.add(name)
                        target_path(root, name).mkdir(parents=True, exist_ok=True)
                        continue
                    if member.type not in (tarfile.REGTYPE, tarfile.AREGTYPE) or member.issparse():
                        raise RestoreError(f"Unsafe member type: {name}")
                    if name not in expected:
                        raise RestoreError(f"Unexpected archive member: {name}")
                    if name in seen:
                        raise RestoreError(f"Duplicate archive member: {name}")
                    seen.add(name)
                    entry = expected[name]
                    if member.size != entry["bytes"]:
                        raise RestoreError(f"Size mismatch in archive: {name}")
                    target = target_path(root, name)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temporary = None
                    output = None
                    try:
                        if name not in skip:
                            handle, temporary_name = tempfile.mkstemp(prefix=".restore-", suffix=".tmp", dir=target.parent)
                            temporary = Path(temporary_name)
                            output = os.fdopen(handle, "wb")
                        digest, count = hashlib.sha256(), 0
                        extracted = archive.extractfile(member)
                        if extracted is None:
                            raise RestoreError(f"Cannot read archive member: {name}")
                        with extracted:
                            for block in iter(lambda: extracted.read(CHUNK), b""):
                                digest.update(block)
                                count += len(block)
                                if output:
                                    output.write(block)
                        if output:
                            output.close()
                            output = None
                        if count != entry["bytes"] or digest.hexdigest() != entry["sha256"]:
                            raise RestoreError(f"SHA256/size mismatch in archive member: {name}")
                        if temporary is not None:
                            target_path(root, name)  # Recheck before the atomic replace.
                            if target.exists() and not overwrite:
                                raise RestoreError(f"Destination appeared during restore: {name}; refusing overwrite")
                            os.replace(temporary, target)
                            temporary = None
                            if os.name != "nt":
                                os.chmod(target, member.mode & 0o777)
                            restored += 1
                        else:
                            skipped += 1
                        os.utime(target, ns=(entry["mtime_ns"], entry["mtime_ns"]))
                    finally:
                        if output:
                            output.close()
                        if temporary is not None:
                            temporary.unlink(missing_ok=True)
            # Reach EOF so decompression/frame errors are not hidden by tar padding.
            while decompressed.read(CHUNK):
                pass
    missing = set(expected) - seen
    if missing:
        example = sorted(missing)[0]
        raise RestoreError(f"Missing {len(missing)} source files from archive; first: {example}")
    return restored, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True, help="Directory in which original folders will be restored")
    parser.add_argument("--cache-dir", type=Path, required=True, help="Persistent directory for downloaded split parts")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing existing regular files with different contents")
    parser.add_argument("--base-url", default=BASE_URL, help="Release asset base URL; override only for a trusted mirror/test fixture")
    args = parser.parse_args()
    try:
        cache = args.cache_dir.expanduser().resolve()
        root = args.destination.expanduser().resolve()
        if root == cache or cache.is_relative_to(root) or root.is_relative_to(cache):
            raise RestoreError("--destination and --cache-dir must be separate, non-nested directories")
        cache.mkdir(parents=True, exist_ok=True)
        archive = read_json_asset(args.base_url, "archive_manifest.json", cache)
        source_name = asset_name(archive["source_manifest"])
        source = read_json_asset(args.base_url, source_name, cache)
        expected = validate_manifest(archive, source)
        print(f"Snapshot: {len(expected)} files, {archive['source_bytes']} source bytes, {len(archive['parts'])} parts", flush=True)
        paths = [download_part(args.base_url, part, cache) for part in archive["parts"]]
        restored, skipped = restore(paths, expected, root, args.overwrite)
        print(f"SUCCESS: restored={restored}, skipped={skipped}, verified={len(expected)}; destination={root}")
        return 0
    except (RestoreError, OSError, ValueError, KeyError, TypeError, tarfile.TarError, zstandard.ZstdError, URLError, HTTPException) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted; downloaded partial parts are retained for the next run.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
