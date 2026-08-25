#!/usr/bin/env python3
"""Verify a completed Rust migration PR evidence bundle against its contract."""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")


class EvidenceError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot load {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise EvidenceError(f"{path} must contain a JSON object")
    return data


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=False
    )
    if check and proc.returncode:
        raise EvidenceError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


def _matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def verify(contract_path: Path, evidence_path: Path) -> dict[str, Any]:
    contract = _load(contract_path)
    evidence = _load(evidence_path)
    errors: list[str] = []

    if contract.get("schema_version") != "metroflow_materialized_rust_engine_pr_v1":
        errors.append("contract is not a materialized Rust PR contract")
    if evidence.get("pr_id") != contract.get("id"):
        errors.append("evidence pr_id does not match contract")
    for key in ("base_sha", "final_sha"):
        if not SHA40_RE.fullmatch(str(evidence.get(key, ""))):
            errors.append(f"evidence {key} must be a 40-hex SHA")
    base = str(evidence.get("base_sha", ""))
    final = str(evidence.get("final_sha", ""))
    if base and base != contract.get("base_binding", {}).get("base_sha"):
        errors.append("evidence base_sha does not match materialized contract")
    if SHA40_RE.fullmatch(base) and SHA40_RE.fullmatch(final):
        if _git("merge-base", "--is-ancestor", base, final, check=False).returncode:
            errors.append("base_sha is not an ancestor of final_sha")
        diff = _git("diff", "--name-only", f"{base}..{final}", check=False)
        if diff.returncode:
            errors.append(f"cannot compute actual diff: {diff.stderr.strip()}")
            actual_paths: list[str] = []
        else:
            actual_paths = [line for line in diff.stdout.splitlines() if line]
        declared_paths = sorted(str(path) for path in evidence.get("actual_changed_paths", []))
        if sorted(actual_paths) != declared_paths:
            errors.append("declared actual_changed_paths differ from git diff")
        scope = contract["scope"]
        for path in actual_paths:
            if not _matches(path, list(scope["allowed_paths"])):
                errors.append(f"changed path outside allowed scope: {path}")
            if _matches(path, list(scope["forbidden_paths"])):
                errors.append(f"forbidden path changed: {path}")
        diff_check = _git("diff", "--check", f"{base}..{final}", check=False)
        if diff_check.returncode:
            errors.append(f"git diff --check failed: {diff_check.stdout}{diff_check.stderr}")
    else:
        actual_paths = []

    required_commands: set[str] = set()
    for category in ("targeted", "negative", "regression", "full_relevant_suite"):
        required_commands.update(contract["verification"][category])
    command_records = evidence.get("commands", [])
    command_map = {
        record.get("command"): record
        for record in command_records
        if isinstance(record, dict) and record.get("command")
    }
    for command in required_commands:
        record = command_map.get(command)
        if record is None:
            errors.append(f"required command not evidenced: {command}")
            continue
        if int(record.get("exit_code", -1)) != 0:
            errors.append(f"required command failed: {command}")
        log_path = record.get("log_path")
        log_sha = record.get("log_sha256")
        if not log_path or not log_sha:
            errors.append(f"command lacks raw log evidence: {command}")
        else:
            path = ROOT / str(log_path)
            if not path.is_file():
                errors.append(f"command log missing: {log_path}")
            elif hashlib.sha256(path.read_bytes()).hexdigest() != log_sha:
                errors.append(f"command log digest mismatch: {log_path}")

    required_inv = set(contract.get("invariant_ids", []))
    inv_records = {
        item.get("id"): item for item in evidence.get("invariants", []) if isinstance(item, dict)
    }
    for inv_id in required_inv:
        record = inv_records.get(inv_id)
        if record is None:
            errors.append(f"missing invariant evidence: {inv_id}")
        elif record.get("status") != "PASS":
            errors.append(f"invariant did not pass: {inv_id}")

    required_fm = set(contract.get("failure_mode_ids", []))
    fm_records = {
        item.get("id"): item for item in evidence.get("failure_modes", []) if isinstance(item, dict)
    }
    for fm_id in required_fm:
        record = fm_records.get(fm_id)
        if record is None:
            errors.append(f"missing failure-mode evidence: {fm_id}")
        elif record.get("status") != "PASS":
            errors.append(f"failure-mode detection did not pass: {fm_id}")

    unresolved = evidence.get("unresolved_blockers", [])
    if unresolved:
        errors.append("unresolved blockers are not empty")
    review = evidence.get("review", {})
    if review.get("status") != "PASS":
        errors.append("fresh-context review status is not PASS")
    findings = review.get("findings", {})
    for key in ("P0", "P1", "unresolved"):
        if int(findings.get(key, -1)) != 0:
            errors.append(f"review findings.{key} must equal 0")
    if review.get("implementer_context_id") == review.get("reviewer_context_id"):
        errors.append("reviewer context must differ from implementer context")
    if review.get("base_sha") != base or review.get("final_sha") != final:
        errors.append("review SHA identity does not match evidence bundle")
    if review.get("first_pass_mode") != "audit_only":
        errors.append("review first pass must be audit_only")

    if errors:
        raise EvidenceError("\n".join(f"- {error}" for error in errors))
    return {
        "pr_id": evidence["pr_id"],
        "base_sha": base,
        "final_sha": final,
        "changed_paths": len(actual_paths),
        "commands": len(required_commands),
        "invariants": len(required_inv),
        "failure_modes": len(required_fm),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    try:
        contract = args.contract if args.contract.is_absolute() else ROOT / args.contract
        evidence = args.evidence if args.evidence.is_absolute() else ROOT / args.evidence
        summary = verify(contract, evidence)
        print("PASS " + json.dumps(summary, sort_keys=True))
        return 0
    except EvidenceError as exc:
        print(f"EVIDENCE_INVALID\n{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
