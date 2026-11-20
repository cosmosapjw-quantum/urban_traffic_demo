"""Actual native event source-sharing and direct-point packet guard progression."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts/v03_event_arc_20261120"


def receipt(name):
    return json.loads((ART / name).read_bytes())


def test_new_immutable_point_path_clears_actual_old_packing_guard():
    original = receipt("C6_CROSS_BINARY_25700.json")
    nonpoint = receipt("C8_DIRECT_CORE_25700.json")
    now = receipt("C9_POINT_CORE_25700.json")
    for row in (original, nonpoint, now):
        assert row["roundtrip_wire_identity"] is True
        assert row["status"] == "BLOCKED_RESOURCE"
        assert row["final_checkpoint_sha256"] is None
        assert row["original_V03_full_day_acceptance"] == "BLOCKED_0_OF_9"
        assert row["process_address_space_cap_bytes"] == 8 * 1024**3
    assert len({x["current_source_sha256"] for x in (original, nonpoint, now)}) == 3
    assert len({x["current_native_binary_sha256"] for x in (original, nonpoint, now)}) == 3
    assert (original["input_checkpoint_sha256"] ==
            nonpoint["input_checkpoint_sha256"] == now["input_checkpoint_sha256"])
    assert original["trace_sites"]["road_work:transfer candidates"]["exceeded"] == 0
    assert now["trace_sites"]["road_work:transfer candidates"]["exceeded"] == 0
    assert original["trace_sites"]["road_work:packet interval packing"]["exceeded"] == 1
    assert nonpoint["trace_sites"]["road_work:packet interval packing"]["exceeded"] == 1
    assert now["trace_sites"]["road_work:packet interval packing"]["exceeded"] == 0


def test_new_next_gate_exact_terms_and_no_false_25700_success():
    now = receipt("C9_POINT_CORE_25700.json")
    row = now["trace_sites"]["road_work:entry interval split"]
    x = row["terms_at_max"]
    assert x["base"] + x["event_bytes"] + x["incoming_rows"] * 128 + (
        x["interval_retained"] + x["interval_transient"] + x["extra"]) == row["max_required"]
    assert row["max_required"] == 5264783728
    assert row["limit_at_max"] == 5264781423
    assert row["max_required"] - row["limit_at_max"] == 2305
    assert row["exceeded"] >= 1
    assert "entry interval split" in now["error"]["message"]
    assert now["completed_time_s"] is None
    assert now["final_checkpoint_bytes"] is None
    assert now["final_ledger"] is None
