from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Callable
import zipfile

import pytest


def _git(repo: Path, *args: str, check: bool = True) -> str:
    process = subprocess.run(
        ("git", *args),
        cwd=repo,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return process.stdout.strip()


def _canonical_json(value: object) -> str:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )


def _create_fixture_repo(path: Path) -> tuple[Path, str, str]:
    path.mkdir()
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.name", "Map Evidence Fixture")
    _git(path, "config", "user.email", "map-evidence@example.invalid")

    (path / "environment-lock.json").write_text(
        _canonical_json(
            {
                "numpy": "2.4.1",
                "python": "3.12.12",
                "schema_version": "metroflow.normalized-environment.v1",
            }
        ),
        encoding="utf-8",
    )
    (path / "evidence.json").write_text(
        _canonical_json({"rows": [1], "schema_version": "fixture.v1"}),
        encoding="utf-8",
    )
    _git(path, "add", ".")
    _git(path, "commit", "-m", "audited base")
    audited_base = _git(path, "rev-parse", "HEAD")

    (path / "evidence.json").write_text(
        _canonical_json({"rows": [1, 2], "schema_version": "fixture.v1"}),
        encoding="utf-8",
    )
    _git(path, "add", "evidence.json")
    _git(path, "commit", "-m", "producer source")
    producer = _git(path, "rev-parse", "HEAD")
    return path, audited_base, producer


def _rewrite_bundle(
    zip_path: Path,
    sidecar: Path,
    mutate: Callable[[dict[str, bytes], str], None],
) -> None:
    with zipfile.ZipFile(zip_path) as archive:
        members = {info.filename: archive.read(info) for info in archive.infolist()}
    manifest_name = f"{zip_path.stem}/PAYLOAD_MANIFEST.json"
    mutate(members, manifest_name)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = (0o100644 & 0xFFFF) << 16
            archive.writestr(info, members[name])
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sidecar.write_text(f"{digest}  {zip_path.name}\n", encoding="ascii")


@pytest.mark.parametrize(
    ("base_selector", "producer_selector", "message"),
    (
        ("missing", "producer", "audited_base_commit must be a full commit id"),
        ("base", "missing", "producer_source_commit must be a full commit id"),
        ("base", "base", "must be distinct"),
        ("zero", "producer", "audited_base_commit does not resolve"),
    ),
)
def test_rejects_missing_equal_or_unresolvable_base_and_producer_commits(
    tmp_path: Path,
    base_selector: str,
    producer_selector: str,
    message: str,
) -> None:
    from tools.build_map_evidence_bundle import build_map_evidence_bundle

    repo, audited_base, producer = _create_fixture_repo(tmp_path / "repo")
    choices = {
        "base": audited_base,
        "producer": producer,
        "missing": "",
        "zero": "0" * 40,
    }

    with pytest.raises((RuntimeError, ValueError), match=message):
        build_map_evidence_bundle(
            tmp_path / "output",
            repo_root=repo,
            audited_base_commit=choices[base_selector],
            producer_source_commit=choices[producer_selector],
            payload_paths=("evidence.json",),
            environment_lock_path="environment-lock.json",
            bundle_name="fixture-map-evidence-v2",
        )


