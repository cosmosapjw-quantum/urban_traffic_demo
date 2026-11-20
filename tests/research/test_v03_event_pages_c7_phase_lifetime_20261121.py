"""Source-locked next original physical tick: phase-local flattening blocker."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
A=ROOT/"artifacts/v03_event_pages_20261121"
PREVIOUS=A/"C6_CROSS_NATIVE_25670.json"
NEXT=A/"C7_SAME_NATIVE_25680.json"

def read(p):
    return json.loads(p.read_bytes())

def test_current_native_checkpoint_bytes_and_input_ledger_survive_restart():
    old,new=read(PREVIOUS),read(NEXT)
    assert old["status"]=="EXECUTED_ORIGINAL_100K_NEXT_TICK_CROSS_BINARY"
    assert new["input_checkpoint_sha256"]==old["final_checkpoint_sha256"]
    assert new["input_checkpoint_size_bytes"]==old["final_checkpoint_bytes"]
    assert new["input_mass_ledger"]==old["completed_mass_ledger"]
    assert new["starting_checkpoint_roundtrip_exact"] is True
    assert new["current_candidate_source_sha256"]==old["current_candidate_source_sha256"]
    assert new["current_native_binary_sha256"]==old["current_native_binary_sha256"]
    assert new["current_source_dirty"] is False
    assert new["current_driver_identity"]==old["current_driver_identity"]
    assert new["original_matrix_sha256"]==old["original_matrix_sha256"]
    assert new["native_process_cap_bytes"]==8*1024**3
    assert new["budget_mode"]=="DEFAULT"

def test_all_original_transfer_and_interval_work_complete_before_late_flat_block():
    next=read(NEXT)
    assert next["status"]=="BLOCKED_RESOURCE"
    assert next["start_time_s"]==25670.
    assert next["end_time_s"]==25680.
    assert "event candidate final materialize" in next["error"]["message"]
    for site in ("road_work:transfer candidates","road_work:entry interval split",
                 "road_work:indexed sweep preflight"):
        assert next["trace_sites"][site]["exceeded"]==0
    late=next["trace_sites"]["road_work:event candidate final materialize"]
    assert late["calls"]==1 and late["exceeded"]==1
    assert late["max_required"]==5_416_411_568
    assert late["limit_at_max"]==5_188_657_743
    assert late["max_required"]-late["limit_at_max"]==227_753_825
    assert late["terms_at_max"]["extra"]==682_436_992
    assert next["final_checkpoint_sha256"] is None
    assert next["completed_mass_ledger"] is None
    assert next["completed_time_s"] is None
    assert next["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
