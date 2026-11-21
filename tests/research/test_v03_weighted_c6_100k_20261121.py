"""Original 100k actual transfer-phase fix and bounded later blocker.
All evidence comes from original binary + native trace, not a mock.
"""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/"artifacts/v03_quantile_capture_20261121/C7_100K_FROM_25700_REQUESTED_20S.json"
FIX=ROOT/"artifacts/v03_weighted_fifo_20261121/C6_ORIGINAL_100K_25710.json"
START=ROOT/"artifacts/v03_packet_lifetime_20261121/C10_ORIGINAL_100K_10S_25700.json"
def read(p):return json.loads(p.read_bytes())
def test_same_100k_physical_input_unchanged_caps_and_source_contract():
    a,b,source=read(BASE),read(FIX),read(START)
    assert b["status"]=="BLOCKED_RESOURCE"
    assert b["start_time_s"]==25700.0 and b["end_time_s"]==25710.0
    assert b["starting_checkpoint_roundtrip_exact"] is True
    assert b["input_checkpoint_sha256"]==source["final_checkpoint_sha256"]
    assert b["input_checkpoint_size_bytes"]==source["final_checkpoint_bytes"]==3405043386
    assert b["input_mass_ledger"]==source["completed_mass_ledger"]
    assert b["original_matrix_sha256"]==source["original_matrix_sha256"]
    assert b["current_driver_identity"]==source["current_driver_identity"]
    assert b["current_source_dirty"] is False
    assert b["budget_mode"]=="DEFAULT" and b["native_process_cap_bytes"]==8*1024**3
    assert b["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
    assert b["current_candidate_source_sha256"]!=a["current_candidate_source_sha256"]
    assert b["current_native_binary_sha256"]!=a["current_native_binary_sha256"]

def test_original_transfer_scratch_released_only_at_transfer_phase():
    prior,new=read(BASE),read(FIX)
    old=prior["trace_sites"]["road_work:transfer candidates"]
    t=new["trace_sites"]["road_work:transfer candidates"]
    assert old["calls"]==188168 and old["exceeded"]==1
    assert t["calls"]==196190 and t["exceeded"]==0
    assert t["terms_at_max"]["transfer_exclusive_cell_scratch"]==135413952
    assert t["terms_at_max"]["full_source_base"]-t["terms_at_max"]["base"]==135413952
    assert t["max_required"]<=t["limit_at_max"]
    assert prior["input_checkpoint_sha256"] if "input_checkpoint_sha256" in prior else True

def test_next_packet_phase_keeps_original_full_scratch_reservation():
    r=read(FIX)
    phase=r["trace_sites"]["road_work:packet interval packing"]
    assert phase["exceeded"]==1 and phase["calls"]==28374
    assert phase["terms_at_max"]["transfer_exclusive_cell_scratch"]==0
    assert phase["terms_at_max"]["base"]==phase["terms_at_max"]["full_source_base"]
    assert phase["max_required"]==5035896816
    assert phase["limit_at_max"]==5025214575
    assert phase["max_required"]-phase["limit_at_max"]==10682241
    assert r["completed_time_s"] is None
    assert r["final_checkpoint_sha256"] is None
    assert r["completed_mass_ledger"] is None
