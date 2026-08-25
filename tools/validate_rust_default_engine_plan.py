#!/usr/bin/env python3
"""Validate the Rust-default-engine compiled execution plan.

This tool is intentionally stdlib-only.  It validates the plan itself and,
optionally, whether one PR is ready to start.  Exit code 2 means the plan is
valid but the requested PR is deliberately blocked by predecessor state.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
EXPECTED_RUST_IDS = tuple(f"RUST-PR-{index:03d}" for index in range(1, 17))
DETECTION_TYPES = {"test", "assertion", "stop"}
ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "docs/exec-plans/rust-default-engine/AUDIT_COMPILED_EXEC_PLAN_V1.json"


class PlanError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanError(f"cannot load {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PlanError(f"{path} must contain a JSON object")
    return data


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=check,
    )


def _receipt_path(plan: dict[str, Any], pr_id: str) -> Path:
    policy = plan["receipt_policy"]
    if pr_id == "MAP-PR-011":
        name = policy["terminal_predecessor_receipt"]
    else:
        name = policy["rust_receipt_pattern"].format(pr_id=pr_id)
    return ROOT / policy["directory"] / name


def _validate_receipt(plan: dict[str, Any], pr_id: str) -> list[str]:
    path = _receipt_path(plan, pr_id)
    if not path.is_file():
        return [f"missing predecessor receipt: {path.relative_to(ROOT)}"]
    receipt = _load(path)
    errors: list[str] = []
    if receipt.get("pr_id") != pr_id:
        errors.append(f"{path}: pr_id mismatch")
    if receipt.get("status") != plan["receipt_policy"]["required_status"]:
        errors.append(f"{path}: status is not PASS")
    findings = receipt.get("findings", {})
    maximum = plan["receipt_policy"]["required_max_findings"]
    for key, expected in maximum.items():
        if int(findings.get(key, -1)) != expected:
            errors.append(f"{path}: findings.{key} must equal {expected}")
    if plan["receipt_policy"]["reviewer_context_must_differ_from_implementer"]:
        if receipt.get("reviewer_context_id") == receipt.get("implementer_context_id"):
            errors.append(f"{path}: reviewer and implementer contexts must differ")
    for key in ("base_sha", "final_sha"):
        if not SHA40_RE.fullmatch(str(receipt.get(key, ""))):
            errors.append(f"{path}: {key} must be a 40-hex SHA")
    return errors


def validate_plan(root: Path = ROOT) -> dict[str, Any]:
    plan = _load(root / PLAN_PATH.relative_to(ROOT))
    arch = _load(root / plan["architecture_ref"])
    threats = _load(root / plan["threat_catalogue_ref"])
    invariants = _load(root / plan["invariant_matrix_ref"])
    review = _load(root / plan["review_contract_ref"])
    evidence = _load(root / plan["evidence_schema_ref"])
    existing = _load(root / plan["existing_dag_preservation"]["authority"])

    errors: list[str] = []
    if plan.get("schema_version") != "metroflow_audit_compiled_exec_plan_rust_engine_v1":
        errors.append("unexpected plan schema")
    if plan.get("repository") != "cosmosapjw-quantum/urban_traffic_demo":
        errors.append("unexpected repository")
    source = plan.get("source_evidence", {})
    if not SHA40_RE.fullmatch(str(source.get("main_sha", ""))):
        errors.append("source main_sha must be 40 hex")
    if not SHA40_RE.fullmatch(str(source.get("main_tree", ""))):
        errors.append("source main_tree must be 40 hex")

    current_nodes = tuple(item["id"] for item in existing["pr_index"])
    current_edges = tuple((e["from"], e["to"]) for e in existing["dependency_dag"])
    frozen = plan["existing_dag_preservation"]
    frozen_nodes = tuple(frozen["nodes_in_order"])
    frozen_edges = tuple((e["from"], e["to"]) for e in frozen["edges_in_order"])
    if current_nodes != frozen_nodes:
        errors.append("existing MAP PR node order changed")
    if current_edges != frozen_edges:
        errors.append("existing MAP dependency edges changed")
    if plan["dependency_dag"][0] != {"from": "MAP-PR-011", "to": "RUST-PR-001"}:
        errors.append("Rust DAG must append only after MAP-PR-011")

    prs = plan.get("pull_requests", [])
    ids = tuple(pr.get("id") for pr in prs)
    branches = tuple(pr.get("branch") for pr in prs)
    if ids != EXPECTED_RUST_IDS:
        errors.append(f"Rust PR IDs/order differ from {EXPECTED_RUST_IDS}")
    if len(branches) != len(set(branches)):
        errors.append("duplicate Rust PR branch names")
    expected_edges = [("MAP-PR-011", "RUST-PR-001")]
    expected_edges.extend(zip(EXPECTED_RUST_IDS[:-1], EXPECTED_RUST_IDS[1:]))
    actual_edges = [(e["from"], e["to"]) for e in plan["dependency_dag"]]
    if actual_edges != expected_edges:
        errors.append("Rust dependency DAG is not the required strict serial append-only chain")

    inv_by_id = {item["id"]: item for item in invariants["invariants"]}
    threat_by_id = {item["id"]: item for item in threats["failure_modes"]}
    if len(inv_by_id) != len(invariants["invariants"]):
        errors.append("duplicate invariant IDs")
    if len(threat_by_id) != len(threats["failure_modes"]):
        errors.append("duplicate failure-mode IDs")

    pr_by_id = {item["id"]: item for item in prs}
    attached_inv: set[str] = set()
    attached_threat: set[str] = set()
    produced_paths: dict[str, str] = {}
    for pr in prs:
        pr_id = pr["id"]
        required_fields = (
            "title", "branch", "depends_on", "base_binding", "objective", "scope",
            "inspect_paths", "planned_new_paths", "preconditions", "invariant_ids",
            "implementation", "verification", "completion_evidence", "agent_policy",
            "review_gate", "claim", "stop_conditions", "failure_mode_ids",
        )
        for field in required_fields:
            if field not in pr:
                errors.append(f"{pr_id}: missing {field}")
        if not pr["scope"].get("allowed_paths"):
            errors.append(f"{pr_id}: allowed_paths must not be empty")
        if not pr["scope"].get("forbidden_paths"):
            errors.append(f"{pr_id}: forbidden_paths must not be empty")
        for category in ("targeted", "negative", "regression", "full_relevant_suite"):
            if not pr["verification"].get(category):
                errors.append(f"{pr_id}: verification.{category} must not be empty")
        if pr["review_gate"].get("pass_condition") != {"P0": 0, "P1": 0, "unresolved": 0}:
            errors.append(f"{pr_id}: review gate must require P0=P1=unresolved=0")
        for inv_id in pr["invariant_ids"]:
            attached_inv.add(inv_id)
            if inv_id not in inv_by_id:
                errors.append(f"{pr_id}: unknown invariant {inv_id}")
        for fm_id in pr["failure_mode_ids"]:
            attached_threat.add(fm_id)
            item = threat_by_id.get(fm_id)
            if item is None:
                errors.append(f"{pr_id}: unknown failure mode {fm_id}")
            elif item.get("owner_pr") != pr_id:
                errors.append(f"{pr_id}: failure mode {fm_id} owner mismatch")
        for path in pr["planned_new_paths"]:
            if path in produced_paths:
                errors.append(f"planned path {path} has multiple producers")
            produced_paths[path] = pr_id

    for item in invariants["invariants"]:
        check = item.get("mechanical_check", {})
        if item.get("severity_if_violated") in {"P0", "P1"}:
            if check.get("type") not in {"pytest", "command", "assertion", "stop"}:
                errors.append(f"{item['id']}: P0/P1 invariant lacks mechanical check")
            if not check.get("target"):
                errors.append(f"{item['id']}: mechanical check target missing")
    for item in threats["failure_modes"]:
        if item.get("owner_pr") not in pr_by_id:
            errors.append(f"{item['id']}: owner PR missing")
        detection = item.get("required_detection", {})
        if item.get("severity") in {"P0", "P1"}:
            if detection.get("type") not in DETECTION_TYPES:
                errors.append(f"{item['id']}: P0/P1 lacks test/assertion/STOP detection")
            if not detection.get("target"):
                errors.append(f"{item['id']}: detection target missing")
        for inv_id in item.get("violates", []):
            if inv_id not in inv_by_id:
                errors.append(f"{item['id']}: unknown violated invariant {inv_id}")

    missing_threats = set(threat_by_id) - attached_threat
    if missing_threats:
        errors.append(f"unattached failure modes: {sorted(missing_threats)}")
    # All invariants need not be hard-attached if they are global, but every hard invariant must be.
    missing_hard = set(plan["hard_invariant_ids"]) - attached_inv
    if missing_hard:
        errors.append(f"hard invariants not attached to a PR: {sorted(missing_hard)}")

    for rel in plan["must_exist_at_audit_base"]:
        if not (root / rel).exists():
            errors.append(f"audit-base path missing: {rel}")
    for rel in (
        plan["architecture_ref"], plan["threat_catalogue_ref"], plan["invariant_matrix_ref"],
        plan["review_contract_ref"], plan["evidence_schema_ref"], plan["handoff_ref"],
        plan["source_audit_receipt_ref"], plan["package_manifest_ref"], *plan["tool_refs"].values(),
    ):
        if not (root / rel).exists():
            errors.append(f"referenced package file missing: {rel}")


    manifest = _load(root / plan["package_manifest_ref"])
    listed = manifest.get("files", [])
    if int(manifest.get("file_count", -1)) != len(listed):
        errors.append("package manifest file_count mismatch")
    listed_paths: set[str] = set()
    for record in listed:
        rel = str(record.get("path", ""))
        if not rel or rel in listed_paths:
            errors.append(f"package manifest duplicate/empty path: {rel!r}")
            continue
        listed_paths.add(rel)
        path = root / rel
        if not path.is_file():
            errors.append(f"package manifest file missing: {rel}")
            continue
        content = path.read_bytes()
        import hashlib
        if int(record.get("size_bytes", -1)) != len(content):
            errors.append(f"package manifest size mismatch: {rel}")
        if record.get("sha256") != hashlib.sha256(content).hexdigest():
            errors.append(f"package manifest digest mismatch: {rel}")

    if arch.get("decision", {}).get("target") != "rust_owned_engine_with_python_frontend":
        errors.append("architecture target is not Rust-owned engine")
    review_pass = review.get("pass_condition", {})
    if any(review_pass.get(key) != 0 for key in ("P0", "P1", "unresolved")):
        errors.append("fresh-review contract must require P0=P1=unresolved=0")
    if review_pass.get("sha_match") is not True or review_pass.get("audit_only_first_pass") is not True:
        errors.append("fresh-review contract must bind SHAs and audit-only first pass")
    required_evidence_fields = set(evidence.get("required", []))
    for field in ("pr_id", "base_sha", "final_sha", "commands", "invariants", "failure_modes", "review"):
        if field not in required_evidence_fields:
            errors.append(f"evidence schema does not require {field}")

    if errors:
        raise PlanError("\n".join(f"- {error}" for error in errors))
    return {
        "pr_count": len(prs),
        "invariant_count": len(inv_by_id),
        "failure_mode_count": len(threat_by_id),
        "existing_map_nodes": len(current_nodes),
        "existing_map_edges": len(current_edges),
        "rust_edges": len(actual_edges),
    }


def readiness(pr_id: str) -> tuple[bool, list[str]]:
    plan = _load(PLAN_PATH)
    prs = {item["id"]: item for item in plan["pull_requests"]}
    if pr_id not in prs:
        raise PlanError(f"unknown PR ID: {pr_id}")
    predecessor = prs[pr_id]["depends_on"][0]
    errors = _validate_receipt(plan, predecessor)
    return not errors, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--check-readiness")
    parser.add_argument("--emit-summary", action="store_true")
    args = parser.parse_args()
    try:
        summary = validate_plan()
        if args.check_readiness:
            ready, errors = readiness(args.check_readiness)
            if not ready:
                print(f"BLOCKED_BY_PREDECESSOR_DAG: {args.check_readiness}", file=sys.stderr)
                for error in errors:
                    print(f"- {error}", file=sys.stderr)
                return 2
            print(f"READY: {args.check_readiness}")
        if args.emit_summary:
            print(json.dumps(summary, indent=2, sort_keys=True))
        elif args.check or not args.check_readiness:
            print(
                "PASS "
                f"prs={summary['pr_count']} "
                f"invariants={summary['invariant_count']} "
                f"failure_modes={summary['failure_mode_count']}"
            )
        return 0
    except PlanError as exc:
        print(f"PLAN_INVALID\n{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
