"""Source-bound exact V03 100k original time-window and resource receipts."""
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
A=ROOT/"artifacts/v03_cross_call_20261121"
NEW=A/"C10_POSTFIX_100K_CROSS_NATIVE_25710.json"
OLD=A/"C8_100K_CROSS_NATIVE_25710.json"
LONG=A/"C10_100K_ESCALATING_80S_FROM_25650.json"
ORIGINAL=ROOT/"artifacts/v03_packet_lifetime_20261121/C10_ORIGINAL_100K_10S_25700.json"
OLD25690=ROOT/"artifacts/v03_persistent_keyset_20261121/C8_KEYSET_CROSS_BINARY_25690.json"

def read(p):return json.loads(p.read_bytes())

def test_true_checkpoint_identity_clean_native_original_cap_and_ledger():
    a,b,old=read(OLD),read(NEW),read(ORIGINAL)
    assert b["status"]=="BLOCKED_RESOURCE"
    assert b["input_checkpoint_sha256"]==a["input_checkpoint_sha256"]==old["final_checkpoint_sha256"]
    assert b["input_checkpoint_size_bytes"]==old["final_checkpoint_bytes"]==3405043386
    assert b["input_mass_ledger"]==old["completed_mass_ledger"]
    assert b["starting_checkpoint_roundtrip_exact"] is True
    assert b["current_driver_identity"]==old["current_driver_identity"]
    assert b["original_matrix_sha256"]==old["original_matrix_sha256"]
    assert b["native_process_cap_bytes"]==8*1024**3
    assert b["budget_mode"]=="DEFAULT"
    assert b["current_source_dirty"] is False
    assert b["current_native_binary_sha256"]!=a["current_native_binary_sha256"]
    assert b["current_candidate_source_sha256"]!=a["current_candidate_source_sha256"]
    assert b["original_full_day_acceptance"]=="BLOCKED_0_OF_9"

def test_packet_remainder_guard_cleared_using_real_physical_descriptors():
    a,b=read(OLD),read(NEW)
    prior=a["trace_sites"]["road_work:packet interval packing"]
    now=b["trace_sites"]["road_work:packet interval packing"]
    assert prior["calls"]==now["calls"]==17116
    assert prior["exceeded"]==1
    assert now["exceeded"]==0
    assert now["terms_at_max"]["incoming_descriptors_frozen"]==1
    assert now["terms_at_max"]["incoming_actual_descriptor_bytes"]==4702272
    assert now["max_required"]<now["limit_at_max"]
    later=b["trace_sites"]["road_work:transfer candidates"]
    assert later["calls"]==97051 and later["exceeded"]==1
    assert later["max_required"]==5025219784
    assert later["limit_at_max"]==5025214575
    assert later["max_required"]-later["limit_at_max"]==5209
    assert b["completed_time_s"] is None
    assert b["completed_mass_ledger"] is None
    assert b["final_checkpoint_sha256"] is None

def test_original_100k_requested_80s_has_exact_40sec_valid_uninterrupted_prefix():
    r,old=read(LONG),read(OLD25690)
    assert r["status"]=="BLOCKED_RESOURCE_WITH_VALID_PREFIX"
    assert r["start_time_s"]==25650.
    assert r["requested_duration_s"]==80
    assert r["valid_advanced_duration_s"]==40.
    assert r["completed_time_s"]==25690.
    assert r["blocked_target_time_s"]==25700.
    assert [v["completed_time_s"] for v in r["completed_step_wall_s"]]==[25660.,25670.,25680.,25690.]
    assert len(r["completed_step_wall_s"])==4
    assert all(math.isfinite(v["wall_s"]) and v["wall_s"]>0 for v in r["completed_step_wall_s"])
    assert r["wall_total_including_full_preparation_and_checkpoint_io_s"]>sum(
        v["wall_s"] for v in r["completed_step_wall_s"])
    assert r["peak_rss_bytes"]<8*1024**3
    assert r["previous_checkpoint_cross_native"] is True
    assert r["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert r["original_candidate_from_time_zero_verified"] is False
    assert r["final_checkpoint_sha256"]==old["final_checkpoint_sha256"]
    assert r["final_checkpoint_bytes"]==old["final_checkpoint_bytes"]==2949231402
    assert r["completed_mass_ledger"]==old["completed_mass_ledger"]
    assert "transfer candidates" in r["error"]["message"]
    assert r["trace_sites"]["road_work:transfer candidates"]["exceeded"]==1
    assert r["trace_sites"]["road_work:transfer candidates"]["max_required"]-(
        r["trace_sites"]["road_work:transfer candidates"]["limit_at_max"])==22657
    assert r["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
