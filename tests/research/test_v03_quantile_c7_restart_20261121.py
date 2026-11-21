"""Exact current native restart from the physically completed 50s Valley prefix."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
LAST=ROOT/"artifacts/v03_quantile_capture_20261121/C6_ORIGINAL_100K_REQUESTED_80S.json"
NEXT=ROOT/"artifacts/v03_quantile_capture_20261121/C7_100K_FROM_25700_REQUESTED_20S.json"

def load(p):return json.loads(p.read_bytes())

def test_prior_full_50s_checkpoint_is_legitimate_precise_input_to_20s():
    old,new=load(LAST),load(NEXT)
    assert old["status"]=="BLOCKED_RESOURCE_WITH_VALID_PREFIX"
    assert old["valid_advanced_duration_s"]==50.0
    assert old["completed_time_s"]==25700.0
    assert new["admitted_last_valid_previous_50s_prefix"] is True
    assert new["status"]=="BLOCKED_RESOURCE"
    assert new["start_time_s"]==25700.0
    assert new["requested_duration_s"]==20
    assert new["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert new["previous_full_checkpoint_sha256"]==old["final_checkpoint_sha256"]
    assert new["previous_full_checkpoint_bytes"]==old["final_checkpoint_bytes"]==3_405_043_386
    assert new["previous_mass_ledger"]==old["completed_mass_ledger"]
    assert new["current_candidate_source_sha256"]==old["current_candidate_source_sha256"]
    assert new["current_native_binary_sha256"]==old["current_native_binary_sha256"]
    assert new["native_process_cap_bytes"]==8*1024**3
    assert new["original_full_day_acceptance"]=="BLOCKED_0_OF_9"

def test_first_unresolved_after_25700_is_resource_block_not_20s_success():
    p=load(NEXT)
    assert p["valid_advanced_duration_s"]==0.0
    assert p["completed_time_s"]==25700.0
    assert p["blocked_target_time_s"]==25710.0
    assert p["error"]["class"]=="BudgetExceeded"
    assert "transfer candidates" in p["error"]["message"]
    t=p["trace_sites"]["road_work:transfer candidates"]
    assert t["exceeded"]==1
    assert t["max_required"]==5_025_413_352
    assert t["limit_at_max"]==5_025_214_575
    assert t["max_required"]-t["limit_at_max"]==198_777
    assert p["final_checkpoint_sha256"] is None
    assert p["completed_step_wall_s"]==[]
