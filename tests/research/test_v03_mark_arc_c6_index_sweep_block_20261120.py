"""C6 experimental Arc-pair credit combined with exact compact Marks.

Native source and input are the SAME as C3 default. Failure is a tested result,
not acceptance of the full day or proof about all dynamic junction states.
"""
import json
from pathlib import Path

from metroflow.v1.native_engine import native_binary_provenance
from tools.run_v1_local_acceptance import candidate_provenance

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts/v03_composed_events_20261120"


def test_same_source_optin_is_blocked_in_interval_indexed_sweep():
    default = json.loads((ART / "C3_DEFAULT_MARK_25700.json").read_bytes())
    candidate = json.loads((ART / "C6_OPTIN_MARK_25700.json").read_bytes())
    assert default["status"] == candidate["status"] == "BLOCKED_BudgetExceeded"
    assert default["budget_experimental_mode"] == "OFF"
    assert candidate["budget_experimental_mode"] == "source_pair_only"
    assert default["source_case"] == candidate["source_case"] == "valley_weekday_s7"
    assert default["input_checkpoint_sha256"] == candidate["input_checkpoint_sha256"]
    assert default["loaded_native_binary_sha256"] == candidate["loaded_native_binary_sha256"]
    assert candidate["loaded_native_binary_sha256"] == native_binary_provenance()["sha256"]
    assert candidate["loaded_candidate_source_sha256"] == candidate_provenance()["source_sha256"]
    assert candidate["original_population"] == default["original_population"] == 100000
    assert candidate["start_time_s"] == 25650
    assert candidate["target_time_s"] == 25700
    assert candidate["actual_reached_target"] is False
    assert candidate["final_checkpoint_sha256"] is None
    assert candidate["final_checkpoint_bytes"] is None
    assert candidate["physical_mass_ledger"] is None
    assert candidate["original_full_day_acceptance"] == "BLOCKED_0_OF_9"
    assert candidate["no_fitted_model_parameters"] is True


def test_exact_index_sweep_resource_terms_and_no_global_cap_relaxation():
    r = json.loads((ART / "C6_OPTIN_MARK_25700.json").read_bytes())
    trace = r["trace_sites"]["road_work:interval edges and indexed sweep"]
    assert r["error"]["class"] == "BudgetExceeded"
    assert r["error"]["stage"] == "PHYSICAL_ADVANCE"
    assert trace["exceeded"] == 1
    assert trace["max_required"] == 5268575872
    assert trace["limit_at_max"] == 5264781391
    assert trace["max_required"] - trace["limit_at_max"] == 3794481
    terms = trace["terms_at_max"]
    assert terms["base"] == 1742656808
    assert terms["event_bytes"] == 2351639968
    assert terms["incoming_rows"] == 7615036
    assert terms["interval_retained"] == 187152224
    assert terms["interval_transient"] == 0
    assert terms["extra"] == 12402264
    assert (
        terms["base"] + terms["event_bytes"] + terms["incoming_rows"] * 128
        + terms["interval_retained"] + terms["interval_transient"] + terms["extra"]
        == trace["max_required"]
    )
    assert r["fixed_original_process_cap_bytes"] == 8 * 1024**3
    assert r["process_peak_rss_bytes"] < r["fixed_original_process_cap_bytes"]
    assert r["previous_25600_effective_road_phase_allowance_bytes"] == 5242806391
    assert r["current_transfer_guard_effective_allowance_bytes"] == 5264781391
    assert r["trace_counters"]["arc.experimental_paired_credit"][1] > 0
