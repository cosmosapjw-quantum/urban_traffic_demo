"""Original Valley 100k genuinely completed 50s continuous physics and capture gate."""
import json
import math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
A=ROOT/"artifacts/v03_quantile_capture_20261121/C6_ORIGINAL_100K_REQUESTED_80S.json"
OLD=ROOT/"artifacts/v03_fifo_closure_20261121/C9_ORIGINAL_100K_REQUESTED_80S.json"
BASE=ROOT/"artifacts/v03_packet_lifetime_20261121/C10_ORIGINAL_100K_10S_25700.json"

def read(p):return json.loads(p.read_bytes())

def test_original_valley_full_100k_50s_contiguous_checkpoint_and_mass_ledger():
    r=read(A);old=read(OLD);baseline=read(BASE)
    assert r["status"]=="BLOCKED_RESOURCE_WITH_VALID_PREFIX"
    assert r["start_time_s"]==old["start_time_s"]==25650.
    assert r["requested_duration_s"]==80
    assert r["valid_advanced_duration_s"]==50.
    assert r["completed_time_s"]==25700.
    assert r["blocked_target_time_s"]==25710.
    assert [x["completed_time_s"] for x in r["completed_step_wall_s"]]==[
        25660.,25670.,25680.,25690.,25700.]
    assert all(x["wall_s"]>0 for x in r["completed_step_wall_s"])
    assert r["previous_checkpoint_cross_native"] is True
    assert r["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert r["original_candidate_from_time_zero_verified"] is False
    assert r["native_process_cap_bytes"]==8*1024**3
    assert r["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
    assert r["final_checkpoint_bytes"]==baseline["final_checkpoint_bytes"]==3_405_043_386
    assert r["final_checkpoint_sha256"]==baseline["final_checkpoint_sha256"]
    assert r["completed_mass_ledger"]==baseline["completed_mass_ledger"]
    for unit in ("persons","vehicles","cargo_kg"):
        x=r["completed_mass_ledger"][unit]
        assert all(math.isfinite(y) for y in x.values())
        eps=1e-9*max(1.,abs(x["released"]),abs(x["requested"]))
        assert abs(x["requested"]-x["released"]-x["pending"])<=eps
        assert abs(x["released"]-x["completed"]-x["active"])<=eps
    assert r["peak_rss_bytes"]<8*1024**3

def test_new_source_real_capture_owner_credit_exactly_closes_prior_phase():
    r=read(A);old=read(OLD)
    assert old["valid_advanced_duration_s"]==40.
    assert old["blocked_target_time_s"]==25700.
    assert "capture/validation" in old["error"]["message"]
    cap=r["trace_sites"]["engine_admission:capture/validation"]
    assert cap["calls"]==5 and cap["exceeded"]==0
    assert cap["max_required"]==5_907_600_205
    assert cap["limit_at_max"]==6_442_450_944
    assert cap["terms_at_max"]["verified_future_capture_arc_credit"]==577_973_296
    assert 6_485_573_501-cap["max_required"]==577_973_296
    assert r["trace_counters"]["arc.experimental_paired_credit"]==[6,0,0]
    assert r["trace_counters"]["engine_admission.verified_future_capture_arc_credit"][2]==577_973_296

def test_new_25710_guard_cannot_be_claimed_as_60s_or_80s_success():
    r=read(A)
    guard=r["trace_sites"]["road_work:transfer candidates"]
    assert guard["exceeded"]==1
    assert guard["max_required"]==4_939_778_752
    assert guard["limit_at_max"]==4_939_690_935
    assert guard["max_required"]-guard["limit_at_max"]==87_817
    assert r["error"]["phase"]=="ADVANCE_TO_25710"
    assert "transfer candidates" in r["error"]["message"]
    assert len(r["completed_step_wall_s"])==5
    assert r["wall_total_including_full_preparation_and_checkpoint_io_s"]>sum(
        x["wall_s"] for x in r["completed_step_wall_s"])
