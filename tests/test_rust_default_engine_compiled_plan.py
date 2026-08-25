from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_json(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_compiled_plan_validates_against_current_repository() -> None:
    module = _load_module(
        "validate_rust_default_engine_plan",
        ROOT / "tools/validate_rust_default_engine_plan.py",
    )
    summary = module.validate_plan(ROOT)
    assert summary == {
        "pr_count": 16,
        "invariant_count": 30,
        "failure_mode_count": 50,
        "existing_map_nodes": 11,
        "existing_map_edges": 10,
        "rust_edges": 16,
    }


def test_existing_map_dag_is_preserved_and_rust_dag_only_appends() -> None:
    plan = _load_json(
        "docs/exec-plans/rust-default-engine/AUDIT_COMPILED_EXEC_PLAN_V1.json"
    )
    existing = _load_json("docs/audit/URBAN_MAP_GENERATION_CODEX_PR_LIST_20260824.json")
    frozen = plan["existing_dag_preservation"]

    assert [item["id"] for item in existing["pr_index"]] == frozen["nodes_in_order"]
    assert existing["dependency_dag"] == frozen["edges_in_order"]
    assert plan["dependency_dag"][0] == {"from": "MAP-PR-011", "to": "RUST-PR-001"}
    assert all(
        edge["from"].startswith("RUST-PR-") and edge["to"].startswith("RUST-PR-")
        for edge in plan["dependency_dag"][1:]
    )


def test_every_p0_p1_failure_has_mechanical_detection_and_owner_pr() -> None:
    plan = _load_json(
        "docs/exec-plans/rust-default-engine/AUDIT_COMPILED_EXEC_PLAN_V1.json"
    )
    threats = _load_json(
        "docs/exec-plans/rust-default-engine/"
        "RUST_ENGINE_P0_P1_THREAT_CATALOGUE_V1.json"
    )
    owner = {
        fm_id: pr["id"]
        for pr in plan["pull_requests"]
        for fm_id in pr["failure_mode_ids"]
    }
    assert len(owner) == 50
    for failure in threats["failure_modes"]:
        assert failure["severity"] in {"P0", "P1"}
        assert failure["required_detection"]["type"] in {"test", "assertion", "stop"}
        assert failure["required_detection"]["target"]
        assert owner[failure["id"]] == failure["owner_pr"]


def test_hard_invariants_are_attached_and_mechanically_checkable() -> None:
    plan = _load_json(
        "docs/exec-plans/rust-default-engine/AUDIT_COMPILED_EXEC_PLAN_V1.json"
    )
    matrix = _load_json(
        "docs/exec-plans/rust-default-engine/"
        "RUST_ENGINE_INVARIANT_TEST_MATRIX_V1.json"
    )
    attached = {
        inv_id for pr in plan["pull_requests"] for inv_id in pr["invariant_ids"]
    }
    assert set(plan["hard_invariant_ids"]) <= attached
    for invariant in matrix["invariants"]:
        assert invariant["mechanical_check"]["type"] in {
            "pytest",
            "command",
            "assertion",
            "stop",
        }
        assert invariant["mechanical_check"]["target"]


def test_first_rust_pr_fails_closed_without_predecessor_receipt(tmp_path: Path) -> None:
    module = _load_module(
        "validate_rust_default_engine_plan_readiness",
        ROOT / "tools/validate_rust_default_engine_plan.py",
    )
    module.ROOT = tmp_path
    ready, errors = module.readiness("RUST-PR-001")
    assert not ready
    assert any("MAP-PR-011.json" in error for error in errors)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True, capture_output=True
    )
    return result.stdout.strip()


def _make_evidence_fixture(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    (repo / "src").mkdir()
    (repo / "src/a.py").write_text("x = 1\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "src/a.py").write_text("x = 2\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "final")
    final = _git(repo, "rev-parse", "HEAD")
    log = repo / "test.log"
    log.write_text("PASS\n")
    command = "python -m pytest -q tests/test_x.py"
    contract = {
        "schema_version": "metroflow_materialized_rust_engine_pr_v1",
        "id": "RUST-PR-TEST",
        "base_binding": {"base_sha": base},
        "scope": {
            "allowed_paths": ["src/**"],
            "forbidden_paths": ["artifacts/frozen/**"],
        },
        "verification": {
            "targeted": [command],
            "negative": [command],
            "regression": [command],
            "full_relevant_suite": [command],
        },
        "invariant_ids": ["RINV-X"],
        "failure_mode_ids": ["RFM-X"],
    }
    evidence = {
        "pr_id": "RUST-PR-TEST",
        "base_sha": base,
        "final_sha": final,
        "actual_changed_paths": ["src/a.py"],
        "commands": [
            {
                "command": command,
                "exit_code": 0,
                "log_path": "test.log",
                "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
            }
        ],
        "invariants": [{"id": "RINV-X", "status": "PASS"}],
        "failure_modes": [{"id": "RFM-X", "status": "PASS"}],
        "review": {
            "status": "PASS",
            "findings": {"P0": 0, "P1": 0, "unresolved": 0},
            "implementer_context_id": "impl",
            "reviewer_context_id": "review",
            "base_sha": base,
            "final_sha": final,
            "first_pass_mode": "audit_only",
        },
        "unresolved_blockers": [],
    }
    contract_path = repo / "contract.json"
    evidence_path = repo / "evidence.json"
    contract_path.write_text(json.dumps(contract))
    evidence_path.write_text(json.dumps(evidence))
    return repo, contract_path, evidence_path, evidence


def test_evidence_verifier_accepts_complete_bundle(tmp_path: Path) -> None:
    module = _load_module(
        "verify_rust_default_engine_evidence",
        ROOT / "tools/verify_rust_default_engine_evidence.py",
    )
    repo, contract, evidence, _ = _make_evidence_fixture(tmp_path)
    module.ROOT = repo
    summary = module.verify(contract, evidence)
    assert summary["changed_paths"] == 1
    assert summary["invariants"] == 1
    assert summary["failure_modes"] == 1


@pytest.mark.parametrize(
    "mutation, expected",
    [
        (lambda data: data["actual_changed_paths"].append("src/fake.py"), "actual_changed_paths"),
        (
            lambda data: data["invariants"].clear(),
            "missing invariant evidence",
        ),
        (
            lambda data: data["review"].update(
                reviewer_context_id=data["review"]["implementer_context_id"]
            ),
            "reviewer context must differ",
        ),
    ],
)
def test_evidence_verifier_fails_closed(
    tmp_path: Path, mutation, expected: str
) -> None:
    module = _load_module(
        "verify_rust_default_engine_evidence_failures",
        ROOT / "tools/verify_rust_default_engine_evidence.py",
    )
    repo, contract, evidence_path, evidence = _make_evidence_fixture(tmp_path)
    module.ROOT = repo
    mutation(evidence)
    evidence_path.write_text(json.dumps(evidence))
    with pytest.raises(module.EvidenceError, match=expected):
        module.verify(contract, evidence_path)
