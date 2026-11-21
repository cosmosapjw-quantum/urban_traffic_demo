"""Independent original 100k 40-second native chronology and byte-identity audit."""
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_keyset_continuous_20261121"
FULL=ART/"C9_HISTORICAL_40S_FROM_25650.json"
SHORT=ART/"C9_HISTORICAL_40S_STAIRCASE.json"
OLD=ROOT/"artifacts/v03_persistent_keyset_20261121/C8_KEYSET_CROSS_BINARY_25690.json"
HIST=ROOT/"artifacts/v03_composed_events_20261120/C8_BITSET_ORIGINAL_DEFAULT_25650.json"


def read(p):
    return json.loads(p.read_bytes())


def test_actual_40sec_original_native_route_and_staircase():
    r=read(FULL);h=read(HIST)
    assert r["status"]=="EXECUTED_CURRENT_SOURCE_CONTINUOUS_HORIZON"
    assert r["start_time_s"]==25650.
    assert r["requested_duration_s"]==r["valid_advanced_duration_s"]==40
    assert r["requested_end_s"]==r["completed_time_s"]==25690.
    assert r["blocked_target_time_s"] is None
    assert r["error"] is None
    assert r["previous_checkpoint_cross_native"] is True
    assert r["historical_original_25650_source"] is True
    assert r["original_candidate_from_time_zero_verified"] is False
    assert r["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert r["previous_full_checkpoint_sha256"]==h["final_checkpoint_sha256"]
    assert r["previous_full_checkpoint_bytes"]==h["checkpoint_bytes"]
    assert r["native_process_cap_bytes"]==8*1024**3
    assert r["trace_mode"]=="record"
    assert r["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
    steps=r["completed_step_wall_s"]
    assert [v["completed_time_s"] for v in steps]==[25660.,25670.,25680.,25690.]
    assert len(steps)==4
    assert 10<steps[0]["wall_s"]<steps[1]["wall_s"]<steps[2]["wall_s"]<steps[3]["wall_s"]<30
    assert r["wall_total_including_full_preparation_and_checkpoint_io_s"]>sum(v["wall_s"] for v in steps)
    assert r["peak_rss_bytes"]<8*1024**3


def test_40sec_and_30sec_distinct_histories_reach_exact_same_25690_bits():
    r=read(FULL);s=read(SHORT);prior=read(OLD)
    assert r["start_time_s"]==25650.
    assert s["start_time_s"]==25660.
    assert r["final_checkpoint_sha256"]==s["final_checkpoint_sha256"]==prior["final_checkpoint_sha256"]
    assert r["final_checkpoint_bytes"]==s["final_checkpoint_bytes"]==prior["final_checkpoint_bytes"]==2949231402
    assert r["completed_mass_ledger"]==s["completed_mass_ledger"]==prior["completed_mass_ledger"]
    assert r["current_candidate_source_sha256"]==s["current_candidate_source_sha256"]
    assert r["current_native_binary_sha256"]==s["current_native_binary_sha256"]
    assert r["current_source_dirty"] is False
    for unit in ("persons","vehicles","cargo_kg"):
        v=r["completed_mass_ledger"][unit]
        assert all(math.isfinite(x) for x in v.values())
        tol=1e-9*max(1.,abs(v["requested"]),abs(v["released"]))
        assert abs(v["requested"]-v["released"]-v["pending"])<=tol
        assert abs(v["released"]-v["completed"]-v["active"])<=tol


def test_keyset_continuous_invoked_four_times_original_guards_have_no_exceeds():
    r=read(FULL)
    for name in (
        "road_work:transfer candidates",
        "road_work:entry interval split",
        "road_work:packet interval packing",
        "road_post:continuous keyset allocation"):
        item=r["trace_sites"][name]
        assert item["exceeded"]==0 and item["calls"]>0
        assert item["max_required"]<=item["limit_at_max"]
    assert r["trace_sites"]["road_post:continuous keyset allocation"]["calls"]==4
    counters=r["trace_counters"]
    assert counters["keyset.continuous_converted"][0]==4
    assert counters["keyset.continuous_saved_bytes"][1]>0
