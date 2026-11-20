"""Observed original Valley block relocation after source-sharing immutable events."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "artifacts/v03_event_arc_20261120/C6_CROSS_BINARY_25700.json"
PREV = ROOT / "artifacts/v03_exact_interval_view_20261120/C8_CROSS_BINARY_25700.json"


def load(p):
    return json.loads(p.read_bytes())


def test_real_old_checkpoint_is_wire_identical_and_candidate_fingerprinted():
    now, old = load(HERE), load(PREV)
    assert now["roundtrip_wire_identity"] is True
    assert old["roundtrip_wire_identity"] is True
    assert now["input_checkpoint_sha256"] == old["input_checkpoint_sha256"]
    assert now["old_driver_identity"] == now["current_driver_identity"]
    assert now["current_source_sha256"] != old["current_source_sha256"]
    assert now["current_native_binary_sha256"] != old["current_native_binary_sha256"]
    assert now["process_address_space_cap_bytes"] == old["process_address_space_cap_bytes"] == 8 * 1024**3


def test_previous_transfer_guard_cleared_but_new_pack_guard_exactly_blocks():
    now, old = load(HERE), load(PREV)
    t0 = old["trace_sites"]["road_work:transfer candidates"]
    t1 = now["trace_sites"]["road_work:transfer candidates"]
    assert t0["exceeded"] == 1
    assert t1["calls"] > 0
    assert t1["exceeded"] == 0
    assert t1["max_required"] < t1["limit_at_max"]
    assert old["status"] == "BLOCKED_RESOURCE"
    assert "transfer candidates" in old["error"]["message"]
    pack = now["trace_sites"]["road_work:packet interval packing"]
    x = pack["terms_at_max"]
    assert (x["base"] + x["event_bytes"] + x["incoming_rows"] * 128
            + x["interval_retained"] + x["interval_transient"] + x["extra"]
            == pack["max_required"])
    assert pack["max_required"] == 5264783344
    assert pack["limit_at_max"] == 5264781423
    assert pack["max_required"] - pack["limit_at_max"] == 1921
    assert pack["exceeded"] == 1
    assert now["status"] == "BLOCKED_RESOURCE"
    assert "packet interval packing" in now["error"]["message"]
    assert now["completed_time_s"] is None
    assert now["final_checkpoint_sha256"] is None
    assert now["final_ledger"] is None
    assert now["original_V03_full_day_acceptance"] == "BLOCKED_0_OF_9"
