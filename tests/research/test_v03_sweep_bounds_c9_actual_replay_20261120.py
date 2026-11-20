"""Original Valley 100k physical gate progression with exact merged edges."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/"artifacts/v03_sweep_live_bounds_20261120/C6_CROSS_BINARY_25700.json"
CURRENT=ROOT/"artifacts/v03_sweep_live_bounds_20261120/C9_CROSS_BINARY_25700.json"

def load(p):
    return json.loads(p.read_bytes())

def test_same_original_valley_source_and_checkpoint_replay():
    a,b=load(OLD),load(CURRENT)
    assert a["roundtrip_wire_identity"] is True
    assert b["roundtrip_wire_identity"] is True
    assert a["input_checkpoint_sha256"] == b["input_checkpoint_sha256"]
    assert a["old_driver_identity"] == b["old_driver_identity"] == b["current_driver_identity"]
    assert a["matrix_sha256"]==b["matrix_sha256"]
    assert a["current_native_binary_sha256"]!=b["current_native_binary_sha256"]
    assert a["current_source_sha256"]!=b["current_source_sha256"]
    assert b["process_address_space_cap_bytes"]==8*1024**3
    assert b["status"]=="BLOCKED_RESOURCE"
    assert b["final_checkpoint_sha256"] is None
    assert b["final_ledger"] is None
    assert b["original_V03_full_day_acceptance"]=="BLOCKED_0_OF_9"

def test_actual_old_entry_split_guard_cleared_new_index_preflight_blocks():
    a,b=load(OLD),load(CURRENT)
    x=a["trace_sites"]["road_work:entry interval split"]
    y=b["trace_sites"]["road_work:entry interval split"]
    assert x["exceeded"]==1
    assert y["exceeded"]==0
    assert x["calls"]==69501
    assert y["calls"]==78000
    assert b["trace_counters"]["split.in_rows"][0]==94
    assert a["trace_counters"]["split.in_rows"][0]==80
    assert b["trace_counters"]["split.out_rows"][1]>a["trace_counters"]["split.out_rows"][1]
    z=b["trace_sites"]["road_work:indexed sweep preflight"]
    assert z["calls"]==95 and z["exceeded"]==1
    assert z["max_required"]==5266719968
    assert z["limit_at_max"]==5264781423
    assert z["max_required"] - z["limit_at_max"]==1938545
    terms=z["terms_at_max"]
    assert terms["interval_transient"]==0
    assert (terms["base"]+terms["event_bytes"]+terms["incoming_rows"]*128+
        terms["interval_retained"]+terms["interval_transient"]+
        terms["extra"]==z["max_required"])
    assert b["completed_time_s"] is None
    assert "indexed sweep preflight" in b["error"]["message"]
