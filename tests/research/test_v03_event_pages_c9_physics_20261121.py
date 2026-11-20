"""New candidate source-bound original 100k 25680 physics and corrected memory-lifetime gate."""
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
A=ROOT/"artifacts/v03_event_pages_20261121"
OLD_ORIGIN=A/"C6_CROSS_NATIVE_25670.json"
OLD_FAILED=A/"C7_SAME_NATIVE_25680.json"
NEW_COMPLETE=A/"C9_CROSS_NATIVE_25680.json"

def read(p):
    return json.loads(p.read_bytes())

def test_exact_original_input_25670_and_complete_cross_native_25680():
    old=read(OLD_ORIGIN); fail=read(OLD_FAILED); new=read(NEW_COMPLETE)
    assert fail["status"]=="BLOCKED_RESOURCE"
    assert new["status"]=="EXECUTED_ORIGINAL_100K_25680_CROSS_BINARY"
    assert new["input_checkpoint_sha256"]==old["final_checkpoint_sha256"]
    assert new["input_checkpoint_size_bytes"]==old["final_checkpoint_bytes"]
    assert new["starting_checkpoint_roundtrip_exact"] is True
    assert new["input_mass_ledger"]==old["completed_mass_ledger"]
    assert new["current_driver_identity"]==old["current_driver_identity"]
    assert new["original_matrix_sha256"]==old["original_matrix_sha256"]
    assert new["previous_candidate_source_sha256"]==old["current_candidate_source_sha256"]
    assert new["previous_native_binary_sha256"]==old["current_native_binary_sha256"]
    assert new["current_candidate_source_sha256"]!=old["current_candidate_source_sha256"]
    assert new["current_native_binary_sha256"]!=old["current_native_binary_sha256"]
    assert new["current_source_dirty"] is False
    assert new["cross_binary_origin"] is True
    assert new["native_process_cap_bytes"]==8*1024**3
    assert new["start_time_s"]==25670.
    assert new["end_time_s"]==new["completed_time_s"]==25680.
    assert new["error"] is None
    assert new["original_full_day_acceptance"]=="BLOCKED_0_OF_9"

def test_25680_original_persons_vehicles_cargo_kg_ledgers_and_file_bits():
    done=read(NEW_COMPLETE)
    assert done["final_checkpoint_bytes"]==2_552_318_466
    assert done["final_checkpoint_sha256"]=="db1e7f59e46385863f8cbbbf56586ca3d0a49d72a43f86d0c884e9fdbbea553a"
    for unit in ("persons","vehicles","cargo_kg"):
        val=done["completed_mass_ledger"][unit]
        assert all(math.isfinite(x) for x in val.values())
        tol=1e-9*max(1.,abs(val["requested"]),abs(val["released"]))
        assert abs(val["requested"]-val["released"]-val["pending"])<=tol
        assert abs(val["released"]-val["completed"]-val["active"])<=tol

def test_only_road_work_lifetime_dropped_not_flat_event_storage():
    fail,now=read(OLD_FAILED),read(NEW_COMPLETE)
    old=fail["trace_sites"]["road_work:event candidate final materialize"]
    assert old["exceeded"]==1
    assert old["max_required"]-old["limit_at_max"]==227_753_825
    for name in ("road_work:transfer candidates","road_work:entry interval split",
                 "road_work:indexed sweep preflight"):
        row=now["trace_sites"][name]
        assert row["exceeded"]==0
        assert row["calls"]>0
    post=now["trace_sites"]["road_post:event candidate materialize after road"]
    assert post["calls"]==1 and post["exceeded"]==0
    assert post["max_required"]==3_894_396_408
    assert post["limit_at_max"]==5_188_657_743
    t=post["terms_at_max"]
    assert t["flat_event_rows"]==10_663_078
    assert t["paged_event_slots"]==10_665_984
    assert t["committed_input_event_bytes"]==582_409_280
    assert post["max_required"]==(t["retained_road_owners"]
            +t["committed_input_event_bytes"]+t["paged_event_slots"]*64
            +t["page_descriptor_slots"]*24+t["flat_event_rows"]*64+96)
    assert now["trace_counters"]["split.in_rows"]==fail["trace_counters"]["split.in_rows"]
    assert now["trace_counters"]["entry.raw_rows"]==fail["trace_counters"]["entry.raw_rows"]
