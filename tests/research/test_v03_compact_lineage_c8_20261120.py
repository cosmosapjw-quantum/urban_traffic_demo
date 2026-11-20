"""Current-native independent 25660 restart evidence; do not mistake blocked 25670 for success."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts/v03_compact_lineage_20261120"


def receipt(filename):
    return json.loads((ART / filename).read_bytes())


def test_new_native_checkpoint_reopen_preserves_source_wire_and_physics_ledger():
    prior = receipt("C7_ORIGINAL_25660.json")
    nxt = receipt("C8_CURRENT_SOURCE_25670.json")
    assert prior["status"] == "EXECUTED_ORIGINAL_100K_ONE_TICK_CROSS_BINARY"
    assert nxt["input_checkpoint_sha256"] == prior["new_checkpoint_sha256"]
    assert nxt["input_checkpoint_size_bytes"] == prior["new_checkpoint_bytes"]
    assert nxt["starting_checkpoint_roundtrip_exact"] is True
    assert nxt["input_mass_ledger"] == prior["completed_ledger"]
    assert nxt["current_candidate_source_sha256"] == prior["current_candidate_sha256"]
    assert nxt["current_native_binary_sha256"] == prior["current_native_sha256"]
    assert nxt["current_source_dirty"] is False
    assert nxt["current_driver_identity"] == nxt["previous_driver_identity"]
    assert nxt["original_matrix_sha256"] == prior["matrix_sha256"]
    assert nxt["native_process_cap_bytes"] == 8 * 1024**3
    assert nxt["budget_mode"] == "DEFAULT"


def test_next_tick_blocked_at_exact_guard_without_new_state_or_false_release():
    nxt = receipt("C8_CURRENT_SOURCE_25670.json")
    t = nxt["trace_sites"]["road_work:transfer candidates"]
    x = t["terms_at_max"]
    assert t["calls"] > 0 and t["exceeded"] == 1
    assert t["max_required"] == 5228912264
    assert t["limit_at_max"] == 5228906583
    assert t["max_required"] - t["limit_at_max"] == 5681
    assert t["max_required"] == (x["base"] + x["event_bytes"]
        + x["incoming_rows"] * 128 + x["interval_retained"]
        + x["interval_transient"] + x["extra"])
    assert nxt["status"] == "BLOCKED_RESOURCE"
    assert "transfer candidates" in nxt["error"]["message"]
    assert nxt["start_time_s"] == 25660.
    assert nxt["end_time_s"] == 25670.
    assert nxt["completed_time_s"] is None
    assert nxt["completed_mass_ledger"] is None
    assert nxt["final_checkpoint_sha256"] is None
    assert nxt["original_full_day_acceptance"] == "BLOCKED_0_OF_9"
