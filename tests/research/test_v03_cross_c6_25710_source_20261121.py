"""Real original Valley 100k exact page-bound replay, 25710 still blocked."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/"artifacts/v03_packet_lifetime_20261121/C10_100K_CONTINUOUS_20S.json"
NEW=ROOT/"artifacts/v03_cross_call_20261121/C6_100K_CROSS_NATIVE_25710.json"
ORIGINAL=ROOT/"artifacts/v03_packet_lifetime_20261121/C10_ORIGINAL_100K_10S_25700.json"


def read(path):
    return json.loads(path.read_bytes())


def test_source_sha_locked_original_100k_25700_checkpoint_and_physical_ledger():
    old,new,input_state=read(OLD),read(NEW),read(ORIGINAL)
    assert old["status"]==new["status"]=="BLOCKED_RESOURCE"
    assert new["input_checkpoint_sha256"]==input_state["final_checkpoint_sha256"]
    assert new["input_checkpoint_size_bytes"]==input_state["final_checkpoint_bytes"]==3405043386
    assert new["starting_checkpoint_roundtrip_exact"] is True
    assert new["input_mass_ledger"]==input_state["completed_mass_ledger"]
    assert new["current_driver_identity"]==input_state["current_driver_identity"]
    assert new["original_matrix_sha256"]==input_state["original_matrix_sha256"]
    assert new["current_candidate_source_sha256"]!=input_state["current_candidate_source_sha256"]
    assert new["current_native_binary_sha256"]!=input_state["current_native_binary_sha256"]
    assert new["current_source_dirty"] is False
    assert new["native_process_cap_bytes"]==8*1024**3
    assert new["budget_mode"]=="DEFAULT"
    assert new["start_time_s"]==25700.0
    assert new["end_time_s"]==25710.0
    assert new["original_full_day_acceptance"]=="BLOCKED_0_OF_9"


def test_old_guard_capacity_bound_not_a_complete_25710_tick():
    old,new=read(OLD),read(NEW)
    x=old["trace_sites"]["road_work:transfer candidates"]
    y=new["trace_sites"]["road_work:transfer candidates"]
    assert x["calls"]==90399 and y["calls"]==90411
    assert x["max_required"]-x["limit_at_max"]==6609
    assert y["max_required"]==5025350520
    assert y["limit_at_max"]==x["limit_at_max"]==5025214575
    assert y["max_required"]-y["limit_at_max"]==135945
    assert y["terms_at_max"]["incoming_rows"]>x["terms_at_max"]["incoming_rows"]
    assert y["exceeded"]==1
    assert new["completed_time_s"] is None
    assert new["completed_mass_ledger"] is None
    assert new["final_checkpoint_sha256"] is None
    assert "transfer candidates" in new["error"]["message"]
