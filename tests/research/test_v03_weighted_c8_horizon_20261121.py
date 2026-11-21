"""Actual Valley 100000 physical 80s request, valid first 50s and source SHA."""
import json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
A=ROOT/"artifacts/v03_weighted_fifo_20261121"
OLD=ROOT/"artifacts/v03_quantile_capture_20261121/C6_ORIGINAL_100K_REQUESTED_80S.json"
def load(p):return json.loads(p.read_bytes())
def test_80s_request_preserves_only_50s_single_native_valid_physics():
    x=load(A/"C8_100K_REQUESTED_80S_FROM_25650.json")
    old=load(OLD)
    assert x["status"]=="BLOCKED_RESOURCE_WITH_VALID_PREFIX"
    assert x["start_time_s"]==25650. and x["requested_duration_s"]==80
    assert x["valid_advanced_duration_s"]==50.
    assert x["completed_time_s"]==25700.
    assert x["blocked_target_time_s"]==25710.
    assert x["previous_checkpoint_cross_native"] is True
    assert x["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert x["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
    assert x["native_process_cap_bytes"]==8*1024**3
    assert [z["completed_time_s"] for z in x["completed_step_wall_s"]]==[
       25660.,25670.,25680.,25690.,25700.]
    assert all(math.isfinite(z["wall_s"]) and z["wall_s"]>0 for z in x["completed_step_wall_s"])
    assert x["wall_total_including_full_preparation_and_checkpoint_io_s"]>sum(z["wall_s"] for z in x["completed_step_wall_s"])
    assert x["peak_rss_bytes"]<8*1024**3
    assert x["final_checkpoint_bytes"]==old["final_checkpoint_bytes"]==3405043386
    assert x["final_checkpoint_sha256"]==old["final_checkpoint_sha256"]
    assert x["completed_mass_ledger"]==old["completed_mass_ledger"]
    assert x["current_native_binary_sha256"]!=old["current_native_binary_sha256"]
    assert x["current_candidate_source_sha256"]!=old["current_candidate_source_sha256"]
def test_next_10s_reject_keeps_full_source_scratch_in_real_packet_phase():
    x=load(A/"C8_100K_REQUESTED_80S_FROM_25650.json")
    t=x["trace_sites"]["road_work:transfer candidates"]
    assert t["calls"]>1_000_000 and t["exceeded"]==0
    assert t["terms_at_max"]["transfer_exclusive_cell_scratch"]==135413952
    pack=x["trace_sites"]["road_work:packet interval packing"]
    assert pack["exceeded"]==1
    assert pack["terms_at_max"]["transfer_exclusive_cell_scratch"]==0
    assert pack["terms_at_max"]["base"]==pack["terms_at_max"]["full_source_base"]
    assert pack["max_required"]==4940342832
    assert pack["limit_at_max"]==4939690935
    assert pack["max_required"]-pack["limit_at_max"]==651897
    assert "packet interval packing" in x["error"]["message"]
