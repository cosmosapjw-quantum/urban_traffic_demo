"""Actual original Valley 100k cross-native sweep guard progression, no false release."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/"artifacts/v03_event_arc_20261120/C9_POINT_CORE_25700.json"
CURRENT=ROOT/"artifacts/v03_sweep_live_bounds_20261120/C6_CROSS_BINARY_25700.json"
def load(p): return json.loads(p.read_bytes())

def test_exact_source_and_original_fifo_gate_comparison():
    old,new=load(OLD),load(CURRENT)
    assert old["roundtrip_wire_identity"] and new["roundtrip_wire_identity"]
    assert old["input_checkpoint_sha256"]==new["input_checkpoint_sha256"]
    assert old["old_driver_identity"] == new["old_driver_identity"] == new["current_driver_identity"]
    assert new["current_native_binary_sha256"]!=old["current_native_binary_sha256"]
    assert new["current_source_sha256"]!=old["current_source_sha256"]
    assert new["process_address_space_cap_bytes"]==old["process_address_space_cap_bytes"]==8*1024**3
    assert new["status"]=="BLOCKED_RESOURCE"
    assert new["final_checkpoint_sha256"] is None and new["final_ledger"] is None
    assert new["original_V03_full_day_acceptance"]=="BLOCKED_0_OF_9"

def test_real_structural_scratch_reduction_but_new_segment_not_complete():
    old,new=load(OLD),load(CURRENT)
    a=old["trace_sites"]["road_work:interval edges and indexed sweep"]
    b=new["trace_sites"]["road_work:interval edges and indexed sweep"]
    assert a["calls"]==b["calls"]==81
    assert a["exceeded"]==b["exceeded"]==0
    assert a["terms_at_max"]["extra"]-b["terms_at_max"]["extra"]==5821400
    x=old["trace_sites"]["road_work:entry interval split"]
    y=new["trace_sites"]["road_work:entry interval split"]
    assert x["calls"]==66798
    assert y["calls"]==69501
    assert y["calls"]>x["calls"]
    assert y["max_required"]-y["limit_at_max"]==2481
    assert y["exceeded"]>=1
    assert y["terms_at_max"]["interval_transient"]<x["terms_at_max"]["interval_transient"]
    assert y["terms_at_max"]["interval_retained"]>x["terms_at_max"]["interval_retained"]
    assert "entry interval split" in new["error"]["message"]
    assert new["completed_time_s"] is None
