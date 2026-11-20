"""Same compiled original V03: default vs opt-in compact Mark 25700 blockers.

Neither is a completed 25700 physics step or an original full-day run.
"""
import json
from pathlib import Path
from metroflow.v1.native_engine import native_binary_provenance
from tools.run_v1_local_acceptance import candidate_provenance

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_composed_events_20261120"


def test_pair_credit_reaches_interval_sweep_but_still_does_not_finish_25700():
    optin=json.loads((ART/"C6_OPTIN_MARK_25700.json").read_bytes())
    default=json.loads((ART/"C3_DEFAULT_MARK_25700.json").read_bytes())
    assert default["status"]==optin["status"]=="BLOCKED_BudgetExceeded"
    assert default["budget_experimental_mode"]=="OFF"
    assert optin["budget_experimental_mode"]=="source_pair_only"
    assert default["input_checkpoint_sha256"]==optin["input_checkpoint_sha256"]
    assert default["loaded_candidate_source_sha256"]==optin["loaded_candidate_source_sha256"]=="1a55b6e33b4444c909d42b7aff8a7b4b7f4c283a3d077adb95414d51497b77f2"
    assert optin["loaded_candidate_source_sha256"]!=candidate_provenance()["source_sha256"]
    assert default["loaded_native_binary_sha256"]==optin["loaded_native_binary_sha256"]=="60bb008b4ef6e34203a625e73193d51f25cf7651ef70ba83594d2c2ae29250ed"
    assert optin["loaded_native_binary_sha256"]!=native_binary_provenance()["sha256"]
    assert optin["actual_reached_target"] is False
    assert optin["physical_mass_ledger"] is None
    assert optin["final_checkpoint_sha256"] is None
    assert optin["target_time_s"]==25700
    assert optin["error"]["class"]=="BudgetExceeded"
    assert optin["last_attempt_phase"]=="PHYSICAL_ADVANCE"
    assert default["original_full_day_acceptance"]==optin["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
    assert optin["fixed_original_process_cap_bytes"]==8*1024**3
    assert optin["trace_mode"]=="record"
    assert optin["trace_counters"]["arc.experimental_paired_credit"][1]>0
    assert default["trace_counters"]["arc.experimental_paired_credit"][1]==0


def test_original_budget_interval_sweep_failure_terms_are_exact_and_nonnegative():
    r=json.loads((ART/"C6_OPTIN_MARK_25700.json").read_bytes())
    x=r["trace_sites"]["road_work:interval edges and indexed sweep"]
    t=x["terms_at_max"]
    assert x["max_required"]==5268575872
    assert x["limit_at_max"]==5264781391
    assert x["max_required"]-x["limit_at_max"]==3794481
    assert x["exceeded"]==1
    assert t["base"]==1742656808
    assert t["event_bytes"]==2351639968
    assert t["incoming_rows"]==7615036
    assert t["interval_retained"]==187152224
    assert t["interval_transient"]==0
    assert t["extra"]==12402264
    assert (
        t["base"]+t["event_bytes"]+128*t["incoming_rows"]+
        t["interval_retained"]+t["interval_transient"]+t["extra"]
    )==x["max_required"]
    assert r["process_peak_rss_bytes"]<8*1024**3
    assert r["previous_25600_effective_road_phase_allowance_bytes"]==5242806391
    assert r["current_transfer_guard_effective_allowance_bytes"]==5264781391
