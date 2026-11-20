"""Original Valley 100k cross-native proof: segmented incoming clears transfer guard."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/"artifacts/v03_compact_lineage_20261120/C8_CURRENT_SOURCE_25670.json"
CURRENT=ROOT/"artifacts/v03_segmented_incoming_20261121/C6_CROSS_NATIVE_25670.json"
OLD_SUCCESS=ROOT/"artifacts/v03_compact_lineage_20261120/C7_ORIGINAL_25660.json"

def load(path):
    return json.loads(path.read_bytes())

def test_new_native_uses_same_100k_checkpoint_and_exact_wire():
    x=load(CURRENT); prev=load(OLD_SUCCESS)
    assert x["schema"]=="V03_SEGMENTED_INCOMING_CROSS_BINARY_NEXT_TICK_V1"
    assert x["input_checkpoint_sha256"]==prev["new_checkpoint_sha256"]
    assert x["input_checkpoint_size_bytes"]==prev["new_checkpoint_bytes"]
    assert x["input_mass_ledger"]==prev["completed_ledger"]
    assert x["starting_checkpoint_roundtrip_exact"] is True
    assert x["cross_binary_origin"] is True
    assert x["previous_candidate_source_sha256"]==prev["current_candidate_sha256"]
    assert x["previous_native_binary_sha256"]==prev["current_native_sha256"]
    assert x["current_candidate_source_sha256"]!=prev["current_candidate_sha256"]
    assert x["current_native_binary_sha256"]!=prev["current_native_sha256"]
    assert x["current_source_dirty"] is False
    assert x["current_driver_identity"]==prev["current_driver_identity"]
    assert x["native_process_cap_bytes"]==8*1024**3
    assert x["budget_mode"]=="DEFAULT"

def test_actual_old_transfer_guard_cleared_and_new_split_guard_is_recorded():
    before=load(OLD); after=load(CURRENT)
    a=before["trace_sites"]["road_work:transfer candidates"]
    b=after["trace_sites"]["road_work:transfer candidates"]
    assert a["exceeded"]==1 and b["exceeded"]==0
    assert b["calls"]>a["calls"]
    s=after["trace_sites"]["road_work:entry interval split"]
    terms=s["terms_at_max"]
    assert s["exceeded"]==1 and s["calls"]>0
    assert s["max_required"]==5228909104
    assert s["limit_at_max"]==5228906583
    assert s["max_required"]-s["limit_at_max"]==2521
    rows=terms["incoming_rows"]
    cells=1586
    page_bound=rows*80+48*63*cells+48*(rows//64+int(rows%64!=0)+cells)
    assert s["max_required"]==(
        terms["base"]+terms["event_bytes"]+page_bound+
        terms["interval_retained"]+terms["interval_transient"]+terms["extra"]
    )
    assert after["status"]=="BLOCKED_RESOURCE"
    assert "entry interval split" in after["error"]["message"]
    assert after["completed_time_s"] is None
    assert after["final_checkpoint_sha256"] is None
    assert after["completed_mass_ledger"] is None
    assert after["original_full_day_acceptance"]=="BLOCKED_0_OF_9"

def test_real_paged_allocation_is_not_a_fictitious_alias_credit():
    x=load(CURRENT)
    row=x["trace_sites"]["road_actual:transfer buffers"]
    t=row["terms_at_max"]
    assert t["incoming_cap"]>=t["incoming_len"]>0
    assert t["incoming_cap"]-t["incoming_len"] <= 63*1586
    assert t["charged_incoming"]>=t["incoming_len"]
    assert t["marks_cap"]>=t["incoming_len"]
    assert row["exceeded"]==0
    assert x["trace_counters"]["split.in_rows"][0]>0