def test_rejects_dirty_worktree_before_snapshot(tmp_path: Path) -> None:
    from tools.build_map_evidence_bundle import build_map_evidence_bundle

    repo, audited_base, producer = _create_fixture_repo(tmp_path / "repo")
    (repo / "evidence.json").write_text("dirty bytes\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="working tree must be clean"):
        build_map_evidence_bundle(
            tmp_path / "output",
            repo_root=repo,
            audited_base_commit=audited_base,
            producer_source_commit=producer,
            payload_paths=("evidence.json",),
            environment_lock_path="environment-lock.json",
            bundle_name="fixture-map-evidence-v2",
        )


def test_rejects_producer_that_is_not_a_descendant_of_audited_base(
    tmp_path: Path,
) -> None:
    from tools.build_map_evidence_bundle import build_map_evidence_bundle

    repo, audited_base, _ = _create_fixture_repo(tmp_path / "repo")
    _git(repo, "switch", "--orphan", "unrelated")
    for path in repo.iterdir():
        if path.name != ".git" and path.is_file():
            path.unlink()
    (repo / "environment-lock.json").write_text(
        _canonical_json({"schema_version": "metroflow.normalized-environment.v1"}),
        encoding="utf-8",
    )
    (repo / "evidence.json").write_text("unrelated\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "unrelated producer")
    producer = _git(repo, "rev-parse", "HEAD")

    with pytest.raises(RuntimeError, match="must descend from audited_base_commit"):
        build_map_evidence_bundle(
            tmp_path / "output",
            repo_root=repo,
            audited_base_commit=audited_base,
            producer_source_commit=producer,
            payload_paths=("evidence.json",),
            environment_lock_path="environment-lock.json",
            bundle_name="fixture-map-evidence-v2",
        )


def test_payload_manifest_excludes_itself_and_covers_every_payload_exactly_once(
    tmp_path: Path,
) -> None:
    from tools.build_map_evidence_bundle import build_map_evidence_bundle

    repo, audited_base, producer = _create_fixture_repo(tmp_path / "repo")
    result = build_map_evidence_bundle(
        tmp_path / "output",
        repo_root=repo,
        audited_base_commit=audited_base,
        producer_source_commit=producer,
        payload_paths=("evidence.json",),
        environment_lock_path="environment-lock.json",
        bundle_name="fixture-map-evidence-v2",
    )

    zip_path = Path(result["zip"])
    with zipfile.ZipFile(zip_path) as archive:
        names = [info.filename for info in archive.infolist() if not info.is_dir()]
        prefix = "fixture-map-evidence-v2/"
        assert names == sorted(names)
        assert names == [
            f"{prefix}PAYLOAD_MANIFEST.json",
            f"{prefix}environment-lock.json",
            f"{prefix}evidence.json",
        ]
        manifest = json.loads(archive.read(f"{prefix}PAYLOAD_MANIFEST.json"))
        assert manifest["schema_version"] == "metroflow.map-evidence-manifest.v2"
        assert manifest["audited_base_commit"] == audited_base
        assert manifest["producer_source_commit"] == producer
        assert manifest["integrity_boundary"] == {
            "detached_digest": "fixture-map-evidence-v2.zip.sha256",
            "excluded_members": ["PAYLOAD_MANIFEST.json"],
            "manifest_scope": "payload_only",
        }
        assert manifest["claims"] == {
            "diagnostic_status": "IMPLEMENTED_DIAGNOSTIC",
            "historical_artifact_replay_status": "NOT_REPRODUCIBLY_CLOSED",
            "new_bundle_byte_replay_status": "IN_PROCESS_SERIALIZATION_MATCH_ONLY",
        }
        entries = manifest["payloads"]
        assert [entry["path"] for entry in entries] == [
            "environment-lock.json",
            "evidence.json",
        ]
        assert len({entry["path"] for entry in entries}) == len(entries)
        for entry in entries:
            content = archive.read(f"{prefix}{entry['path']}")
            assert entry["bytes"] == len(content)
            assert entry["sha256"] == hashlib.sha256(content).hexdigest()
        assert (
            archive.read(f"{prefix}evidence.json")
            == _git(repo, "show", f"{producer}:evidence.json").encode() + b"\n"
        )
        assert not any(name.endswith(".sha256") for name in names)
        assert not any("SHA256SUMS" in name for name in names)


def test_single_build_reports_only_its_in_process_serialization_check(
    tmp_path: Path,
) -> None:
    from tools.build_map_evidence_bundle import build_map_evidence_bundle

    repo, audited_base, producer = _create_fixture_repo(tmp_path / "repo")
    arguments = {
        "repo_root": repo,
        "audited_base_commit": audited_base,
        "producer_source_commit": producer,
        "payload_paths": ("evidence.json",),
        "environment_lock_path": "environment-lock.json",
        "bundle_name": "fixture-map-evidence-v2",
    }
    first = build_map_evidence_bundle(tmp_path / "first", **arguments)
    second = build_map_evidence_bundle(tmp_path / "second", **arguments)

    first_zip = Path(first["zip"])
    second_zip = Path(second["zip"])
    first_sidecar = Path(first["sha256_file"])
    second_sidecar = Path(second["sha256_file"])
    assert first_zip.read_bytes() == second_zip.read_bytes()
    assert first_sidecar.read_bytes() == second_sidecar.read_bytes()
    digest = hashlib.sha256(first_zip.read_bytes()).hexdigest()
    assert first_sidecar.read_bytes() == (
        f"{digest}  fixture-map-evidence-v2.zip\n".encode("ascii")
    )
    assert first["in_process_serialization_count"] == 2
    assert "canonical_build_count" not in first

    with zipfile.ZipFile(first_zip) as archive:
        for info in archive.infolist():
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            assert info.compress_type == zipfile.ZIP_STORED
            assert info.create_system == 3
            assert (info.external_attr >> 16) & 0o777 == 0o644


def test_independent_replay_promotion_requires_a_separate_receipt(
    tmp_path: Path,
) -> None:
    from tools.build_map_evidence_bundle import write_independent_replay_receipt

    repo, audited_base, producer = _create_fixture_repo(tmp_path / "repo")
    checkouts = (tmp_path / "checkout-a", tmp_path / "checkout-b")
    outputs = (tmp_path / "independent-a", tmp_path / "independent-b")
    builder = Path("tools/build_map_evidence_bundle.py").resolve()
    for checkout, output in zip(checkouts, outputs, strict=True):
        subprocess.run(
            ("git", "clone", "--quiet", str(repo), str(checkout)),
            check=True,
        )
        subprocess.run(
            (
                sys.executable,
                str(builder),
                "--output-dir",
                str(output),
                "--repo-root",
                str(checkout),
                "--audited-base-commit",
                audited_base,
                "--producer-source-commit",
                producer,
                "--environment-lock-path",
                "environment-lock.json",
                "--bundle-name",
                "fixture-map-evidence-v2",
                "--payload",
                "evidence.json",
            ),
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    first_zip = outputs[0] / "fixture-map-evidence-v2.zip"
    first_digest = outputs[0] / "fixture-map-evidence-v2.zip.sha256"
    second_zip = outputs[1] / "fixture-map-evidence-v2.zip"
    second_digest = outputs[1] / "fixture-map-evidence-v2.zip.sha256"
    receipt_path = tmp_path / "receipts" / "fixture-map-evidence-v2.replay.json"

    receipt = write_independent_replay_receipt(
        first_zip=first_zip,
        first_digest=first_digest,
        second_zip=second_zip,
        second_digest=second_digest,
        receipt_path=receipt_path,
    )

    assert receipt_path.read_bytes() == _canonical_json(receipt).encode("utf-8")
    assert receipt == {
        "artifact_sha256": hashlib.sha256(first_zip.read_bytes()).hexdigest(),
        "audited_base_commit": audited_base,
        "bundle_filename": "fixture-map-evidence-v2.zip",
        "comparison_scope": "caller_supplied_distinct_build_outputs",
        "producer_source_commit": producer,
        "replay_status": "INDEPENDENT_BUILD_BYTES_MATCH",
        "schema_version": "metroflow.map-evidence-independent-replay-receipt.v1",
    }
    with pytest.raises(FileExistsError, match="refuses to overwrite"):
        write_independent_replay_receipt(
            first_zip=first_zip,
            first_digest=first_digest,
            second_zip=second_zip,
            second_digest=second_digest,
            receipt_path=receipt_path,
        )


def test_detached_digest_is_not_a_zip_member_and_detects_zip_tampering(
    tmp_path: Path,
) -> None:
    from tools.build_map_evidence_bundle import (
        build_map_evidence_bundle,
        verify_map_evidence_bundle,
    )

    repo, audited_base, producer = _create_fixture_repo(tmp_path / "repo")
    result = build_map_evidence_bundle(
        tmp_path / "output",
        repo_root=repo,
        audited_base_commit=audited_base,
        producer_source_commit=producer,
        payload_paths=("evidence.json",),
        environment_lock_path="environment-lock.json",
        bundle_name="fixture-map-evidence-v2",
    )
    zip_path = Path(result["zip"])
    sidecar = Path(result["sha256_file"])

    verified = verify_map_evidence_bundle(zip_path, sidecar)
    assert verified["producer_source_commit"] == producer
    with zipfile.ZipFile(zip_path) as archive:
        assert sidecar.name not in archive.namelist()

    zip_path.write_bytes(zip_path.read_bytes() + b"tamper")
    with pytest.raises(RuntimeError, match="detached ZIP digest mismatch"):
        verify_map_evidence_bundle(zip_path, sidecar)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("missing", "does not cover every payload member"),
        ("duplicate", "duplicate payload manifest entry"),
        ("unsafe", "unsafe or noncanonical payload path"),
        ("metadata", "payload manifest metadata mismatch"),
        ("provenance", "audited base and producer source commits must be distinct"),
        ("environment", "host-dependent field"),
    ),
)
def test_manifest_tamper_missing_path_duplicate_path_and_unsafe_path_fail_closed(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    from tools.build_map_evidence_bundle import (
        build_map_evidence_bundle,
        verify_map_evidence_bundle,
    )

    repo, audited_base, producer = _create_fixture_repo(tmp_path / "repo")
    result = build_map_evidence_bundle(
        tmp_path / "output",
        repo_root=repo,
        audited_base_commit=audited_base,
        producer_source_commit=producer,
        payload_paths=("evidence.json",),
        environment_lock_path="environment-lock.json",
        bundle_name="fixture-map-evidence-v2",
    )
    zip_path = Path(result["zip"])
    sidecar = Path(result["sha256_file"])

    def mutate(members: dict[str, bytes], manifest_name: str) -> None:
        manifest = json.loads(members[manifest_name])
        if mutation == "missing":
            manifest["payloads"].pop()
        elif mutation == "duplicate":
            manifest["payloads"].append(dict(manifest["payloads"][0]))
        elif mutation == "unsafe":
            manifest["payloads"][0]["path"] = "../escape"
        elif mutation == "metadata":
            members[f"{zip_path.stem}/evidence.json"] += b"tamper"
        elif mutation == "provenance":
            manifest["producer_source_commit"] = manifest["audited_base_commit"]
        elif mutation == "environment":
            lock_name = f"{zip_path.stem}/environment-lock.json"
            environment = json.loads(members[lock_name])
            environment["captured_at_utc"] = "2026-08-09T00:00:00Z"
            lock_bytes = _canonical_json(environment).encode("utf-8")
            members[lock_name] = lock_bytes
            for entry in manifest["payloads"]:
                if entry["path"] == "environment-lock.json":
                    entry["bytes"] = len(lock_bytes)
                    entry["sha256"] = hashlib.sha256(lock_bytes).hexdigest()
            manifest["environment_lock"]["sha256"] = hashlib.sha256(lock_bytes).hexdigest()
        members[manifest_name] = _canonical_json(manifest).encode("utf-8")

    _rewrite_bundle(zip_path, sidecar, mutate)
    with pytest.raises(RuntimeError, match=message):
        verify_map_evidence_bundle(zip_path, sidecar)


def test_verifier_rejects_a_fully_resealed_payload_claim_promotion(
    tmp_path: Path,
) -> None:
    from tools.build_map_evidence_bundle import (
        build_map_evidence_bundle,
        verify_map_evidence_bundle,
    )

    repo, audited_base, producer = _create_fixture_repo(tmp_path / "repo")
    result = build_map_evidence_bundle(
        tmp_path / "output",
        repo_root=repo,
        audited_base_commit=audited_base,
        producer_source_commit=producer,
        payload_paths=("evidence.json",),
        environment_lock_path="environment-lock.json",
        bundle_name="fixture-map-evidence-v2",
    )
    zip_path = Path(result["zip"])
    sidecar = Path(result["sha256_file"])

    def promote(members: dict[str, bytes], manifest_name: str) -> None:
        manifest = json.loads(members[manifest_name])
        evidence_name = f"{zip_path.stem}/evidence.json"
        evidence = json.loads(members[evidence_name])
        evidence["evidence_status"] = "VALIDATED"
        evidence["historical_artifact_replay_status"] = "REPRODUCIBLY_CLOSED"
        evidence_bytes = _canonical_json(evidence).encode("utf-8")
        members[evidence_name] = evidence_bytes
        for entry in manifest["payloads"]:
            if entry["path"] == "evidence.json":
                entry["bytes"] = len(evidence_bytes)
                entry["sha256"] = hashlib.sha256(evidence_bytes).hexdigest()
        members[manifest_name] = _canonical_json(manifest).encode("utf-8")

    _rewrite_bundle(zip_path, sidecar, promote)
    with pytest.raises(RuntimeError, match="payload claim status conflicts"):
        verify_map_evidence_bundle(zip_path, sidecar)


@pytest.mark.parametrize(
    "wrapper_path",
    (
        "SHA256SUMS.txt",
        "sha256sums.TXT",
        "audit/Sha256Sums.txt",
        "SHA256SUMS.txt/evidence.json",
        "audit/payload.SHA256",
    ),
)
def test_integrity_wrapper_case_and_path_variants_cannot_be_payloads(
    tmp_path: Path,
    wrapper_path: str,
) -> None:
    from tools.build_map_evidence_bundle import build_map_evidence_bundle

    repo, audited_base, _ = _create_fixture_repo(tmp_path / "repo")
    wrapper = repo / wrapper_path
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text("not a payload\n", encoding="utf-8")
    _git(repo, "add", wrapper_path)
    _git(repo, "commit", "-m", "add forbidden integrity wrapper")
    producer = _git(repo, "rev-parse", "HEAD")

    with pytest.raises(ValueError, match="integrity wrapper cannot be a payload"):
        build_map_evidence_bundle(
            tmp_path / "output",
            repo_root=repo,
            audited_base_commit=audited_base,
            producer_source_commit=producer,
            payload_paths=(wrapper_path,),
            environment_lock_path="environment-lock.json",
            bundle_name="fixture-map-evidence-v2",
        )


@pytest.mark.parametrize("existing", ("zip", "sidecar", "both"))
def test_existing_output_targets_are_strict_no_clobber(
    tmp_path: Path,
    existing: str,
) -> None:
    from tools.build_map_evidence_bundle import build_map_evidence_bundle

    repo, audited_base, producer = _create_fixture_repo(tmp_path / "repo")
    output = tmp_path / "output"
    output.mkdir()
    zip_path = output / "fixture-map-evidence-v2.zip"
    sidecar = output / "fixture-map-evidence-v2.zip.sha256"
    if existing in {"zip", "both"}:
        zip_path.write_bytes(b"protected existing zip")
    if existing in {"sidecar", "both"}:
        sidecar.write_bytes(b"protected existing sidecar")
    before = {path: path.read_bytes() for path in (zip_path, sidecar) if path.exists()}

    with pytest.raises(FileExistsError, match="refuses to overwrite"):
        build_map_evidence_bundle(
            output,
            repo_root=repo,
            audited_base_commit=audited_base,
            producer_source_commit=producer,
            payload_paths=("evidence.json",),
            environment_lock_path="environment-lock.json",
            bundle_name="fixture-map-evidence-v2",
        )

    assert {path: path.read_bytes() for path in before} == before
    assert not list(output.glob(".*.tmp-*"))


@pytest.mark.parametrize(
    "protected_name",
    (
        "MetroFlow_map_generation_reaudit_2026-08-08",
        "MetroFlow_CAPR_research_2026-08-08",
        "morphology-null-operator-control-20260808",
    ),
)
def test_protected_historical_basenames_are_never_publication_targets(
    tmp_path: Path,
    protected_name: str,
) -> None:
    from tools.build_map_evidence_bundle import build_map_evidence_bundle

    repo, audited_base, producer = _create_fixture_repo(tmp_path / "repo")
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="protected historical basename"):
        build_map_evidence_bundle(
            output,
            repo_root=repo,
            audited_base_commit=audited_base,
            producer_source_commit=producer,
            payload_paths=("evidence.json",),
            environment_lock_path="environment-lock.json",
            bundle_name=protected_name,
        )
    assert not output.exists() or not tuple(output.iterdir())


def test_new_publication_failure_removes_zip_sidecar_and_temporaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tools.build_map_evidence_bundle as builder

    repo, audited_base, producer = _create_fixture_repo(tmp_path / "repo")
    output = tmp_path / "output"
    output.mkdir()
    zip_path = output / "fixture-map-evidence-v2.zip"
    sidecar = output / "fixture-map-evidence-v2.zip.sha256"

    def fail_verification(zip_file: Path, digest_file: Path) -> dict[str, object]:
        assert zip_file == zip_path
        assert digest_file == sidecar
        raise RuntimeError("injected post-publish verification failure")

    monkeypatch.setattr(builder, "verify_map_evidence_bundle", fail_verification)
    with pytest.raises(RuntimeError, match="post-publish verification failure"):
        builder.build_map_evidence_bundle(
            output,
            repo_root=repo,
            audited_base_commit=audited_base,
            producer_source_commit=producer,
            payload_paths=("evidence.json",),
            environment_lock_path="environment-lock.json",
            bundle_name="fixture-map-evidence-v2",
        )

    assert not zip_path.exists()
    assert not sidecar.exists()
    assert not list(output.glob(".*.tmp-*"))


def test_normalized_environment_rejects_host_dependent_capture_fields(
    tmp_path: Path,
) -> None:
    from tools.build_map_evidence_bundle import build_map_evidence_bundle

    repo, audited_base, _ = _create_fixture_repo(tmp_path / "repo")
    (repo / "environment-lock.json").write_text(
        _canonical_json(
            {
                "captured_at_utc": "2026-08-09T00:00:00Z",
                "numpy": "2.4.1",
                "python": "3.12.12",
                "schema_version": "metroflow.normalized-environment.v1",
            }
        ),
        encoding="utf-8",
    )
    _git(repo, "add", "environment-lock.json")
    _git(repo, "commit", "-m", "add host-dependent environment capture")
    producer = _git(repo, "rev-parse", "HEAD")

    with pytest.raises(RuntimeError, match="host-dependent field"):
        build_map_evidence_bundle(
            tmp_path / "output",
            repo_root=repo,
            audited_base_commit=audited_base,
            producer_source_commit=producer,
            payload_paths=("evidence.json",),
            environment_lock_path="environment-lock.json",
            bundle_name="fixture-map-evidence-v2",
        )


@pytest.mark.parametrize(
    "environment",
    (
        {
            "python": "3.12.12",
            "schema_version": "metroflow.normalized-environment.v1",
        },
        {
            "numpy": ">=2.0",
            "python": ">=3.12",
            "schema_version": "metroflow.normalized-environment.v1",
        },
    ),
)
def test_normalized_environment_requires_exact_python_and_numpy_versions(
    tmp_path: Path,
    environment: dict[str, str],
) -> None:
    from tools.build_map_evidence_bundle import build_map_evidence_bundle

    repo, audited_base, _ = _create_fixture_repo(tmp_path / "repo")
    (repo / "environment-lock.json").write_text(
        _canonical_json(environment),
        encoding="utf-8",
    )
    _git(repo, "add", "environment-lock.json")
    _git(repo, "commit", "-m", "add incomplete environment lock")
    producer = _git(repo, "rev-parse", "HEAD")

    with pytest.raises(RuntimeError, match="exact Python 3.12 and NumPy versions"):
        build_map_evidence_bundle(
            tmp_path / "output",
            repo_root=repo,
            audited_base_commit=audited_base,
            producer_source_commit=producer,
            payload_paths=("evidence.json",),
            environment_lock_path="environment-lock.json",
            bundle_name="fixture-map-evidence-v2",
        )


def test_claim_status_cannot_promote_diagnostic_or_unclosed_replay(
    tmp_path: Path,
) -> None:
    from tools.build_map_evidence_bundle import build_map_evidence_bundle

    repo, audited_base, _ = _create_fixture_repo(tmp_path / "repo")
    (repo / "evidence.json").write_text(
        _canonical_json(
            {
                "evidence_status": "VALIDATED",
                "historical_artifact_replay_status": "REPRODUCIBLY_CLOSED",
                "rows": [1, 2],
                "schema_version": "fixture.v1",
            }
        ),
        encoding="utf-8",
    )
    _git(repo, "add", "evidence.json")
    _git(repo, "commit", "-m", "attempt claim promotion")
    producer = _git(repo, "rev-parse", "HEAD")

    with pytest.raises(RuntimeError, match="payload claim status conflicts"):
        build_map_evidence_bundle(
            tmp_path / "output",
            repo_root=repo,
            audited_base_commit=audited_base,
            producer_source_commit=producer,
            payload_paths=("evidence.json",),
            environment_lock_path="environment-lock.json",
            bundle_name="fixture-map-evidence-v2",
        )


def test_repository_state_drift_during_build_fails_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tools.build_map_evidence_bundle as builder

    repo, audited_base, producer = _create_fixture_repo(tmp_path / "repo")
    output = tmp_path / "output"
    real_write_zip = builder._write_canonical_zip
    call_count = 0

    def inject_tree_drift(
        path: Path,
        *,
        root_name: str,
        members: dict[str, bytes],
    ) -> None:
        nonlocal call_count
        real_write_zip(path, root_name=root_name, members=members)
        call_count += 1
        if call_count == 1:
            (repo / "DRIFT").write_text("changed during build\n", encoding="utf-8")

    monkeypatch.setattr(builder, "_write_canonical_zip", inject_tree_drift)
    with pytest.raises(RuntimeError, match="repository state changed during evidence build"):
        builder.build_map_evidence_bundle(
            output,
            repo_root=repo,
            audited_base_commit=audited_base,
            producer_source_commit=producer,
            payload_paths=("evidence.json",),
            environment_lock_path="environment-lock.json",
            bundle_name="fixture-map-evidence-v2",
        )

    assert not (output / "fixture-map-evidence-v2.zip").exists()
    assert not (output / "fixture-map-evidence-v2.zip.sha256").exists()


def test_verifier_rejects_noncanonical_zip_metadata_with_a_matching_digest(
    tmp_path: Path,
) -> None:
    from tools.build_map_evidence_bundle import (
        build_map_evidence_bundle,
        verify_map_evidence_bundle,
    )

    repo, audited_base, producer = _create_fixture_repo(tmp_path / "repo")
    result = build_map_evidence_bundle(
        tmp_path / "output",
        repo_root=repo,
        audited_base_commit=audited_base,
        producer_source_commit=producer,
        payload_paths=("evidence.json",),
        environment_lock_path="environment-lock.json",
        bundle_name="fixture-map-evidence-v2",
    )
    zip_path = Path(result["zip"])
    sidecar = Path(result["sha256_file"])
    with zipfile.ZipFile(zip_path) as archive:
        members = {info.filename: archive.read(info) for info in archive.infolist()}
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(members):
            archive.writestr(name, members[name])
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sidecar.write_text(f"{digest}  {zip_path.name}\n", encoding="ascii")

    with pytest.raises(RuntimeError, match="noncanonical ZIP member metadata"):
        verify_map_evidence_bundle(zip_path, sidecar)
