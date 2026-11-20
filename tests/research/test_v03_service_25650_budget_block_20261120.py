"""Original V03 25650 stress evidence: real failure is structural, not RSS cap.

Does not infer exact failure tick or a 25650 checkpoint; neither run reached it.
"""
import hashlib
import json
from pathlib import Path

from tools.research.v03_service_25650_audit import audit

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_fifo_service_stream_20261120"


def test_two_source_matched_25650_runs_both_hit_original_internal_packing_budget():
    x=audit(ROOT)
    assert x["status"]=="BOTH_FAILED_INTERNAL_PACKET_PACKING_BUDGET"
    assert x["old_and_candidate_source_checkpoint_byte_identical"] is True
    assert x["attempted_simulated_interval_s"]==[25600,25650]
    assert x["physical_target_reached_by_either"] is False
    assert x["original_residents"]==100000
    assert x["original_24hour_9_run_acceptance"]=="0_OF_9_BLOCKED"
    assert x["actual_current_native_3_city_calendar_prep"]=="3_OF_3"
    assert x["original_source_plan_19_of_21"] is True
    old=x["two_variants"]["old"]
    arc=x["two_variants"]["arc"]
    assert old["status"]==arc["status"]=="FAILED_BudgetExceeded"
    assert old["error_phase"]==arc["error_phase"]=="packet interval packing"
    assert old["native_budget_bytes"]==arc["native_budget_bytes"]==5242806391
    assert old["native_excess_bytes"]==4041
    assert arc["native_excess_bytes"]==4873
    assert old["original_25600_checkpoint_sha256"]==arc["original_25600_checkpoint_sha256"]
    assert old["source_sha256"]!=arc["source_sha256"]


def test_arc_reduces_real_peak_rss_but_not_structural_budget_blocker():
    x=audit(ROOT)
    old=x["two_variants"]["old"]
    arc=x["two_variants"]["arc"]
    assert old["process_rss_bytes"]==3640336384
    assert arc["process_rss_bytes"]==3273211904
    assert x["arc_rss_saved_bytes"]==367124480
    assert 0.09<x["arc_rss_saved_fraction"]<0.11
    assert old["process_rss_bytes"]<old["process_address_space_limit_bytes"]==8*1024**3
    assert arc["process_rss_bytes"]<arc["process_address_space_limit_bytes"]==8*1024**3
    assert arc["native_required_bytes"]>arc["native_budget_bytes"]
    assert old["native_required_bytes"]>old["native_budget_bytes"]
    assert x["causal_attribution_Arc_double_count_caused_25650_failure"]=="UNRESOLVED"
    assert x["physical_target_reached_by_either"] is False


def test_stress_receipts_are_original_files_not_fabricated_release_success():
    r=json.loads((ART/"C10_25650_STRESS_VERDICT.json").read_bytes())
    assert r["status"]=="BOTH_FAILED_INTERNAL_PACKET_PACKING_BUDGET"
    for kind,name in (("old","old_prearc"),("arc","arc")):
        p=ART/"stress"/(name+"_25650.json")
        payload=json.loads(p.read_bytes())
        assert hashlib.sha256(p.read_bytes()).hexdigest()==r["two_variants"][kind]["receipt_sha256"]
        assert payload["final_checkpoint_sha256"] is None
        assert payload["final_time_s"] is None
        assert payload["original_24h_accepted"] is False
        assert payload["original_release_runs_completed"]==0
        assert payload["new_fitted_physical_parameters"]==[]
        assert payload["source_roundtrip_byte_identical"] is True
        assert payload["source_checkpoint_sha256"]=="75bae0ea200a0bd3fd0842770efd0cecec9ce6297179149db88f77ded91b134d"
