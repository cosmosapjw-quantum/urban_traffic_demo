#!/usr/bin/env python3
"""Build a canonical, provenance-bound map evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import subprocess
import tempfile
from typing import Sequence
import zipfile


_FULL_OBJECT_ID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_BUNDLE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_PYTHON_312_VERSION = re.compile(r"3\.12\.\d+(?:[a-z0-9.+-]*)?")
_PACKAGE_VERSION = re.compile(r"\d+\.\d+\.\d+(?:[a-z0-9.+-]*)?")
_MANIFEST_NAME = "PAYLOAD_MANIFEST.json"
_IN_PROCESS_REPLAY_STATUS = "IN_PROCESS_SERIALIZATION_MATCH_ONLY"
_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_INTEGRITY_WRAPPER_NAMES = {
    "checksum",
    "checksum.txt",
    "checksums",
    "checksums.txt",
    "content_manifest.json",
    "file_manifest.json",
    "payload_manifest.json",
    "sha256sum",
    "sha256sum.txt",
    "sha256sums",
    "sha256sums.txt",
}
_INTEGRITY_WRAPPER_SUFFIXES = (".sha256", ".sha256sum", ".sha256sums")
_PROTECTED_HISTORICAL_BASENAMES = {
    "metroflow_capr_research_2026-08-08",
    "metroflow_map_generation_reaudit_2026-08-08",
    "morphology-null-operator-control-20260808",
}
_HOST_DEPENDENT_ENVIRONMENT_FIELDS = {
    "captured_at",
    "captured_at_utc",
    "cwd",
    "hostname",
    "platform",
    "python_executable",
    "timestamp",
}


def _git(repo_root: Path, *args: str, check: bool = True) -> str:
    process = subprocess.run(
        ("git", *args),
        cwd=repo_root,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return process.stdout.strip()


def _git_bytes(repo_root: Path, *args: str) -> bytes:
    return subprocess.run(
        ("git", *args),
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ).stdout


def _resolve_explicit_commit(repo_root: Path, value: str, *, field: str) -> str:
    if _FULL_OBJECT_ID.fullmatch(value) is None:
        raise ValueError(f"{field} must be a full commit id")
    try:
        resolved = _git(repo_root, "rev-parse", "--verify", f"{value}^{{commit}}")
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"{field} does not resolve to a commit") from exc
    if resolved != value:
        raise RuntimeError(f"{field} did not resolve exactly")
    return resolved


def _is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    process = subprocess.run(
        ("git", "merge-base", "--is-ancestor", ancestor, descendant),
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if process.returncode not in {0, 1}:
        raise RuntimeError("unable to verify audited-base ancestry")
    return process.returncode == 0


def _repository_state(repo_root: Path) -> tuple[str, str, str]:
    return (
        _git(repo_root, "rev-parse", "HEAD"),
        _git(repo_root, "show-ref", "--head"),
        _git(repo_root, "status", "--porcelain=v1", "--untracked-files=all"),
    )


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _validate_payload_path(value: str) -> str:
    if not value or "\n" in value or "\r" in value or "\\" in value:
        raise ValueError("payload paths must be non-empty canonical POSIX paths")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ValueError(f"unsafe or noncanonical payload path: {value!r}")
    folded_parts = tuple(part.casefold() for part in path.parts)
    if any(
        part in _INTEGRITY_WRAPPER_NAMES or part.endswith(_INTEGRITY_WRAPPER_SUFFIXES)
        for part in folded_parts
    ):
        raise ValueError(f"integrity wrapper cannot be a payload: {value!r}")
    return value


def _read_regular_blob(repo_root: Path, commit: str, path: str) -> bytes:
    listing = _git(repo_root, "ls-tree", commit, "--", path)
    if not listing:
        raise RuntimeError(f"payload is missing from producer commit: {path}")
    metadata, separator, listed_path = listing.partition("\t")
    fields = metadata.split()
    if not separator or listed_path != path or len(fields) != 3:
        raise RuntimeError(f"unable to resolve payload in producer commit: {path}")
    mode, object_type, _ = fields
    if mode not in {"100644", "100755"} or object_type != "blob":
        raise RuntimeError(f"payload must be a tracked regular file: {path}")
    return _git_bytes(repo_root, "show", f"{commit}:{path}")


def _write_canonical_zip(path: Path, *, root_name: str, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for relative in sorted(members):
            info = zipfile.ZipInfo(f"{root_name}/{relative}", date_time=_FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = (0o100644 & 0xFFFF) << 16
            archive.writestr(info, members[relative])


def _reject_host_dependent_environment(value: object, *, location: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _HOST_DEPENDENT_ENVIRONMENT_FIELDS:
                raise RuntimeError(
                    f"normalized environment contains host-dependent field: {location}.{key}"
                )
            _reject_host_dependent_environment(child, location=f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_host_dependent_environment(child, location=f"{location}[{index}]")


def _validate_normalized_environment(value: object) -> None:
    if not isinstance(value, dict) or value.get("schema_version") != (
        "metroflow.normalized-environment.v1"
    ):
        raise RuntimeError("environment lock has an unsupported schema_version")
    python_version = value.get("python")
    numpy_version = value.get("numpy")
    if (
        not isinstance(python_version, str)
        or _PYTHON_312_VERSION.fullmatch(python_version) is None
        or not isinstance(numpy_version, str)
        or _PACKAGE_VERSION.fullmatch(numpy_version) is None
    ):
        raise RuntimeError("environment lock requires exact Python 3.12 and NumPy versions")
    _reject_host_dependent_environment(value)


def _reject_promoted_payload_claims(path: str, content: bytes) -> None:
    if not path.casefold().endswith(".json"):
        return
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return
    if not isinstance(payload, dict):
        return
    expected = {
        "diagnostic_status": "IMPLEMENTED_DIAGNOSTIC",
        "evidence_status": "IMPLEMENTED_DIAGNOSTIC",
        "historical_artifact_replay_status": "NOT_REPRODUCIBLY_CLOSED",
    }
    conflicts = {
        key: payload[key]
        for key, expected_value in expected.items()
        if key in payload and payload[key] != expected_value
    }
    if conflicts:
        raise RuntimeError(f"payload claim status conflicts with G0 boundary: {path}")


def verify_map_evidence_bundle(zip_path: Path, digest_path: Path) -> dict[str, object]:
    """Verify the detached digest and return the embedded payload manifest."""

    zip_path = zip_path.resolve()
    digest_path = digest_path.resolve()
    try:
        sidecar = digest_path.read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeError("detached ZIP digest is missing or invalid") from exc
    line = sidecar.removesuffix("\n")
    digest, separator, filename = line.partition("  ")
    if (
        not separator
        or sidecar != line + "\n"
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        or filename != zip_path.name
    ):
        raise RuntimeError("detached ZIP digest receipt is malformed")
    observed = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    if observed != digest:
        raise RuntimeError("detached ZIP digest mismatch")

    root_name = zip_path.name.removesuffix(".zip")
    with zipfile.ZipFile(zip_path) as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise RuntimeError(f"ZIP CRC check failed at {bad_member}")
        infos = archive.infolist()
        if archive.comment:
            raise RuntimeError("noncanonical ZIP archive comment")
        for info in infos:
            if (
                info.is_dir()
                or info.date_time != _FIXED_ZIP_TIME
                or info.compress_type != zipfile.ZIP_STORED
                or info.create_system != 3
                or ((info.external_attr >> 16) & 0o777) != 0o644
                or info.extra
                or info.comment
            ):
                raise RuntimeError(f"noncanonical ZIP member metadata: {info.filename}")
        names = [info.filename for info in infos]
        if names != sorted(names):
            raise RuntimeError("ZIP members are not in canonical sorted order")
        if len(names) != len(set(names)):
            raise RuntimeError("ZIP contains a duplicate member name")
        prefix = f"{root_name}/"
        if any(not name.startswith(prefix) for name in names):
            raise RuntimeError("ZIP member escapes the canonical package root")
        try:
            manifest_bytes = archive.read(f"{prefix}{_MANIFEST_NAME}")
        except KeyError as exc:
            raise RuntimeError("ZIP is missing PAYLOAD_MANIFEST.json") from exc
        try:
            manifest = json.loads(manifest_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("payload manifest is not valid UTF-8 JSON") from exc
        if not isinstance(manifest, dict):
            raise RuntimeError("payload manifest must be a JSON object")
        if manifest_bytes != _canonical_json(manifest):
            raise RuntimeError("payload manifest JSON is not canonical")
        if manifest.get("schema_version") != "metroflow.map-evidence-manifest.v2":
            raise RuntimeError("payload manifest schema_version is invalid")
        audited_base = manifest.get("audited_base_commit")
        producer_source = manifest.get("producer_source_commit")
        if not isinstance(audited_base, str) or _FULL_OBJECT_ID.fullmatch(audited_base) is None:
            raise RuntimeError("payload manifest audited_base_commit is invalid")
        if (
            not isinstance(producer_source, str)
            or _FULL_OBJECT_ID.fullmatch(producer_source) is None
        ):
            raise RuntimeError("payload manifest producer_source_commit is invalid")
        if audited_base == producer_source:
            raise RuntimeError("audited base and producer source commits must be distinct")
        expected_claims = {
            "diagnostic_status": "IMPLEMENTED_DIAGNOSTIC",
            "historical_artifact_replay_status": "NOT_REPRODUCIBLY_CLOSED",
            "new_bundle_byte_replay_status": _IN_PROCESS_REPLAY_STATUS,
        }
        if manifest.get("claims") != expected_claims:
            raise RuntimeError("payload manifest claim statuses are invalid")
        expected_boundary = {
            "detached_digest": digest_path.name,
            "excluded_members": [_MANIFEST_NAME],
            "manifest_scope": "payload_only",
        }
        if manifest.get("integrity_boundary") != expected_boundary:
            raise RuntimeError("payload manifest integrity boundary is invalid")

        entries = manifest.get("payloads")
        if not isinstance(entries, list):
            raise RuntimeError("payload manifest payloads must be a list")
        observed_paths: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                raise RuntimeError("payload manifest entry must contain a path")
            try:
                relative = _validate_payload_path(entry["path"])
            except ValueError as exc:
                raise RuntimeError(str(exc)) from exc
            if relative in observed_paths:
                raise RuntimeError(f"duplicate payload manifest entry: {relative}")
            observed_paths.add(relative)
            member = f"{prefix}{relative}"
            if member not in names:
                raise RuntimeError(f"payload manifest references missing member: {relative}")
            content = archive.read(member)
            if (
                entry.get("bytes") != len(content)
                or entry.get("sha256") != hashlib.sha256(content).hexdigest()
            ):
                raise RuntimeError(f"payload manifest metadata mismatch: {relative}")
            _reject_promoted_payload_claims(relative, content)
        expected_names = {f"{prefix}{path}" for path in observed_paths}
        expected_names.add(f"{prefix}{_MANIFEST_NAME}")
        if set(names) != expected_names:
            raise RuntimeError("payload manifest does not cover every payload member")

        environment_lock = manifest.get("environment_lock")
        if not isinstance(environment_lock, dict):
            raise RuntimeError("payload manifest environment_lock is invalid")
        lock_path = environment_lock.get("path")
        if lock_path not in observed_paths:
            raise RuntimeError("environment lock is not a declared payload")
        lock_bytes = archive.read(f"{prefix}{lock_path}")
        if environment_lock.get("sha256") != hashlib.sha256(lock_bytes).hexdigest():
            raise RuntimeError("environment lock digest mismatch")
        try:
            lock_payload = json.loads(lock_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("environment lock is not valid UTF-8 JSON") from exc
        if lock_bytes != _canonical_json(lock_payload):
            raise RuntimeError("environment lock JSON is not canonical")
        _validate_normalized_environment(lock_payload)
    return manifest


def build_map_evidence_bundle(
    output_dir: Path,
    *,
    repo_root: Path,
    audited_base_commit: str,
    producer_source_commit: str,
    payload_paths: Sequence[str],
    environment_lock_path: str,
    bundle_name: str,
) -> dict[str, str | int]:
    """Build a map evidence ZIP from an explicit committed producer tree."""

    repo_root = repo_root.resolve()
    if _BUNDLE_NAME.fullmatch(bundle_name) is None or bundle_name.endswith(".zip"):
        raise ValueError("bundle_name must be a safe basename without .zip")
    if bundle_name.casefold() in _PROTECTED_HISTORICAL_BASENAMES:
        raise ValueError("bundle_name is a protected historical basename")
    output_dir = output_dir.resolve()
    output_zip = output_dir / f"{bundle_name}.zip"
    digest_path = output_zip.with_suffix(output_zip.suffix + ".sha256")
    if output_zip.exists() or digest_path.exists():
        raise FileExistsError("evidence builder refuses to overwrite an existing target")

    audited_base = _resolve_explicit_commit(
        repo_root,
        audited_base_commit,
        field="audited_base_commit",
    )
    producer = _resolve_explicit_commit(
        repo_root,
        producer_source_commit,
        field="producer_source_commit",
    )
    if audited_base == producer:
        raise ValueError("audited_base_commit and producer_source_commit must be distinct")
    if not _is_ancestor(repo_root, audited_base, producer):
        raise RuntimeError("producer_source_commit must descend from audited_base_commit")
    initial_state = _repository_state(repo_root)
    status = initial_state[2]
    if status:
        raise RuntimeError("working tree must be clean before evidence snapshot")
    if initial_state[0] != producer:
        raise RuntimeError("clean repository HEAD must equal producer_source_commit")

    environment_lock_path = _validate_payload_path(environment_lock_path)
    requested = tuple(_validate_payload_path(path) for path in payload_paths)
    if not requested:
        raise ValueError("payload_paths must contain at least one payload")
    if len(set(requested)) != len(requested):
        raise ValueError("payload_paths contains a duplicate path")

    all_payload_paths = tuple(sorted(set((*requested, environment_lock_path))))
    payloads = {path: _read_regular_blob(repo_root, producer, path) for path in all_payload_paths}
    try:
        environment = json.loads(payloads[environment_lock_path])
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("environment lock must be canonical UTF-8 JSON") from exc
    _validate_normalized_environment(environment)
    if payloads[environment_lock_path] != _canonical_json(environment):
        raise RuntimeError("environment lock JSON is not canonical")
    for path, content in payloads.items():
        if path != environment_lock_path:
            _reject_promoted_payload_claims(path, content)

    entries = [
        {
            "bytes": len(payloads[path]),
            "path": path,
            "sha256": hashlib.sha256(payloads[path]).hexdigest(),
        }
        for path in all_payload_paths
    ]
    manifest = {
        "audited_base_commit": audited_base,
        "claims": {
            "diagnostic_status": "IMPLEMENTED_DIAGNOSTIC",
            "historical_artifact_replay_status": "NOT_REPRODUCIBLY_CLOSED",
            "new_bundle_byte_replay_status": _IN_PROCESS_REPLAY_STATUS,
        },
        "environment_lock": {
            "path": environment_lock_path,
            "sha256": hashlib.sha256(payloads[environment_lock_path]).hexdigest(),
        },
        "integrity_boundary": {
            "detached_digest": f"{bundle_name}.zip.sha256",
            "excluded_members": [_MANIFEST_NAME],
            "manifest_scope": "payload_only",
        },
        "payloads": entries,
        "producer_source_commit": producer,
        "schema_version": "metroflow.map-evidence-manifest.v2",
    }
    members = {**payloads, _MANIFEST_NAME: _canonical_json(manifest)}

    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="metroflow-map-evidence-") as first_dir:
        first_zip = Path(first_dir) / output_zip.name
        _write_canonical_zip(first_zip, root_name=bundle_name, members=members)
        first_bytes = first_zip.read_bytes()
    with tempfile.TemporaryDirectory(prefix="metroflow-map-evidence-") as second_dir:
        second_zip = Path(second_dir) / output_zip.name
        _write_canonical_zip(second_zip, root_name=bundle_name, members=members)
        second_bytes = second_zip.read_bytes()
    if first_bytes != second_bytes:
        raise RuntimeError("in-process canonical serializations produced different ZIP bytes")
    if _repository_state(repo_root) != initial_state:
        raise RuntimeError("repository state changed during evidence build")
    digest = hashlib.sha256(first_bytes).hexdigest()
    sidecar_bytes = f"{digest}  {output_zip.name}\n".encode("ascii")
    with tempfile.NamedTemporaryFile(
        dir=output_dir,
        prefix=f".{bundle_name}.zip.tmp-",
        delete=False,
    ) as zip_stream:
        zip_stream.write(first_bytes)
        temporary_zip = Path(zip_stream.name)
    with tempfile.NamedTemporaryFile(
        dir=output_dir,
        prefix=f".{bundle_name}.zip.sha256.tmp-",
        delete=False,
    ) as sidecar_stream:
        sidecar_stream.write(sidecar_bytes)
        temporary_sidecar = Path(sidecar_stream.name)
    published_paths: list[Path] = []
    try:
        os.link(temporary_zip, output_zip)
        published_paths.append(output_zip)
        os.link(temporary_sidecar, digest_path)
        published_paths.append(digest_path)
        verify_map_evidence_bundle(output_zip, digest_path)
        if _repository_state(repo_root) != initial_state:
            raise RuntimeError("repository state changed during evidence publication")
    except Exception:
        for published in reversed(published_paths):
            published.unlink(missing_ok=True)
        raise
    finally:
        temporary_zip.unlink(missing_ok=True)
        temporary_sidecar.unlink(missing_ok=True)
    return {
        "bytes": len(first_bytes),
        "in_process_serialization_count": 2,
        "producer_source_commit": producer,
        "sha256": digest,
        "sha256_file": str(digest_path),
        "zip": str(output_zip),
    }


def write_independent_replay_receipt(
    *,
    first_zip: Path,
    first_digest: Path,
    second_zip: Path,
    second_digest: Path,
    receipt_path: Path,
) -> dict[str, str]:
    """Compare distinct bundle outputs and publish a separate replay receipt.

    The caller is responsible for producing the two inputs in independent clean
    checkout/process runs. This comparison never upgrades either embedded
    manifest's deliberately narrow in-process serialization status.
    """

    first_zip = first_zip.resolve()
    first_digest = first_digest.resolve()
    second_zip = second_zip.resolve()
    second_digest = second_digest.resolve()
    if os.path.samefile(first_zip, second_zip) or os.path.samefile(first_digest, second_digest):
        raise ValueError("independent replay inputs must be distinct files")
    receipt_path = receipt_path.resolve()
    if receipt_path.exists():
        raise FileExistsError("replay receipt writer refuses to overwrite an existing target")

    first_manifest = verify_map_evidence_bundle(first_zip, first_digest)
    second_manifest = verify_map_evidence_bundle(second_zip, second_digest)
    if first_zip.name != second_zip.name:
        raise RuntimeError("independent replay bundle filenames differ")
    first_zip_bytes = first_zip.read_bytes()
    second_zip_bytes = second_zip.read_bytes()
    if first_zip_bytes != second_zip_bytes:
        raise RuntimeError("independent replay ZIP bytes differ")
    if first_digest.read_bytes() != second_digest.read_bytes():
        raise RuntimeError("independent replay detached digest bytes differ")
    if first_manifest != second_manifest:
        raise RuntimeError("independent replay payload manifests differ")

    receipt = {
        "artifact_sha256": hashlib.sha256(first_zip_bytes).hexdigest(),
        "audited_base_commit": str(first_manifest["audited_base_commit"]),
        "bundle_filename": first_zip.name,
        "comparison_scope": "caller_supplied_distinct_build_outputs",
        "producer_source_commit": str(first_manifest["producer_source_commit"]),
        "replay_status": "INDEPENDENT_BUILD_BYTES_MATCH",
        "schema_version": "metroflow.map-evidence-independent-replay-receipt.v1",
    }
    receipt_bytes = _canonical_json(receipt)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=receipt_path.parent,
        prefix=f".{receipt_path.name}.tmp-",
        delete=False,
    ) as stream:
        stream.write(receipt_bytes)
        temporary_receipt = Path(stream.name)
    try:
        os.link(temporary_receipt, receipt_path)
    finally:
        temporary_receipt.unlink(missing_ok=True)
    return receipt


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--audited-base-commit", required=True)
    parser.add_argument("--producer-source-commit", required=True)
    parser.add_argument("--environment-lock-path", required=True)
    parser.add_argument("--bundle-name", required=True)
    parser.add_argument("--payload", action="append", dest="payload_paths", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    result = build_map_evidence_bundle(
        args.output_dir,
        repo_root=args.repo_root,
        audited_base_commit=args.audited_base_commit,
        producer_source_commit=args.producer_source_commit,
        payload_paths=args.payload_paths,
        environment_lock_path=args.environment_lock_path,
        bundle_name=args.bundle_name,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
