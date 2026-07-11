from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from metroflow.benchmarks.runtime_self_drive_probe import run_runtime_self_drive_probe
import tools.build_external_audit_bundle as audit_builder
from tools.build_external_audit_bundle import build_bundle


ROOT = Path(__file__).resolve().parents[1]
AUDIT_ROOT = ROOT / "docs" / "audit" / "metroflow_external_audit_20260711"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ("git", *args),
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ).stdout.strip()


def _create_audit_fixture_repo(path: Path) -> Path:
    path.mkdir()
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.name", "Audit Fixture")
    _git(path, "config", "user.email", "audit@example.invalid")
    audit = path / "docs" / "audit" / "packet"
    audit.mkdir(parents=True)
    (audit / "README.md").write_text("# Fixture audit\n", encoding="utf-8")
    (audit / "NO_LICENSE_NOTICE.md").write_text("# No license\n", encoding="utf-8")
    (path / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "fixture audit")
    return path


def test_external_audit_packet_has_required_documents_and_claim_boundaries() -> None:
    required = {
        "README.md",
        "01_ORIGIN_AND_RESEARCH_MOTIVATION.md",
        "02_DEVELOPMENT_HISTORY.md",
        "03_ARCHITECTURE_AND_ALGORITHMS.md",
        "04_EXPERIMENTS_FAILURES_AND_RESULTS.md",
        "05_ADVERSARIAL_TECHNICAL_AUDIT.md",
        "06_CLAIM_PROVENANCE.md",
        "07_REPRODUCTION_AND_EXTERNAL_REVIEW.md",
        "08_SOURCE_AND_ARTIFACT_INDEX.md",
        "09_REVIEW_CLOSURE.md",
        "NO_LICENSE_NOTICE.md",
        "evidence_snapshot.json",
    }
    assert required == {path.name for path in AUDIT_ROOT.iterdir() if path.is_file()}

    entrypoint = (AUDIT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "not yet a validated 100k-city traffic simulator" in entrypoint
    assert "turn demand" in entrypoint
    assert "no root license" in entrypoint


def test_external_audit_evidence_snapshot_is_fail_closed() -> None:
    payload = json.loads((AUDIT_ROOT / "evidence_snapshot.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "metroflow.external-audit-evidence.v1"
    assert payload["source_baseline_commit"] == (
        "96e54ca907babe6425212ac2e088615687549d72"
    )
    assert payload["functional_probe"]["tick_1_to_3_moved_agents"] == 0
    assert payload["experiments"]["jax_graph_cost_to_go"]["seed_gate_pass_count"] == 0
    assert "no root redistribution license" in payload["claim_limits"]


def test_external_audit_runtime_self_drive_probe_reproduces_stall() -> None:
    result = run_runtime_self_drive_probe(scenario_seed=41, steps=3)

    assert result["runtime_closure_blocker_reproduced"] is True
    assert result["initial"] == {
        "trip_count": 16,
        "turn_demand_total": 0.0,
        "queue_vehicles_total": 0.0,
    }
    assert [row["active_agent_count"] for row in result["ticks"]] == [15, 15, 15]
    assert [row["moved_agent_count"] for row in result["ticks"]] == [0, 0, 0]
    assert [row["queue_vehicles_total"] for row in result["ticks"]] == [15.0, 15.0, 15.0]


def test_external_audit_builder_uses_only_standard_library_imports() -> None:
    builder = ROOT / "tools" / "build_external_audit_bundle.py"
    tree = ast.parse(builder.read_text(encoding="utf-8"))
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
    assert imported_roots <= (set(sys.stdlib_module_names) | {"__future__"})


def test_external_audit_builder_creates_closed_integrity_package(tmp_path: Path) -> None:
    repo = _create_audit_fixture_repo(tmp_path / "repo")
    output = tmp_path / "output"
    result = build_bundle(
        output,
        audit_date="2026-07-11",
        allow_dirty=False,
        repo_root=repo,
        audit_relative=Path("docs/audit/packet"),
    )

    zip_path = Path(result["zip"])
    sidecar = Path(result["sha256_file"])
    assert zip_path.is_file()
    assert sidecar.read_text(encoding="utf-8").split()[0] == hashlib.sha256(
        zip_path.read_bytes()
    ).hexdigest()

    with zipfile.ZipFile(zip_path) as archive:
        names = {info.filename for info in archive.infolist() if not info.is_dir()}
        package_name = zip_path.stem
        prefix = f"{package_name}/"
        assert all(name.startswith(prefix) and ".." not in Path(name).parts for name in names)
        metadata = json.loads(archive.read(f"{prefix}provenance/package_metadata.json"))
        manifest = json.loads(archive.read(f"{prefix}MANIFEST.json"))
        assert metadata["packaged_commit"] == _git(repo, "rev-parse", "HEAD")
        assert manifest["entry_exclusions"] == ["MANIFEST.json", "SHA256SUMS"]
        manifest_entries = {entry["path"]: entry for entry in manifest["entries"]}
        expected_manifest_paths = {
            name.removeprefix(prefix)
            for name in names
            if name not in {f"{prefix}MANIFEST.json", f"{prefix}SHA256SUMS"}
        }
        assert set(manifest_entries) == expected_manifest_paths
        for relative, entry in manifest_entries.items():
            content = archive.read(f"{prefix}{relative}")
            assert entry["bytes"] == len(content)
            assert entry["sha256"] == hashlib.sha256(content).hexdigest()
        checksums = archive.read(f"{prefix}SHA256SUMS").decode("utf-8").splitlines()
        listed = set()
        for line in checksums:
            digest, relative = line.split("  ", 1)
            member = f"{prefix}{relative}"
            assert hashlib.sha256(archive.read(member)).hexdigest() == digest
            listed.add(member)
        assert listed == names - {f"{prefix}SHA256SUMS"}
        assert f"{prefix}history/metroflow-all-refs.bundle" in names
        bundle_bytes = archive.read(f"{prefix}history/metroflow-all-refs.bundle")

    bundle_path = tmp_path / "round-trip.bundle"
    bundle_path.write_bytes(bundle_bytes)
    bundle_heads = subprocess.run(
        ("git", "bundle", "list-heads", str(bundle_path)),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ).stdout
    assert metadata["packaged_commit"] in bundle_heads
    clone = tmp_path / "bundle-clone"
    subprocess.run(
        ("git", "clone", str(bundle_path), str(clone)),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert _git(clone, "rev-parse", "HEAD") == metadata["packaged_commit"]


def test_external_audit_builder_rejects_dirty_shallow_and_invalid_date(
    tmp_path: Path,
) -> None:
    repo = _create_audit_fixture_repo(tmp_path / "repo")
    (repo / "README.md").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="working tree is dirty"):
        build_bundle(
            tmp_path / "dirty-output",
            audit_date="2026-07-11",
            allow_dirty=False,
            repo_root=repo,
            audit_relative=Path("docs/audit/packet"),
        )
    with pytest.raises(ValueError, match="canonical YYYY-MM-DD"):
        build_bundle(
            tmp_path / "escape-output",
            audit_date="/../../escaped",
            allow_dirty=True,
            repo_root=repo,
            audit_relative=Path("docs/audit/packet"),
        )

    symlink_repo = _create_audit_fixture_repo(tmp_path / "symlink-repo")
    (symlink_repo / "target.txt").write_text("target\n", encoding="utf-8")
    (symlink_repo / "link.txt").symlink_to("target.txt")
    _git(symlink_repo, "add", "-A")
    _git(symlink_repo, "commit", "-m", "add tracked symlink")
    with pytest.raises(RuntimeError, match="tracked symlinks"):
        build_bundle(
            tmp_path / "symlink-output",
            audit_date="2026-07-11",
            allow_dirty=False,
            repo_root=symlink_repo,
            audit_relative=Path("docs/audit/packet"),
        )

    _git(repo, "restore", "README.md")
    (repo / "bad\nname").write_text("unsafe checksum path\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "add unsafe path")
    with pytest.raises(RuntimeError, match="contain no newline"):
        build_bundle(
            tmp_path / "unsafe-path-output",
            audit_date="2026-07-11",
            allow_dirty=False,
            repo_root=repo,
            audit_relative=Path("docs/audit/packet"),
        )

    (repo / "SECOND").write_text("second\n", encoding="utf-8")
    _git(repo, "add", "SECOND")
    _git(repo, "commit", "-m", "second fixture commit")
    shallow = tmp_path / "shallow"
    subprocess.run(
        ("git", "clone", "--depth", "1", repo.as_uri(), str(shallow)),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    with pytest.raises(RuntimeError, match="shallow repository"):
        build_bundle(
            tmp_path / "shallow-output",
            audit_date="2026-07-11",
            allow_dirty=False,
            repo_root=shallow,
            audit_relative=Path("docs/audit/packet"),
        )


def test_external_audit_builder_rejects_transient_bundle_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _create_audit_fixture_repo(tmp_path / "repo")
    real_run = audit_builder._run

    def inject_transient_ref(
        args: tuple[str, ...],
        *,
        cwd: Path,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        result = real_run(args, cwd=cwd, check=check)
        if tuple(args[:3]) == ("git", "bundle", "list-heads"):
            return subprocess.CompletedProcess(
                args,
                0,
                result.stdout + f"{'0' * 40} refs/heads/transient\n",
                "",
            )
        return result

    monkeypatch.setattr(audit_builder, "_run", inject_transient_ref)
    with pytest.raises(RuntimeError, match="bundle refs do not match"):
        build_bundle(
            tmp_path / "output",
            audit_date="2026-07-11",
            allow_dirty=False,
            repo_root=repo,
            audit_relative=Path("docs/audit/packet"),
        )


def test_external_audit_builder_removes_stale_sidecar_before_publish_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _create_audit_fixture_repo(tmp_path / "repo")
    output = tmp_path / "output"
    output.mkdir()
    commit = _git(repo, "rev-parse", "HEAD")
    package_name = f"metroflow_external_audit_20260711_{commit[:12]}"
    output_zip = output / f"{package_name}.zip"
    sidecar = output / f"{package_name}.zip.sha256"
    output_zip.write_bytes(b"old zip")
    sidecar.write_text("stale digest\n", encoding="utf-8")

    real_replace = audit_builder.os.replace
    replace_count = 0

    def fail_sidecar_replace(source: Path, destination: Path) -> None:
        nonlocal replace_count
        replace_count += 1
        if replace_count == 2:
            raise OSError("injected sidecar publish failure")
        real_replace(source, destination)

    monkeypatch.setattr(audit_builder.os, "replace", fail_sidecar_replace)
    with pytest.raises(OSError, match="sidecar publish failure"):
        build_bundle(
            output,
            audit_date="2026-07-11",
            allow_dirty=False,
            repo_root=repo,
            audit_relative=Path("docs/audit/packet"),
        )

    assert output_zip.read_bytes() != b"old zip"
    assert not sidecar.exists()
    with zipfile.ZipFile(output_zip) as archive:
        assert archive.testzip() is None
