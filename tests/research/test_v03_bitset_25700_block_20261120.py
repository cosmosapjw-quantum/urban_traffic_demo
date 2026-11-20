"""C8 exact native bitset interval sweep: default vs opt-in physical results.

Default retains byte-identical original 25650 checkpoint; neither allocation
policy reaches 25700, and the failure phases/resource terms are reported without
claiming a 25700 ledger or full V03 acceptance.
"""
import json
from pathlib import Path

from metroflow.v1.native_engine import native_binary_provenance
from tools.run_v1_local_acceptance import candidate_provenance

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT / "artifacts/v03_composed_events_20261120"


def _read(name: str):
    return json.loads((ART / name).read_bytes())


def test_default_and_optin_both_fail_25700_without_relaxing_process_cap():
    source = _read("C8_BITSET_ORIGINAL_DEFAULT_25650.json")
    default = _read("C8_BITSET_DEFAULT_25700.json")
    optin = _read("C8_BITSET_OPTIN_25700.json")
    assert source["status"] == "EXECUTED_SOURCE_BOUND_25650_SCOPED"
    for candidate in (default,optin):
        assert candidate["status"] == "BLOCKED_BudgetExceeded"
        assert candidate["actual_reached_target"] is False
        assert candidate["last_attempt_phase"] == "PHYSICAL_ADVANCE"
        assert candidate["final_checkpoint_sha256"] is None
        assert candidate["final_checkpoint_bytes"] is None
        assert candidate["physical_mass_ledger"] is None
        assert candidate["start_time_s"] == 25650
        assert candidate["target_time_s"] == 25700
        assert candidate["source_case"] == "valley_weekday_s7"
        assert candidate["original_population"] == 100000
        assert candidate["input_checkpoint_sha256"] == source["final_checkpoint_sha256"]
        assert candidate["loaded_native_binary_sha256"] == source["loaded_native_sha256"]
        assert candidate["loaded_candidate_source_sha256"] == source["source_sha256"]
        assert candidate["loaded_native_binary_sha256"] == native_binary_provenance()["sha256"]
        assert candidate["loaded_candidate_source_sha256"] == candidate_provenance()["source_sha256"]
        assert candidate["fixed_original_process_cap_bytes"] == 8 * 1024**3
        assert candidate["process_peak_rss_bytes"] < 8 * 1024**3
        assert candidate["original_full_day_acceptance"] == "BLOCKED_0_OF_9"
        assert candidate["trace_mode"] == "record"
        assert candidate["no_fitted_model_parameters"] is True
    assert default["budget_experimental_mode"] == "OFF"
    assert optin["budget_experimental_mode"] == "source_pair_only"
    assert default["error"]["message"].endswith(
        "phase=transfer candidates, required_bytes=5264786120, budget_bytes=5264781391"
    )
    assert optin["error"]["message"].endswith(
        "phase=interval edges and indexed sweep, required_bytes=5265186936, budget_bytes=5264781391"
    )


def test_interval_bitset_has_smaller_index_work_envelope_but_still_budget_blocked():
    x = _read("C8_BITSET_OPTIN_25700.json")
    old = _read("C6_OPTIN_MARK_25700.json")
    current = x["trace_sites"]["road_work:interval edges and indexed sweep"]
    previous = old["trace_sites"]["road_work:interval edges and indexed sweep"]
    assert current["max_required"] == 5265186936
    assert previous["max_required"] == 5268575872
    assert current["limit_at_max"] == previous["limit_at_max"] == 5264781391
    assert current["max_required"] - current["limit_at_max"] == 405545
    assert previous["max_required"] - previous["limit_at_max"] == 3794481
    assert current["exceeded"] == previous["exceeded"] == 1
    now = current["terms_at_max"]
    before = previous["terms_at_max"]
    assert now["base"] == before["base"] == 1742656808
    assert now["event_bytes"] == before["event_bytes"] == 2351639968
    assert now["incoming_rows"] == before["incoming_rows"] == 7615036
    assert now["extra"] == 3943664
    assert before["extra"] == 12402264
    assert now["interval_retained"] == 192221888
    assert before["interval_retained"] == 187152224
    assert (
        now["base"] + now["event_bytes"] +
        128 * now["incoming_rows"] + now["interval_retained"] +
        now["interval_transient"] + now["extra"]
        == current["max_required"]
    )
    assert old["loaded_native_binary_sha256"] != x["loaded_native_binary_sha256"]
    assert old["input_checkpoint_sha256"] == x["input_checkpoint_sha256"]
    assert x["trace_counters"]["arc.experimental_paired_credit"][1] > 0
