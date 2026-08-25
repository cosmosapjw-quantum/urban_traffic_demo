#!/usr/bin/env python3
"""Bind one Rust migration PR contract to its exact Git base.

The generic compiled plan deliberately leaves future base SHAs unresolved.  This
tool may materialize a PR only when its predecessor receipt passes and HEAD is
exactly the requested base.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "docs/exec-plans/rust-default-engine/AUDIT_COMPILED_EXEC_PLAN_V1.json"
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
sys.path.insert(0, str(ROOT / "tools"))
from validate_rust_default_engine_plan import PlanError, readiness, validate_plan  # noqa: E402


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=False
    )
    if proc.returncode:
        raise PlanError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _blob_sha(base_sha: str, path: str) -> str | None:
    proc = subprocess.run(
        ["git", "rev-parse", f"{base_sha}:{path}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pr-id", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        validate_plan()
        if not SHA40_RE.fullmatch(args.base_sha):
            raise PlanError("--base-sha must be a 40-hex commit SHA")
        ready, errors = readiness(args.pr_id)
        if not ready:
            print(f"BLOCKED_BY_PREDECESSOR_DAG: {args.pr_id}", file=sys.stderr)
            for error in errors:
                print(f"- {error}", file=sys.stderr)
            return 2
        head = _git("rev-parse", "HEAD")
        if head != args.base_sha:
            raise PlanError(f"HEAD {head} does not equal requested base {args.base_sha}")
        if _git("status", "--porcelain=v1"):
            raise PlanError("worktree must be clean")
        _git("cat-file", "-e", f"{args.base_sha}^{{commit}}")
        tree = _git("show", "-s", "--format=%T", args.base_sha)

        plan = _load(PLAN_PATH)
        pr = next((item for item in plan["pull_requests"] if item["id"] == args.pr_id), None)
        if pr is None:
            raise PlanError(f"unknown PR ID: {args.pr_id}")
        contract = json.loads(json.dumps(pr))
        contract["schema_version"] = "metroflow_materialized_rust_engine_pr_v1"
        contract["source_plan"] = str(PLAN_PATH.relative_to(ROOT))
        contract["source_plan_sha256"] = hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest()
        contract["base_binding"] = {
            "base_sha": args.base_sha,
            "base_tree": tree,
            "state": "MATERIALIZED_READY",
            "predecessor": pr["depends_on"][0],
        }
        snapshot: dict[str, str] = {}
        for path in pr["inspect_paths"]:
            if any(token in path for token in ("*", "?", "[")):
                continue
            sha = _blob_sha(args.base_sha, path)
            if sha is not None:
                snapshot[path] = sha
        contract["base_blob_snapshot"] = snapshot

        output = args.output or (
            ROOT
            / "docs/exec-plans/rust-default-engine/materialized"
            / f"{args.pr_id}.json"
        )
        if not output.is_absolute():
            output = ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(output.relative_to(ROOT))
        return 0
    except (PlanError, OSError, json.JSONDecodeError) as exc:
        print(f"MATERIALIZATION_FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
