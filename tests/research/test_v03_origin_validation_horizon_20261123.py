"""Admission tests for real checkpoint identity and atomic-call clock credit."""
import json
from pathlib import Path
import pytest
from tools.research.v03_origin_validation_horizon_20261123 import (
    predecessor, next_target, SCHEMA, OLD_SOURCE, OLD_NATIVE,
)

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "artifacts/v03_event_store_envelope_20261123/R8e_original_100k_25720_requested_10s.json"


def test_exact_saved_pin_accepts_new_native():
    r, cross = predecessor(P.read_bytes(), "new-source", "new-native")
    assert cross and r["completed_time_s"] == 25730


def test_unpinned_cross_native_is_rejected():
    r = json.loads(P.read_bytes())
    r["created_utc"] = "changed"
    with pytest.raises(ValueError, match="unpinned"):
        predecessor(json.dumps(r).encode(), "new-source", "new-native")


@pytest.mark.parametrize("field,value", [
    ("native_process_cap_bytes", 16 * 1024**3),
    ("trace_mode", "record"), ("current_source_dirty", True),
    ("previous_checkpoint_full_wire_roundtrip_exact", False),
    ("final_checkpoint_sha256", None), ("completed_mass_ledger", None),
])
def test_cap_or_provenance_drift_rejected(field, value):
    r = json.loads(P.read_bytes())
    r.update(schema=SCHEMA)
    r[field] = value
    with pytest.raises(ValueError):
        predecessor(json.dumps(r).encode(), OLD_SOURCE, OLD_NATIVE)


def test_same_source_saved_partial_can_continue_but_cross_source_cannot():
    r = json.loads(P.read_bytes())
    r.update(schema=SCHEMA, status="BLOCKED_RESOURCE_WITH_VALID_PREFIX",
             requested_duration_s=20,
             error={"class": "BudgetExceeded", "message": "actual guard", "phase": "ADVANCE"})
    raw = json.dumps(r).encode()
    assert predecessor(raw, OLD_SOURCE, OLD_NATIVE)[1] is False
    with pytest.raises(ValueError, match="unpinned"):
        predecessor(raw, "other-source", OLD_NATIVE)


def test_failed_call_cannot_claim_unreturned_clock():
    r = json.loads(P.read_bytes())
    r.update(schema=SCHEMA, completed_time_s=25740)
    with pytest.raises(ValueError, match="clock mismatch"):
        predecessor(json.dumps(r).encode(), OLD_SOURCE, OLD_NATIVE)


def test_call_cadence_changes_boundaries_not_physical_dt():
    assert next_target(25730, 25750, "tick", 20) == 25740
    assert next_target(25730, 25750, "window", 20) == 25750
    assert next_target(25730, 29000, "hourly", 10) == 28800
    assert next_target(28800, 29000, "hourly", 10) == 29000


def test_exact_this_session_saved_25690_pin_can_reproduce_failed_40s():
    p = ROOT / "artifacts/v03_origin_validation_20261123/R8_staircase/from_25670_duration_20.json"
    r, cross = predecessor(p.read_bytes(), "capture-fixed-source", "capture-fixed-native")
    assert cross and r["completed_time_s"] == 25690
    assert predecessor(p.read_bytes(), r["current_candidate_source_sha256"],
                       r["current_native_binary_sha256"])[1] is False


def test_changed_this_session_receipt_cannot_cross_source():
    p = ROOT / "artifacts/v03_origin_validation_20261123/R8_staircase/from_25670_duration_20.json"
    r = json.loads(p.read_bytes())
    r["created_utc"] = "not-the-recorded-receipt"
    with pytest.raises(ValueError, match="unpinned"):
        predecessor(json.dumps(r).encode(), "capture-fixed-source", "capture-fixed-native")


def test_returned_40s_with_failed_save_is_not_a_durable_predecessor():
    p = ROOT / "artifacts/v03_origin_validation_20261123/R8_staircase/from_25690_duration_40.json"
    r = json.loads(p.read_bytes())
    with pytest.raises(ValueError, match="saved physical prefix"):
        predecessor(p.read_bytes(), r["current_candidate_source_sha256"],
                    r["current_native_binary_sha256"])
