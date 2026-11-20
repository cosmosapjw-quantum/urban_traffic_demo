"""Matched original Valley checkpoint proof for paired incoming Part+Mark pages."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
A=ROOT/"artifacts/v03_segmented_incoming_20261121"
BEFORE=A/"C6_CROSS_NATIVE_25670.json"
AFTER=A/"C8_CROSS_NATIVE_25670.json"


def load(path):
    return json.loads(path.read_bytes())


def test_exact_original_checkpoint_and_cross_binary_physical_contract():
    first, second=load(BEFORE),load(AFTER)
    assert first["input_checkpoint_sha256"]==second["input_checkpoint_sha256"]
    assert first["input_checkpoint_size_bytes"]==second["input_checkpoint_size_bytes"]
    assert first["starting_checkpoint_roundtrip_exact"] is True
    assert second["starting_checkpoint_roundtrip_exact"] is True
    assert first["input_mass_ledger"]==second["input_mass_ledger"]
    assert first["current_driver_identity"]==second["current_driver_identity"]
    assert first["original_matrix_sha256"]==second["original_matrix_sha256"]
    assert first["current_source_dirty"] is False
    assert second["current_source_dirty"] is False
    assert first["current_native_binary_sha256"]!=second["current_native_binary_sha256"]
    assert first["current_candidate_source_sha256"]!=second["current_candidate_source_sha256"]
    assert second["native_process_cap_bytes"]==8*1024**3
    assert second["budget_mode"]=="DEFAULT"

def test_matched_transfer_source_proves_actual_mark_reallocation_removed():
    x,y=load(BEFORE),load(AFTER)
    old=x["trace_sites"]["road_work:transfer candidates"]
    new=y["trace_sites"]["road_work:transfer candidates"]
    assert old["calls"]==new["calls"]==143944
    assert old["exceeded"]==new["exceeded"]==0
    assert old["terms_at_max"]["event_bytes"]==new["terms_at_max"]["event_bytes"]
    assert old["terms_at_max"]["incoming_rows"]==new["terms_at_max"]["incoming_rows"]==8992612
    assert old["max_required"]-new["max_required"]==135462496
    oldcap=x["trace_sites"]["road_actual:transfer buffers"]["terms_at_max"]
    newcap=y["trace_sites"]["road_actual:transfer buffers"]["terms_at_max"]
    assert oldcap["incoming_len"]==newcap["incoming_len"]==8941884
    assert oldcap["marks_cap"]==12959072
    assert newcap["marks_cap"]==newcap["incoming_cap"]==8977280
    assert (oldcap["marks_cap"]-newcap["marks_cap"])*16==63708672
    assert newcap["marks_cap"]-newcap["incoming_len"]<=63*1586

def test_new_original_physical_progress_and_next_guard_kept_blocked():
    x,y=load(BEFORE),load(AFTER)
    assert y["trace_counters"]["split.in_rows"][0]==1079
    assert x["trace_counters"]["split.in_rows"][0]==94
    p=x["trace_sites"]["road_work:entry interval split"]
    q=y["trace_sites"]["road_work:entry interval split"]
    assert q["calls"]>p["calls"]
    assert q["calls"]==311246
    assert q["max_required"]==5228908816
    assert q["limit_at_max"]==5228906583
    assert q["max_required"]-q["limit_at_max"]==2233
    assert q["exceeded"]==1
    assert y["status"]=="BLOCKED_RESOURCE"
    assert "entry interval split" in y["error"]["message"]
    assert y["completed_time_s"] is None
    assert y["completed_mass_ledger"] is None
    assert y["final_checkpoint_sha256"] is None
    assert y["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
