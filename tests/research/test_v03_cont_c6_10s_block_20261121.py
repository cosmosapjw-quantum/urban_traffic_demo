"""Original Valley 100k source-locked 10s baseline and B128 progression."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PREV=ROOT/"artifacts/v03_persistent_keyset_20261121/C9_SAME_NATIVE_25700.json"
NOW=ROOT/"artifacts/v03_keyset_continuous_20261121/C6_100K_10S_25700.json"
def load(p):return json.loads(p.read_bytes())

def test_checkpoint_origins_and_original_phase_budget_unchanged():
    old,new=load(PREV),load(NOW)
    assert new["starting_checkpoint_roundtrip_exact"] is True
    assert new["input_checkpoint_sha256"]==old["input_checkpoint_sha256"]
    assert new["input_mass_ledger"]==old["input_mass_ledger"]
    assert new["current_driver_identity"]==old["current_driver_identity"]
    assert new["original_matrix_sha256"]==old["original_matrix_sha256"]
    assert new["current_source_dirty"] is False
    assert new["current_candidate_source_sha256"] !=old["current_candidate_source_sha256"]
    assert new["current_native_binary_sha256"]!=old["current_native_binary_sha256"]
    assert new["native_process_cap_bytes"]==8*1024**3
    assert new["budget_mode"]=="DEFAULT"
    assert new["status"]=="BLOCKED_RESOURCE"
    assert new["completed_time_s"] is None
    assert new["final_checkpoint_sha256"] is None
    assert new["original_full_day_acceptance"]=="BLOCKED_0_OF_9"

def test_actual_new_part_mark_page_geometry_progress_but_not_full_tick():
    old,new=load(PREV),load(NOW)
    a=old["trace_sites"]["road_work:transfer candidates"]
    b=new["trace_sites"]["road_work:transfer candidates"]
    assert a["exceeded"]==b["exceeded"]==1
    assert b["calls"]>a["calls"]
    assert a["calls"]==162851 and b["calls"]==163003
    assert a["max_required"]-a["limit_at_max"]==10161
    assert b["max_required"]-b["limit_at_max"]==7377
    assert a["limit_at_max"]==b["limit_at_max"]
    assert new["error"]["phase"]=="PHYSICAL_25690_TO_25700"
    assert "transfer candidates" in new["error"]["message"]
    assert a["terms_at_max"]["incoming_rows"]!=b["terms_at_max"]["incoming_rows"]
