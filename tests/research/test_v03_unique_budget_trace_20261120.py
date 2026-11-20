"""Actual source-bound 25600->25650 native budget diagnostic, record-only."""
from pathlib import Path
import json
from tools.run_v1_local_acceptance import candidate_provenance
from metroflow.v1.native_engine import native_binary_provenance

ROOT=Path(__file__).resolve().parents[2]
PATH=ROOT/"artifacts/v03_fifo_unique_accounting_20261120/C5_REAL_25650_PHASE_BUDGET_TRACE.json"


def test_actual_structural_failure_reproduces_without_budget_bypass():
    a=json.loads(PATH.read_bytes())
    assert a["trace_mode"]=="record_only_never_observe"
    assert a["status"]=="ORIGINAL_NATIVE_ERROR"
    assert a["trace_alloc_counting_enabled"] is False
    assert a["error"]["type"]=="BudgetExceeded"
    assert "packet interval packing" in a["error"]["message"]
    assert a["original_100k_city"]=="valley_weekday_s7"
    assert a["initial_time_s"]==25600 and a["target_time_s"]==25650
    assert a["original_process_address_space_limit_bytes"]==8*1024**3
    assert a["process_peak_rss_bytes"]<8*1024**3
    assert a["road_work_budget_modified"] is False
    assert a["original_24hour_runs_completed"]==0
    assert a["source_sha256"]==candidate_provenance()["source_sha256"]
    assert a["loaded_native_sha256"]==native_binary_provenance()["sha256"]


def test_failing_term_breakdown_reconstructs_exact_byte_count():
    a=json.loads(PATH.read_bytes())
    guard=a["failing_road_work_guard"]
    terms=guard["terms_at_max"]
    assert guard["exceeded"]==1
    assert guard["limit_at_max"]==5242806391
    assert guard["max_required"]==5242811264
    assert guard["max_required"]-guard["limit_at_max"]==4873
    assert terms["base"]==1980005976
    assert terms["event_bytes"]==2047480928
    assert terms["incoming_rows"]==6751471
    assert terms["interval_retained"]==131126880
    assert terms["interval_transient"]==3955912
    assert terms["extra"]==6208
    # Source type Mark=(usize,f64,f64,f64): 32B, Part=48B, two copies.
    incoming=terms["incoming_rows"]*(2*(48+32))
    total=(terms["base"]+terms["event_bytes"]+incoming+
           terms["interval_retained"]+terms["interval_transient"]+terms["extra"])
    assert incoming==1080235360
    assert total==guard["max_required"]
    assert guard["calls"]==498636
    assert a["all_native_budget_trace_sites"]["road_work:entry interval split"]["calls"]==836307


def test_failed_trace_does_not_promote_full_day_or_physical_25650():
    a=json.loads(PATH.read_bytes())
    assert a["claim_scope"].startswith("failed physical step")
    assert "FAILED" not in a["status"]  # Error is recorded, not reported as success.
    assert a["error"]["message"].startswith("native road storage budget exceeded")
    assert a["trace_counters"]["xfer.partial_serve"][1]==44852
    assert a["trace_counters"]["split.out_rows"][1]==23901798
    assert a["trace_counters"]["tick.cell_parts"][2]==14347276
