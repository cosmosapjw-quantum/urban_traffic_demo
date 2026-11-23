#!/usr/bin/env python3
"""Losslessly archive one consumed research checkpoint with full-byte evidence.

The source is removed only on explicit request, after streaming verification of
the original and decompressed SHA/length, and an fsynced durable JSON receipt.
Historical event-store seeds and all tracked files are outside allowed roots.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

BASE = Path("/home/cosmosapjw/worktrees")
ALLOWED = (
    BASE / "urban-traffic-v03-origin-validation-20261123/artifacts/v03_origin_validation_20261123",
    BASE / "urban-traffic-v03-constructive-remodel-20261123/artifacts/v03_constructive_remodel_20261123",
)
ARCHIVES = BASE / "v03-constructive-remodel-20261123-checkpoints"

def stream_identity(stream):
    digest, count = hashlib.sha256(), 0
    while chunk := stream.read(1024 * 1024):
        digest.update(chunk)
        count += len(chunk)
    return count, digest.hexdigest()

def file_identity(path):
    with path.open("rb") as stream:
        return stream_identity(stream)

def save_receipt(path, payload):
    temp = path.with_name(path.name + ".tmp")
    with temp.open("x") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--bytes", required=True, type=int)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--remove-source-after-verify", action="store_true")
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    allowed = next((p for p in ALLOWED if source.is_relative_to(p)), None)
    if allowed is None or source.suffix != ".bin":
        raise ValueError("only consumed checkpoints from this research lane may be archived")
    repo = allowed.parents[1]
    tracked = subprocess.run(["git", "-C", str(repo), "ls-files", "--error-unmatch",
                              str(source.relative_to(repo))], capture_output=True)
    if tracked.returncode != 1:
        raise ValueError("source must be an untracked checkpoint in a verified repository")
    source_stat = source.stat()
    original_stat = (source_stat.st_ino, source_stat.st_size, source_stat.st_mtime_ns)
    if args.receipt.exists():
        raise FileExistsError("receipt already exists; inspect before taking another action")
    ARCHIVES.mkdir(exist_ok=True)
    archive = ARCHIVES / (source.name + "." + args.sha256[:16] + ".zst")
    if archive.exists():
        raise FileExistsError("archive already exists; inspect before taking another action")
    started = time.perf_counter()
    free_before = shutil.disk_usage(BASE).free
    expected = args.bytes, args.sha256
    if file_identity(source) != expected:
        raise ValueError("complete source bytes differ from preserved receipt")
    subprocess.run(["zstd", "-T2", "-3", "--check", "--no-progress", "--keep",
                    str(source), "-o", str(archive)], check=True)
    with archive.open("rb") as stored:
        os.fsync(stored.fileno())
    decoder = subprocess.Popen(["zstd", "-d", "--stdout", str(archive)],
                               stdout=subprocess.PIPE)
    try:
        decoded = stream_identity(decoder.stdout)
    finally:
        decoder.stdout.close()
    if decoder.wait() != 0 or decoded != expected:
        raise ValueError("decompressed complete bytes differ; source remains")
    archive_bytes, archive_sha = file_identity(archive)
    payload = {
        "schema": "V03_VERIFIED_CHECKPOINT_ARCHIVE_V1",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_path": str(source), "source_bytes": args.bytes,
        "source_sha256": args.sha256, "archive_path": str(archive),
        "archive_bytes": archive_bytes, "archive_sha256": archive_sha,
        "decompressed_bytes": decoded[0], "decompressed_sha256": decoded[1],
        "full_byte_identity_verified": True,
        "source_removed": False,
        "free_before_bytes": free_before,
        "scope": "local lossless checkpoint storage, no physics or release acceptance credit",
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    save_receipt(args.receipt, payload)
    if args.remove_source_after_verify:
        # Recheck file metadata before unlinking; the full hash was verified above.
        current = source.stat()
        if (current.st_ino, current.st_size, current.st_mtime_ns) != original_stat:
            raise ValueError("source changed after verification; source remains")
        source.unlink()
        payload["source_removed"] = True
    payload["free_after_bytes"] = shutil.disk_usage(BASE).free
    payload["wall_s"] = time.perf_counter() - started
    save_receipt(args.receipt, payload)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
