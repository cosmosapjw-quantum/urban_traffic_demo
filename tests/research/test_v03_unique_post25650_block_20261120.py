"""C10 original 100k Valley 25650→25700: bounded opt-in negative evidence.

Source-locked finite assertion, not a V03 full-day acceptance or proof of
unsafe resource accounting. Distinguishes the engine's changing per-road
phase allowance from unchanged original overall process cap and policy.
"""
import json
from pathlib import Path

from metroflow.v1.native_engine import native_binary_provenance
from tools.run_v1_local_acceptance import candidate_provenance

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_fifo_unique_accounting_20261120"


def _record():
    return json.loads((ART/"C10_PAIR_POST25650_25700.json").read_bytes())


def test_actual_25650_to_25700_does_not_reach_target():
    r=_record()
    prior=json.loads((ART/"C8_PAIR_EXPERIMENT_25650.json").read_bytes())
    assert r["status"]=="BLOCKED_BudgetExceeded"
    assert r["actual_reached_target"] is False
    assert r["last_attempt_phase"]=="PHYSICAL_ADVANCE"
    assert r["start_time_s"]==25650.0
    assert r["target_time_s"]==25700.0
    assert r["original_population"]==100000
    assert r["source_case"]=="valley_weekday_s7"
    assert r["final_checkpoint_sha256"] is None
    assert r["final_checkpoint_bytes"] is None
    assert r["physical_mass_ledger"] is None
    assert r["error"]["class"]=="BudgetExceeded"
    assert r["error"]["stage"]=="PHYSICAL_ADVANCE"
    assert r["input_checkpoint_sha256"]==prior["final_checkpoint_sha256"]
    assert r["input_checkpoint_bytes"]==prior["checkpoint_bytes"]
    assert r["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
    assert r["no_fitted_model_parameters"] is True
    assert r["budget_experimental_mode"]=="source_pair_only"
    assert r["trace_mode"]=="record"


def test_dynamic_road_phase_allowance_is_not_a_relaxed_global_cap():
    r=_record()
    x=r["trace_sites"]["road_work:transfer candidates"]
    assert r["previous_25600_effective_road_phase_allowance_bytes"]==5242806391
    assert r["current_transfer_guard_effective_allowance_bytes"]==5264781391
    assert x["max_required"]==5264847112
    assert x["limit_at_max"]==5264781391
    assert x["max_required"]-x["limit_at_max"]==65721
    assert x["exceeded"]==1
    t=x["terms_at_max"]
    assert t["base"]==1742656808
    assert t["event_bytes"]==2329821664
    assert t["incoming_rows"]==7452304
    assert t["interval_retained"]==0
    assert t["interval_transient"]==0
    assert t["extra"]==0
    assert t["base"]+t["event_bytes"]+160*t["incoming_rows"]==x["max_required"]
    assert r["fixed_original_process_cap_bytes"]==8*1024**3
    assert r["process_peak_rss_bytes"]<r["fixed_original_process_cap_bytes"]


def test_real_25650_input_packet_census_and_source_identity():
    r=_record()
    trace=r["trace_counters"]
    assert trace["arc.experimental_paired_credit"]==[1,528923200,528923200]
    assert trace["tick.cell_packets"][2]==310031
    assert trace["tick.cell_parts"][2]==16528850
    b=r["initial_road_debug"]["arc_backing_census"]
    c=r["initial_road_debug"]["arc_committed_snapshot_union_census"]
    assert b["owner_count"]==b["unique_backing_count"]==310031
    assert b["owner_payload_bytes"]==b["unique_payload_bytes"]==528923200
    assert b["duplicate_payload_bytes"]==0
    assert c["owner_count"]==620062
    assert c["unique_backing_count"]==310031
    assert c["duplicate_payload_bytes"]==528923200
    assert r["loaded_candidate_source_sha256"]==candidate_provenance()["source_sha256"]
    assert r["loaded_native_binary_sha256"]==native_binary_provenance()["sha256"]
    assert r["original_matrix_sha256"]==json.loads((ART/"C8_PAIR_EXPERIMENT_25650.json").read_bytes())["original_matrix_sha256"]
