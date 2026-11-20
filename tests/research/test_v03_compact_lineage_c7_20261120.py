"""Finite evidence check for the newly completed original 100k Valley 10s tick."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts/v03_compact_lineage_20261120"
C6 = ART / "C6_CROSS_BINARY_25700.json"
C7 = ART / "C7_ORIGINAL_25660.json"


def load(path):
    return json.loads(path.read_bytes())


def test_new_source_completes_a_real_25650_to_25660_tick_and_preserves_original_input():
    prior = load(C6)
    done = load(C7)
    assert done["status"] == "EXECUTED_ORIGINAL_100K_ONE_TICK_CROSS_BINARY"
    assert done["start_time_s"] == 25650.
    assert done["target_time_s"] == done["completed_time_s"] == 25660.
    assert done["error"] is None
    assert done["current_source_dirty"] is False
    assert done["historical_roundtrip_wire_exact"] is True
    assert done["historical_input_checkpoint_sha256"] == prior["input_checkpoint_sha256"]
    assert done["historical_input_checkpoint_bytes"] == prior["input_checkpoint_bytes"]
    assert done["original_driver_identity"] == done["current_driver_identity"]
    assert done["current_candidate_sha256"] == prior["current_source_sha256"]
    assert done["current_native_sha256"] == prior["current_native_binary_sha256"]
    assert done["process_cap_bytes"] == 8 * 1024**3
    assert done["budget_experimental_override"] == "OFF"
    assert done["full_original_24h_acceptance"] == "BLOCKED_0_OF_9"
    assert done["original_current_native_0_to_25650_path_verified"] is False


def test_every_original_physical_unit_is_conserved_after_complete_tick():
    d = load(C7)
    assert isinstance(d["completed_ledger"], dict)
    for unit in ("persons", "vehicles", "cargo_kg"):
        z = d["completed_ledger"][unit]
        vals = [z[k] for k in ("requested", "released", "completed", "pending", "active")]
        assert all(math.isfinite(x) for x in vals)
        atol = 1e-9 * max(1., abs(z["requested"]), abs(z["released"]))
        assert abs(z["requested"] - z["released"] - z["pending"]) <= atol
        assert abs(z["released"] - z["completed"] - z["active"]) <= atol
    assert d["start_ledger"]["persons"]["requested"] < d["completed_ledger"]["persons"]["requested"]
    assert d["completed_time_s"] == 25660.


def test_original_later_guards_are_no_longer_blocking_during_this_complete_tick():
    d = load(C7)
    assert d["trace_sites"]["road_work:indexed sweep preflight"]["calls"] > 0
    for site in (
        "road_work:indexed sweep preflight",
        "road_work:entry interval split",
        "road_work:transfer candidates",
        "road_work:packet interval packing",
    ):
        row = d["trace_sites"][site]
        assert row["exceeded"] == 0
        assert row["max_required"] <= row["limit_at_max"]
    assert isinstance(d["new_checkpoint_sha256"], str)
    assert len(d["new_checkpoint_sha256"]) == 64
    assert d["new_checkpoint_bytes"] > 10**9
    assert d["new_checkpoint_local_only"] is True
