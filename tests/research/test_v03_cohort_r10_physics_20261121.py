"""Measured source-bound original 100k cross-native run: negative acceptance is evidence.

The attempted 80 seconds from 25,700 must not be misreported as physical
completion. Both formerly blocked packet-packing repair and newly identified
transfer-preflight blocker are checked against original budget trace.
"""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_fifo_cohort_20261121"

def test_r10_same_original_100k_checkpoint_cross_native_fails_closed_at_25710():
    prior=json.loads((ART/"R9_original_100k_requested_40s.json").read_text())
    row=json.loads((ART/"R10_cross_native_100k_requested_80s.json").read_text())
    assert row["case"]=="valley_weekday_s7"
    assert row["status"]=="BLOCKED_RESOURCE"
    assert row["error"]["class"]=="BudgetExceeded"
    assert row["error"]["phase"]=="ADVANCE_TO_25710"
    assert "phase=transfer candidates" in row["error"]["message"]
    assert "required_bytes=5025270048" in row["error"]["message"]
    assert "budget_bytes=5025214575" in row["error"]["message"]
    assert row["start_time_s"]==row["completed_time_s"]==25700
    assert row["requested_duration_s"]==80
    assert row["valid_advanced_duration_s"]==0
    assert row["blocked_target_time_s"]==25710
    assert row["final_checkpoint_sha256"] is None
    assert row["previous_full_checkpoint_sha256"]==prior["final_checkpoint_sha256"]
    assert row["previous_full_checkpoint_bytes"]==prior["final_checkpoint_bytes"]
    assert row["previous_mass_ledger"]==prior["completed_mass_ledger"]
    assert row["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert row["cross_native_original_25700_source"] is True
    assert row["previous_checkpoint_cross_native"] is True
    assert row["current_candidate_source_sha256"]!=prior["current_candidate_source_sha256"]
    assert row["current_native_binary_sha256"]!=prior["current_native_binary_sha256"]
    assert row["current_source_dirty"] is False
    assert row["trace_mode"]=="record"
    assert row["native_process_cap_bytes"]==8*1024**3
    assert row["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
    assert row["original_matrix_sha256"]==hashlib.sha256(
        (ROOT/"scenarios/v1/release_matrix.json").read_bytes()).hexdigest()
    assert row["trace_counters"]["arc.experimental_paired_credit"][1]==0

def test_r10_packet_packing_obstacle_removed_in_trace_but_transfer_not_solved():
    row=json.loads((ART/"R10_cross_native_100k_requested_80s.json").read_text())
    sites=row["trace_sites"]
    packet=sites["road_work:packet interval packing"]
    xfer=sites["road_work:transfer candidates"]
    assert packet["calls"]>=31950 and packet["exceeded"]==0
    assert packet["max_required"]<packet["limit_at_max"]
    assert packet["terms_at_max"]["packet_no_active_combine_reserve_replaced"]==135413952
    assert packet["terms_at_max"]["packet_current_live_source_part_bytes"]>0
    assert xfer["calls"]>=232953 and xfer["exceeded"]==1
    assert xfer["max_required"]-xfer["limit_at_max"]==55473
    assert xfer["terms_at_max"]["incoming_descriptors_frozen"]==0
    assert xfer["terms_at_max"]["incoming_rows"]==15438668
    assert xfer["terms_at_max"]["transfer_exclusive_cell_scratch"]==135413952
    assert row["peak_rss_bytes"]<8*1024**3
    assert row["completed_step_wall_s"]==[]
