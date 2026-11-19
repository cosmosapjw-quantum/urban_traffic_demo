"""The optimized native research binary must not inherit previous V03 receipt credit."""
import hashlib
import json
from pathlib import Path

from metroflow.v1.native_engine import native_binary_provenance
from metroflow.v1.v03_readiness import assess_v03_readiness

ROOT=Path(__file__).resolve().parents[2]


def test_old_native_calendar_receipts_are_stale_after_rebuilding_rust_kernel():
    raw=(ROOT/"scenarios/v1/release_matrix.json").read_bytes()
    matrix=json.loads(raw)
    plan=json.loads((ROOT/"docs/v1/PLAN.json").read_bytes())
    old=ROOT/"artifacts/kcmb_v03_physics_20261119/preparation"
    receipts=[json.loads((old/(case["id"]+".prepare.json")).read_bytes())
              for case in matrix["cases"]]
    current=native_binary_provenance()["sha256"]
    assert current != receipts[0]["native_binary_sha256"]
    result=assess_v03_readiness(
        plan,matrix,matrix_sha256=hashlib.sha256(raw).hexdigest(),
        preparation_receipts=receipts,
        live_native_binary_sha256=current,
    )
    assert result["v03"]["calendar_preparation_verified"]==0
    assert result["v03"]["completed_full_day_runs"]==0
    assert all(
        info["status"]=="REJECTED_EVIDENCE"
        for info in result["case_preparation"].values()
    )
