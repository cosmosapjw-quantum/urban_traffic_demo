"""Original Valley 100k exact destination-page replay and later interval bound."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/"artifacts/v03_cross_call_20261121/C6_100K_CROSS_NATIVE_25710.json"
NEW=ROOT/"artifacts/v03_cross_call_20261121/C8_100K_CROSS_NATIVE_25710.json"
CHECKPOINT=ROOT/"artifacts/v03_packet_lifetime_20261121/C10_ORIGINAL_100K_10S_25700.json"
def load(p):return json.loads(p.read_bytes())

def test_same_original_checkpoint_source_wire_and_ledger():
    a,b,p=load(OLD),load(NEW),load(CHECKPOINT)
    assert a["status"]==b["status"]=="BLOCKED_RESOURCE"
    assert a["input_checkpoint_sha256"]==b["input_checkpoint_sha256"]==p["final_checkpoint_sha256"]
    assert b["input_checkpoint_size_bytes"]==p["final_checkpoint_bytes"]==3405043386
    assert b["starting_checkpoint_roundtrip_exact"] is True
    assert b["input_mass_ledger"]==p["completed_mass_ledger"]
    assert b["current_driver_identity"]==p["current_driver_identity"]
    assert b["original_matrix_sha256"]==p["original_matrix_sha256"]
    assert b["current_candidate_source_sha256"]!=a["current_candidate_source_sha256"]
    assert b["current_native_binary_sha256"]!=a["current_native_binary_sha256"]
    assert b["current_source_dirty"] is False
    assert b["native_process_cap_bytes"]==8*1024**3
    assert b["budget_mode"]=="DEFAULT"

def test_physical_transfer_page_expansion_cleared_but_packet_interval_stopped():
    a,b=load(OLD),load(NEW)
    prev=a["trace_sites"]["road_work:transfer candidates"]
    transfer=b["trace_sites"]["road_work:transfer candidates"]
    assert prev["calls"]==90411 and prev["exceeded"]==1
    assert transfer["calls"]==97050 and transfer["exceeded"]==0
    assert transfer["terms_at_max"]["incoming_live_pages"]==68334
    assert transfer["terms_at_max"]["incoming_rows"]==8735538
    assert transfer["terms_at_max"]["incoming_actual_page_charge"]==496534896
    late=b["trace_sites"]["road_work:packet interval packing"]
    assert late["calls"]==17116
    assert late["exceeded"]==1
    assert late["max_required"]==5025214752
    assert late["limit_at_max"]==5025214575
    assert late["max_required"]-late["limit_at_max"]==177
    assert late["terms_at_max"]["incoming_live_pages"]==68334
    assert b["completed_time_s"] is None
    assert b["completed_mass_ledger"] is None
    assert b["final_checkpoint_sha256"] is None
    assert b["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
