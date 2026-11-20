"""Source-bound *cross-version* physical probe: reproduce exact negative claim."""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
CURRENT = BASE / "artifacts/v03_exact_interval_view_20261120/C8_CROSS_BINARY_25700.json"
HISTORICAL = BASE / "artifacts/v03_composed_events_20261120/C8_BITSET_ORIGINAL_DEFAULT_25650.json"
CURRENT_READINESS = BASE / "artifacts/v03_exact_interval_view_20261120/C7_CURRENT_NATIVE_READINESS.json"


def load(path):
    return json.loads(path.read_bytes())


def test_checkpoint_identity_distinguishes_historical_and_current_source():
    r, old = load(CURRENT), load(HISTORICAL)
    assert r["schema"] == "V03_EXACT_VIEW_CROSS_BINARY_PROBE_V1"
    assert r["old_source_sha256"] == old["source_sha256"]
    assert r["old_native_binary_sha256"] == old["loaded_native_sha256"]
    assert r["input_checkpoint_sha256"] == old["final_checkpoint_sha256"]
    assert r["input_checkpoint_bytes"] == old["checkpoint_bytes"]
    assert r["old_driver_identity"] == r["current_driver_identity"]
    assert r["current_source_sha256"] != r["old_source_sha256"]
    assert r["current_native_binary_sha256"] != r["old_native_binary_sha256"]
    assert r["current_source_dirty"] is False
    assert r["roundtrip_wire_identity"] is True
    assert r["original_source_bound_current_prefix"] is False


def test_original_unchanged_guard_exact_terms_and_no_false_release():
    r = load(CURRENT)
    s = r["trace_sites"]["road_work:transfer candidates"]
    x = s["terms_at_max"]
    assert x["interval_transient"] == 0
    assert x["interval_retained"] == 0
    assert (x["base"] + x["event_bytes"] + x["incoming_rows"] * 128
            + x["interval_retained"] + x["interval_transient"] + x["extra"]
            == s["max_required"])
    assert s["max_required"] == 5264786120
    assert s["limit_at_max"] == 5264781391
    assert s["max_required"] - s["limit_at_max"] == 4729
    assert s["exceeded"] >= 1
    assert r["status"] == "BLOCKED_RESOURCE"
    assert r["phase"] == "PHYSICAL_25650_TO_25700"
    assert "transfer candidates" in r["error"]["message"]
    assert r["final_checkpoint_sha256"] is None
    assert r["final_ledger"] is None
    assert r["completed_time_s"] is None
    assert r["process_address_space_cap_bytes"] == 8 * 1024**3
    assert r["original_V03_full_day_acceptance"] == "BLOCKED_0_OF_9"


def test_original_v03_calendar_preparation_does_not_count_physics_runs():
    r, ready = load(CURRENT), load(CURRENT_READINESS)
    assert r["current_source_sha256"] == ready["measurement_context"]["live_candidate_source_sha256"]
    assert r["current_native_binary_sha256"] == ready["measurement_context"]["live_native_binary_sha256"]
    assert ready["v03"]["calendar_preparation_verified"] == 3
    assert ready["v03"]["dependency_nodes_completed"] == 3
    assert (ready["dag"]["completed"], ready["dag"]["total"]) == (19, 21)
    assert (ready["v03"]["completed_full_day_runs"],
            ready["v03"]["required_full_day_runs"]) == (0, 9)
    assert not ready["v03"]["ready_for_release"]
