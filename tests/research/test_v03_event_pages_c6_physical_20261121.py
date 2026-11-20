"""Actual 100k Valley FIFO tick and exact event-page candidate evidence."""
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/"artifacts/v03_segmented_incoming_20261121/C8_CROSS_NATIVE_25670.json"
CURRENT=ROOT/"artifacts/v03_event_pages_20261121/C6_CROSS_NATIVE_25670.json"
HISTORICAL=ROOT/"artifacts/v03_compact_lineage_20261120/C7_ORIGINAL_25660.json"


def load(p):
    return json.loads(p.read_bytes())


def test_original_checkpoint_identical_and_complete_current_source_physical_tick():
    old=load(OLD); new=load(CURRENT); src=load(HISTORICAL)
    assert new["schema"]=="V03_SEGMENTED_INCOMING_CROSS_BINARY_NEXT_TICK_V1"
    assert new["input_checkpoint_sha256"]==old["input_checkpoint_sha256"]==src["new_checkpoint_sha256"]
    assert new["input_checkpoint_size_bytes"]==src["new_checkpoint_bytes"]
    assert new["starting_checkpoint_roundtrip_exact"] is True
    assert new["input_mass_ledger"]==src["completed_ledger"]
    assert new["current_driver_identity"]==old["current_driver_identity"]
    assert new["original_matrix_sha256"]==old["original_matrix_sha256"]
    assert new["current_source_dirty"] is False
    assert new["current_candidate_source_sha256"]!=old["current_candidate_source_sha256"]
    assert new["current_native_binary_sha256"]!=old["current_native_binary_sha256"]
    assert new["native_process_cap_bytes"]==8*1024**3
    assert new["budget_mode"]=="DEFAULT"
    assert new["status"]=="EXECUTED_ORIGINAL_100K_NEXT_TICK_CROSS_BINARY"
    assert new["start_time_s"]==25660.
    assert new["end_time_s"]==new["completed_time_s"]==25670.
    assert new["error"] is None
    assert new["original_full_day_acceptance"]=="BLOCKED_0_OF_9"


def test_three_original_mass_ledgers_conserved_at_completed_tick():
    row=load(CURRENT)
    for unit in ("persons","vehicles","cargo_kg"):
        v=row["completed_mass_ledger"][unit]
        atol=1e-9*max(1.,abs(v["requested"]),abs(v["released"]))
        assert all(math.isfinite(t) for t in v.values())
        assert abs(v["requested"]-(v["released"]+v["pending"]))<=atol
        assert abs(v["released"]-(v["completed"]+v["active"]))<=atol
    assert row["final_checkpoint_bytes"]==2_210_069_010
    assert row["final_checkpoint_sha256"]=="a3c0c3ef0cfe9859374fd1446513d2346d53a3cb33ac78a0d15edbcbc97319ab"


def test_old_entry_guard_cleared_and_event_page_allocations_real():
    old=load(OLD); new=load(CURRENT)
    assert old["trace_sites"]["road_work:entry interval split"]["exceeded"]==1
    for name in ("road_work:transfer candidates","road_work:entry interval split",
                 "road_work:indexed sweep preflight",
                 "road_work:event candidate final materialize"):
        site=new["trace_sites"][name]
        assert site["calls"]>0 and site["exceeded"]==0
        assert site["max_required"]<=site["limit_at_max"]
    before=old["trace_sites"]["road_work:transfer candidates"]
    after=new["trace_sites"]["road_work:transfer candidates"]
    assert before["calls"]==after["calls"]==143944
    assert before["terms_at_max"]["incoming_rows"]==after["terms_at_max"]["incoming_rows"]
    assert before["max_required"]-after["max_required"]==1_164_396_424
    c0=old["trace_sites"]["road_actual:transfer buffers"]["terms_at_max"]
    c1=new["trace_sites"]["road_actual:transfer buffers"]["terms_at_max"]
    assert c0["events_len"]==c1["events_len"]==9_100_145
    assert c0["events_cap"]==16_777_216
    assert c1["events_cap"]==9_101_312
    assert (c0["events_cap"]-c1["events_cap"])*64==491_257_856
    assert new["trace_counters"]["split.in_rows"][0]>=1080
