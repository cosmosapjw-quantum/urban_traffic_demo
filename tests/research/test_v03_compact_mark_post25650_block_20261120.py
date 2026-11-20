"""Original default 25,650→25,700 Mark-compressed failure is a retained blocker.

The observed native road allowance is dynamic, not an altered global cap.
No 25,700 checkpoint exists; no success should be synthesized from a failure.
"""
import json
from pathlib import Path
from metroflow.v1.native_engine import native_binary_provenance
from tools.run_v1_local_acceptance import candidate_provenance

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_composed_events_20261120"

def test_mark_native_default_still_blocked_at_25700_with_unmodified_policy():
    r=json.loads((ART/"C3_DEFAULT_MARK_25700.json").read_bytes())
    initial=json.loads((ART/"C2_ORIGINAL_DEFAULT_25650.json").read_bytes())
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
    assert r["error"]["message"]=="native road storage budget exceeded: phase=transfer candidates, required_bytes=5264786120, budget_bytes=5264781391"
    assert r["input_checkpoint_sha256"]==initial["final_checkpoint_sha256"]
    assert r["budget_experimental_mode"]=="OFF"
    assert r["trace_mode"]=="record"
    assert r["fixed_original_process_cap_bytes"]==8*1024**3
    assert r["process_peak_rss_bytes"]<8*1024**3
    assert r["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
    assert r["no_fitted_model_parameters"] is True
    assert r["loaded_candidate_source_sha256"]=="1a55b6e33b4444c909d42b7aff8a7b4b7f4c283a3d077adb95414d51497b77f2"
    assert r["loaded_candidate_source_sha256"]!=candidate_provenance()["source_sha256"]
    assert r["loaded_native_binary_sha256"]=="60bb008b4ef6e34203a625e73193d51f25cf7651ef70ba83594d2c2ae29250ed"
    assert r["loaded_native_binary_sha256"]!=native_binary_provenance()["sha256"]

def test_exact_failed_guard_terms_reconstruct_original_int_budget():
    r=json.loads((ART/"C3_DEFAULT_MARK_25700.json").read_bytes())
    x=r["trace_sites"]["road_work:transfer candidates"]
    t=x["terms_at_max"]
    assert x["max_required"]==5264786120
    assert x["limit_at_max"]==5264781391
    assert x["max_required"]-x["limit_at_max"]==4729
    assert x["exceeded"]==1
    assert t["base"]==2271580008
    assert t["event_bytes"]==2154344800
    assert t["incoming_rows"]==6553604
    # New Mark 16B, original Part 48B, two-copy scratch allowance fixed.
    assert t["base"]+t["event_bytes"]+128*t["incoming_rows"]==x["max_required"]
    assert r["previous_25600_effective_road_phase_allowance_bytes"]==5242806391
    assert r["current_transfer_guard_effective_allowance_bytes"]==5264781391
    assert r["trace_counters"]["arc.experimental_paired_credit"][1]==0
