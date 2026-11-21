"""Original Valley 100k pointer-exact backing source evidence, not final 25710."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/"artifacts/v03_cross_call_20261121/C10_POSTFIX_100K_CROSS_NATIVE_25710.json"
NEW=ROOT/"artifacts/v03_fifo_closure_20261121/C8_ORIGINAL_100K_25710.json"
START=ROOT/"artifacts/v03_packet_lifetime_20261121/C10_ORIGINAL_100K_10S_25700.json"

def read(p):return json.loads(p.read_bytes())

def test_original_binary_full_roundtrip_mass_ledger_and_actual_native():
    old,new,source=read(OLD),read(NEW),read(START)
    assert new["status"]=="BLOCKED_RESOURCE"
    assert new["input_checkpoint_sha256"]==old["input_checkpoint_sha256"]==source["final_checkpoint_sha256"]
    assert new["input_checkpoint_size_bytes"]==source["final_checkpoint_bytes"]==3_405_043_386
    assert new["starting_checkpoint_roundtrip_exact"] is True
    assert new["input_mass_ledger"]==source["completed_mass_ledger"]
    assert new["current_driver_identity"]==old["current_driver_identity"]
    assert new["original_matrix_sha256"]==old["original_matrix_sha256"]
    assert new["current_source_dirty"] is False
    assert new["native_process_cap_bytes"]==8*1024**3
    assert new["budget_mode"]=="DEFAULT"
    assert new["current_candidate_source_sha256"]!=old["current_candidate_source_sha256"]
    assert new["current_native_binary_sha256"]!=old["current_native_binary_sha256"]
    assert new["original_full_day_acceptance"]=="BLOCKED_0_OF_9"

def test_real_one_unique_arc_backing_credit_used_no_experimental_flag():
    old,new=read(OLD),read(NEW)
    assert old["trace_sites"]["road_work:transfer candidates"]["calls"]==97_051
    oldbase=old["trace_sites"]["road_base:components"]
    newbase=new["trace_sites"]["road_base:components"]
    assert oldbase["terms_at_max"]["paired_arc_credit"]==0
    assert newbase["terms_at_max"]["default_pointer_verified_credit"]==577_973_296
    assert newbase["terms_at_max"]["experimental_pointer_verified_credit"]==0
    assert oldbase["max_required"]-newbase["max_required"]==577_973_296
    assert new["trace_counters"]["arc.default_pointer_verified_credit"]==[1,577_973_296,577_973_296]
    assert new["trace_counters"]["arc.experimental_paired_credit"]==[1,0,0]
    # Physical source continues far beyond the old named failure, but remains
    # blocked at a NEW point rather than falsifying the original experiment.
    new_transfer=new["trace_sites"]["road_work:transfer candidates"]
    assert new_transfer["calls"]==188_168>old["trace_sites"]["road_work:transfer candidates"]["calls"]
    assert new_transfer["exceeded"]==1
    assert new_transfer["max_required"]==5_025_413_352
    assert new_transfer["limit_at_max"]==5_025_214_575
    assert new_transfer["max_required"]-new_transfer["limit_at_max"]==198_777
    assert new["completed_time_s"] is None
    assert new["completed_mass_ledger"] is None
    assert new["final_checkpoint_sha256"] is None
