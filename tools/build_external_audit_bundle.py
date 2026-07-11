#!/usr/bin/env python3
"""Build an integrity-checked Metroflow audit archive with normalized ZIP layout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_RELATIVE = Path("docs/audit/metroflow_external_audit_20260711")
DEFAULT_AUDIT_DATE = "2026-07-11"


def _run(
    args: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=cwd,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def _git(repo_root: Path, *args: str, check: bool = True) -> str:
    return _run(("git", *args), cwd=repo_root, check=check).stdout.strip()


def _git_bytes(repo_root: Path, *args: str) -> bytes:
    process = subprocess.run(
        ("git", *args),
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return process.stdout


def _parse_audit_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("audit_date must use canonical YYYY-MM-DD format") from exc
    if parsed.isoformat() != value:
        raise ValueError("audit_date must use canonical YYYY-MM-DD format")
    return parsed


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _command_version(command: Sequence[str], *, cwd: Path) -> str:
    try:
        return _run(command, cwd=cwd, check=False).stdout.strip()
    except OSError as exc:
        return f"unavailable: {exc}"


def _tracked_paths(repo_root: Path, commit: str) -> tuple[str, ...]:
    raw = _git_bytes(repo_root, "ls-tree", "-rz", "--full-tree", commit)
    paths: list[str] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        header, separator, encoded = record.partition(b"\t")
        if not separator:
            raise RuntimeError("unable to parse git tree entry")
        fields = header.split()
        if len(fields) != 3:
            raise RuntimeError("unable to parse git tree entry header")
        mode, object_type, _ = fields
        if mode not in {b"100644", b"100755"} or object_type != b"blob":
            raise RuntimeError(
                "tracked symlinks, gitlinks, and non-regular files are not supported "
                "by audit packaging"
            )
        try:
            value = encoded.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError("tracked paths must be valid UTF-8 for audit packaging") from exc
        _validate_checksum_path(value)
        paths.append(value)
    return tuple(paths)


def _validate_checksum_path(value: str) -> None:
    if not value or "\n" in value or "\r" in value or "\\" in value:
        raise RuntimeError(
            "audit package paths must be non-empty and contain no newline, carriage return, "
            "or backslash"
        )
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise RuntimeError(f"unsafe audit package path: {value!r}")


def _extract_commit_snapshot(destination: Path, *, repo_root: Path, commit: str) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".tar") as archive_file:
        subprocess.run(
            ("git", "archive", "--format=tar", commit),
            cwd=repo_root,
            check=True,
            stdout=archive_file,
        )
        archive_file.flush()
        with tarfile.open(archive_file.name, mode="r") as archive:
            archive.extractall(destination, filter="data")


def _tracked_file_hashes(
    snapshot_root: Path,
    *,
    tracked_paths: Sequence[str],
) -> dict[str, str]:
    return {path: _sha256(snapshot_root / path) for path in tracked_paths}


def _zip_datetime(commit_epoch: int) -> tuple[int, int, int, int, int, int]:
    value = datetime.fromtimestamp(commit_epoch, tz=UTC)
    if value.year < 1980:
        value = datetime(1980, 1, 1, tzinfo=UTC)
    return value.year, value.month, value.day, value.hour, value.minute, value.second


def _package_files(package_root: Path) -> list[Path]:
    return sorted(item for item in package_root.rglob("*") if item.is_file())


def _write_normalized_zip(source_root: Path, output: Path, commit_epoch: int) -> None:
    timestamp = _zip_datetime(commit_epoch)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in _package_files(source_root):
            relative = path.relative_to(source_root.parent).as_posix()
            _validate_checksum_path(relative)
            info = zipfile.ZipInfo(relative, date_time=timestamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (path.stat().st_mode & 0xFFFF) << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)


def _inventory(
    snapshot_root: Path,
    *,
    repo_root: Path,
    tracked_paths: Sequence[str],
    ref_tips: Sequence[str],
) -> dict[str, int]:
    def count(pattern: str, root: Path) -> int:
        return sum(1 for item in root.rglob(pattern) if item.is_file())

    return {
        "tracked_file_count": len(tracked_paths),
        "python_source_file_count": count("*.py", snapshot_root / "src"),
        "python_test_file_count": count("test_*.py", snapshot_root / "tests"),
        "rust_source_file_count": count("*.rs", snapshot_root / "crates"),
        "commit_count_all_refs": int(
            _git(repo_root, "rev-list", "--count", *sorted(set(ref_tips)))
        ),
    }


def _write_checksums(package_root: Path) -> None:
    entries: list[str] = []
    for path in _package_files(package_root):
        if path.name == "SHA256SUMS":
            continue
        relative = path.relative_to(package_root).as_posix()
        _validate_checksum_path(relative)
        entries.append(f"{_sha256(path)}  {relative}")
    _write_text(package_root / "SHA256SUMS", "\n".join(entries))


def _verify_zip_integrity(
    zip_path: Path,
    *,
    package_name: str,
    expected_commit: str,
) -> None:
    prefix = f"{package_name}/"
    checksum_member = f"{prefix}SHA256SUMS"
    with zipfile.ZipFile(zip_path) as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise RuntimeError(f"ZIP CRC check failed at {bad_member}")
        names = {info.filename for info in archive.infolist() if not info.is_dir()}
        for name in names:
            if not name.startswith(prefix):
                raise RuntimeError(f"ZIP member escapes package root: {name}")
            _validate_checksum_path(name)
        if checksum_member not in names:
            raise RuntimeError("ZIP is missing SHA256SUMS")
        listed: set[str] = set()
        for line in archive.read(checksum_member).decode("utf-8").splitlines():
            digest, separator, relative = line.partition("  ")
            if not separator or len(digest) != 64:
                raise RuntimeError(f"invalid SHA256SUMS entry: {line!r}")
            _validate_checksum_path(relative)
            member = f"{prefix}{relative}"
            if member not in names:
                raise RuntimeError(f"checksum references missing ZIP member: {relative}")
            if _sha256_bytes(archive.read(member)) != digest:
                raise RuntimeError(f"ZIP SHA-256 mismatch: {relative}")
            listed.add(member)
        expected = names - {checksum_member}
        if listed != expected:
            raise RuntimeError("SHA256SUMS does not cover every non-checksum ZIP member")

        manifest_member = f"{prefix}MANIFEST.json"
        if manifest_member not in names:
            raise RuntimeError("ZIP is missing MANIFEST.json")
        manifest = json.loads(archive.read(manifest_member))
        if manifest.get("packaged_commit") != expected_commit:
            raise RuntimeError("manifest packaged_commit does not match the snapshot commit")
        if manifest.get("entry_exclusions") != ["MANIFEST.json", "SHA256SUMS"]:
            raise RuntimeError("manifest entry exclusions are invalid")
        manifest_entries = manifest.get("entries")
        if not isinstance(manifest_entries, list):
            raise RuntimeError("manifest entries must be a list")
        observed_entries: dict[str, tuple[int, str]] = {}
        for entry in manifest_entries:
            if not isinstance(entry, dict):
                raise RuntimeError("manifest entry must be an object")
            relative = entry.get("path")
            if not isinstance(relative, str):
                raise RuntimeError("manifest entry path must be a string")
            _validate_checksum_path(relative)
            if relative in observed_entries:
                raise RuntimeError(f"duplicate manifest entry: {relative}")
            member = f"{prefix}{relative}"
            if member not in names:
                raise RuntimeError(f"manifest references missing ZIP member: {relative}")
            content = archive.read(member)
            expected_size = entry.get("bytes")
            expected_digest = entry.get("sha256")
            if expected_size != len(content) or expected_digest != _sha256_bytes(content):
                raise RuntimeError(f"manifest metadata mismatch: {relative}")
            observed_entries[relative] = (len(content), _sha256_bytes(content))
        expected_manifest_paths = {
            name.removeprefix(prefix)
            for name in names
            if name not in {manifest_member, checksum_member}
        }
        if set(observed_entries) != expected_manifest_paths:
            raise RuntimeError("manifest does not cover every declared payload member")


def _parse_ref_map(text: str) -> dict[str, str]:
    refs: dict[str, str] = {}
    for line in text.splitlines():
        object_id, separator, ref_name = line.partition(" ")
        if not separator or not object_id or not ref_name or ref_name in refs:
            raise RuntimeError(f"invalid or duplicate ref listing: {line!r}")
        refs[ref_name] = object_id
    if not refs:
        raise RuntimeError("audit history requires at least one Git ref")
    return refs


def _repo_state(repo_root: Path) -> dict[str, str]:
    return {
        "status": _git(repo_root, "status", "--short"),
        "head": _git(repo_root, "rev-parse", "HEAD"),
        "refs": _git(repo_root, "show-ref", "--head"),
        "branch": _git(repo_root, "branch", "--show-current"),
    }


def build_bundle(
    output_dir: Path,
    *,
    audit_date: str,
    allow_dirty: bool,
    repo_root: Path = REPO_ROOT,
    audit_relative: Path = AUDIT_RELATIVE,
) -> dict[str, Any]:
    parsed_date = _parse_audit_date(audit_date)
    repo_root = repo_root.resolve()
    _validate_checksum_path(audit_relative.as_posix())
    if _git(repo_root, "rev-parse", "--is-shallow-repository") == "true":
        raise RuntimeError("shallow repository cannot provide complete reachable history")

    initial_state = _repo_state(repo_root)
    initial_ref_map = _parse_ref_map(initial_state["refs"])
    status = initial_state["status"]
    if status and not allow_dirty:
        raise RuntimeError(
            "working tree is dirty; commit intended audit files before packaging\n" + status
        )

    commit = initial_state["head"]
    tracked_paths = _tracked_paths(repo_root, commit)
    short_commit = commit[:12]
    commit_epoch = int(_git(repo_root, "show", "-s", "--format=%ct", commit))
    date_slug = parsed_date.strftime("%Y%m%d")
    package_name = f"metroflow_external_audit_{date_slug}_{short_commit}"
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_zip = output_dir / f"{package_name}.zip"
    digest_path = output_zip.with_suffix(output_zip.suffix + ".sha256")
    temporary_zip = output_dir / f".{package_name}.zip.tmp-{os.getpid()}"
    temporary_sidecar = output_dir / f".{package_name}.zip.sha256.tmp-{os.getpid()}"

    try:
        with tempfile.TemporaryDirectory(prefix="metroflow-audit-") as temp_dir:
            package_root = Path(temp_dir) / package_name
            snapshot_root = package_root / "repository"
            history_root = package_root / "history"
            provenance_root = package_root / "provenance"
            history_root.mkdir(parents=True)
            provenance_root.mkdir(parents=True)

            _extract_commit_snapshot(snapshot_root, repo_root=repo_root, commit=commit)
            audit_snapshot = snapshot_root / audit_relative
            if not audit_snapshot.is_dir():
                raise RuntimeError(f"audit documents are missing from commit: {audit_relative}")

            shutil.copy2(audit_snapshot / "README.md", package_root / "AUDIT_START_HERE.md")
            shutil.copy2(
                audit_snapshot / "NO_LICENSE_NOTICE.md",
                package_root / "NO_LICENSE_NOTICE.md",
            )

            bundle_path = history_root / "metroflow-all-refs.bundle"
            _run(
                ("git", "bundle", "create", str(bundle_path), "--all"),
                cwd=repo_root,
            )
            bundle_verify = _run(
                ("git", "bundle", "verify", str(bundle_path)),
                cwd=repo_root,
            ).stdout
            _write_text(provenance_root / "git-bundle-verify.txt", bundle_verify)
            bundle_heads = _run(
                ("git", "bundle", "list-heads", str(bundle_path)),
                cwd=repo_root,
            ).stdout.strip()
            if _parse_ref_map(bundle_heads) != initial_ref_map:
                raise RuntimeError("history bundle refs do not match the initial ref snapshot")

            history_format = "%H%x09%aI%x09%an%x09%ae%x09%s"
            _write_text(
                history_root / "commit-history.tsv",
                "commit\tauthor_date\tauthor_name\tauthor_email\tsubject\n"
                + _git(
                    repo_root,
                    "log",
                    f"--format={history_format}",
                    *sorted(set(initial_ref_map.values())),
                ),
            )
            _write_text(history_root / "refs.txt", bundle_heads)
            _write_text(provenance_root / "git-status.txt", status or "clean")
            _write_text(
                provenance_root / "git-fsck.txt",
                _run(("git", "fsck", "--full"), cwd=repo_root).stdout or "ok",
            )
            _write_text(
                provenance_root / "git-count-objects.txt",
                _git(repo_root, "count-objects", "-vH"),
            )

            environment = {
                "captured_at_utc": datetime.now(tz=UTC).isoformat(),
                "platform": platform.platform(),
                "python": platform.python_version(),
                "python_executable": sys.executable,
                "git": _command_version(("git", "--version"), cwd=repo_root),
                "rustc": _command_version(("rustc", "--version"), cwd=repo_root),
                "cargo": _command_version(("cargo", "--version"), cwd=repo_root),
                "nvidia_smi": _command_version(
                    (
                        "nvidia-smi",
                        "--query-gpu=name,memory.total,driver_version",
                        "--format=csv,noheader",
                    ),
                    cwd=repo_root,
                ),
                "note": "capture does not import optional JAX, torch, or the Rust extension",
            }
            _write_text(
                provenance_root / "environment.json",
                json.dumps(environment, indent=2, sort_keys=True),
            )
            _write_text(
                provenance_root / "python-packages.txt",
                _command_version(
                    (sys.executable, "-m", "pip", "freeze", "--all"),
                    cwd=repo_root,
                ),
            )

            tracked_hashes = _tracked_file_hashes(
                snapshot_root,
                tracked_paths=tracked_paths,
            )
            _write_text(
                provenance_root / "tracked-files-sha256.json",
                json.dumps(tracked_hashes, indent=2, sort_keys=True),
            )

            build_options = {
                "output_dir": str(output_dir),
                "audit_date": parsed_date.isoformat(),
                "allow_dirty": bool(allow_dirty),
            }
            metadata = {
                "schema_version": "metroflow.external-audit-package.v1",
                "audit_date": parsed_date.isoformat(),
                "packaged_commit": commit,
                "packaged_ref": initial_state["branch"] or "detached",
                "commit_author_date": _git(
                    repo_root,
                    "show",
                    "-s",
                    "--format=%aI",
                    commit,
                ),
                "source_audit_baseline": (
                    "96e54ca907babe6425212ac2e088615687549d72"
                ),
                "working_tree_status": "dirty override" if status else "clean",
                "build_options": build_options,
                "inventory": _inventory(
                    snapshot_root,
                    repo_root=repo_root,
                    tracked_paths=tracked_paths,
                    ref_tips=tuple(initial_ref_map.values()),
                ),
                "contents": {
                    "snapshot": "repository/",
                    "history_bundle": "history/metroflow-all-refs.bundle",
                    "audit_entrypoint": "AUDIT_START_HERE.md",
                    "checksums": "SHA256SUMS",
                },
                "limitations": [
                    "no root license grant",
                    "pre-import and donor history is not present in supplied git objects",
                    "historical experiment artifacts are not independently attested",
                    "git bundle bytes and host environment capture are not reproducible bytes",
                ],
            }
            _write_text(
                provenance_root / "package_metadata.json",
                json.dumps(metadata, indent=2, sort_keys=True),
            )
            command = [
                sys.executable,
                "tools/build_external_audit_bundle.py",
                "--output-dir",
                str(output_dir),
                "--audit-date",
                parsed_date.isoformat(),
            ]
            if allow_dirty:
                command.append("--allow-dirty")
            _write_text(provenance_root / "build-command.txt", shlex.join(command))

            manifest_entries = []
            for path in _package_files(package_root):
                manifest_entries.append(
                    {
                        "path": path.relative_to(package_root).as_posix(),
                        "bytes": path.stat().st_size,
                        "sha256": _sha256(path),
                    }
                )
            manifest = {
                "schema_version": "metroflow.external-audit-manifest.v1",
                "packaged_commit": commit,
                "entry_exclusions": ["MANIFEST.json", "SHA256SUMS"],
                "entries": manifest_entries,
            }
            _write_text(
                package_root / "MANIFEST.json",
                json.dumps(manifest, indent=2, sort_keys=True),
            )
            _write_checksums(package_root)

            final_state = _repo_state(repo_root)
            if final_state != initial_state:
                raise RuntimeError("repository HEAD, refs, or working tree changed during packaging")

            _write_normalized_zip(package_root, temporary_zip, commit_epoch)
            _verify_zip_integrity(
                temporary_zip,
                package_name=package_name,
                expected_commit=commit,
            )
            zip_digest = _sha256(temporary_zip)
            _write_text(temporary_sidecar, f"{zip_digest}  {output_zip.name}")
            digest_path.unlink(missing_ok=True)
            os.replace(temporary_zip, output_zip)
            os.replace(temporary_sidecar, digest_path)
    finally:
        temporary_zip.unlink(missing_ok=True)
        temporary_sidecar.unlink(missing_ok=True)

    if _sha256(output_zip) != zip_digest:
        raise RuntimeError("published ZIP digest changed after verification")
    return {
        "zip": str(output_zip),
        "sha256_file": str(digest_path),
        "sha256": zip_digest,
        "packaged_commit": commit,
        "bytes": output_zip.stat().st_size,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "dist",
        help="directory for the ZIP and SHA-256 sidecar",
    )
    parser.add_argument("--audit-date", default=DEFAULT_AUDIT_DATE)
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="archive HEAD while explicitly recording that working-tree changes were excluded",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        result = build_bundle(
            args.output_dir,
            audit_date=args.audit_date,
            allow_dirty=args.allow_dirty,
        )
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"external audit bundle build failed: {exc}") from exc
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
