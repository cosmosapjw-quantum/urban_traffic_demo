"""Original Valley 100k gradual true continuous 10/20/30/40-second ladder."""
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
A=ROOT/"artifacts/v03_keyset_continuous_20261121"
STEPS=A/"C9_HISTORICAL_40S_STAIRCASE.json"
OLD=ROOT/"artifacts/v03_persistent_keyset_20261121/C8_KEYSET_CROSS_BINARY_25690.json"
FAILED=A/"C9_100K_10S_25700.json"


def read(p):
    return json.loads(p.read_bytes())


def test_actual_10_20_30_successful_prefix_and_40s_blocked_not_claimed():
    r=read(STEPS)
    assert r["status"]=="BLOCKED_RESOURCE_WITH_VALID_PREFIX"
    assert r["start_time_s"]==25660.
    assert r["requested_duration_s"]==40
    assert r["requested_end_s"]==25700.
    assert r["completed_time_s"]==25690.
    assert r["valid_advanced_duration_s"]==30.
    assert r["blocked_target_time_s"]==25700.
    measured=r["completed_step_wall_s"]
    assert [s["completed_time_s"] for s in measured]==[25670.,25680.,25690.]
    assert len(measured)==3
    assert all(0.<s["wall_s"]<7200 for s in measured)
    assert measured[0]["wall_s"]<measured[1]["wall_s"]<measured[2]["wall_s"]
    assert r["wall_total_including_full_preparation_and_checkpoint_io_s"]>sum(
        s["wall_s"] for s in measured)
    assert r["peak_rss_bytes"]<8*1024**3
    assert r["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert r["previous_checkpoint_cross_native"] is True
    assert r["original_candidate_from_time_zero_verified"] is False
    assert r["native_process_cap_bytes"]==8*1024**3
    assert r["trace_mode"]=="record"
    assert r["original_full_day_acceptance"]=="BLOCKED_0_OF_9"


def test_30second_continuous_checkpoint_equals_previous_independent_binary():
    r=read(STEPS)
    old=read(OLD)
    assert r["final_checkpoint_sha256"]==old["final_checkpoint_sha256"]
    assert r["final_checkpoint_bytes"]==old["final_checkpoint_bytes"]==2949231402
    assert r["completed_mass_ledger"]==old["completed_mass_ledger"]
    assert r["current_candidate_source_sha256"]!=old["current_candidate_source_sha256"]
    assert r["current_native_binary_sha256"]!=old["current_native_binary_sha256"]
    for unit in ("persons","vehicles","cargo_kg"):
        v=r["completed_mass_ledger"][unit]
        assert all(math.isfinite(t) for t in v.values())
        atol=1e-9*max(1.,abs(v["requested"]),abs(v["released"]))
        assert abs(v["requested"]-v["released"]-v["pending"])<=atol
        assert abs(v["released"]-v["completed"]-v["active"])<=atol


def test_named_first_new_guard_is_late_packet_packing_not_silent_success():
    r=read(STEPS)
    packed=r["trace_sites"]["road_work:packet interval packing"]
    assert packed["calls"]>0 and packed["exceeded"]==1
    assert packed["max_required"]==5026043552
    assert packed["limit_at_max"]==5026041759
    assert packed["max_required"]-packed["limit_at_max"]==1793
    for name in ("road_work:transfer candidates","road_work:entry interval split"):
        assert r["trace_sites"][name]["exceeded"]==0
    assert "packet interval packing" in r["error"]["message"]
    single=read(FAILED)
    assert single["status"]=="BLOCKED_RESOURCE"
    assert single["input_checkpoint_sha256"]!=r["previous_full_checkpoint_sha256"]
    assert single["current_candidate_source_sha256"]==r["current_candidate_source_sha256"]
    assert single["current_native_binary_sha256"]==r["current_native_binary_sha256"]
