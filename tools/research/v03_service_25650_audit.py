#!/usr/bin/env python3
"""Read-only audit of original 25600->25650 native budget failures.

Does not re-run the expensive ~53s cases; reads source-bound real receipts
after both old/Arc engines independently attempted exactly the same target.
Classifies structural/native preflight separately from actual process RSS.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"src")]

from tools.run_v1_local_acceptance import candidate_provenance
from metroflow.v1.native_engine import native_binary_provenance


def audit(root:Path=ROOT)->dict:
    root=Path(root).resolve()
    art=root/"artifacts/v03_fifo_service_stream_20261120"
    a=art/"stress"
    previous=json.loads((a/"old_prearc_25650.json").read_bytes())
    arc=json.loads((a/"arc_25650.json").read_bytes())
    prep=json.loads((art/"C8_ARC_PREP_VERIFIED.json").read_bytes())
    original=json.loads((art/"prefix/valley_weekday_s7.native_stream_25600.json").read_bytes())
    bridge=json.loads((art/"arc_prefix/C9_ARC_PHYSICAL_REPLAY.json").read_bytes())
    live_src=candidate_provenance()
    live_bin=native_binary_provenance()
    if live_src.get("status")!="MEASURED" or live_src.get("source_dirty") is not False:
        raise ValueError("new source is dirty or not measured")
    if live_bin.get("status")!="MEASURED":
        raise ValueError("native library not identified")
    if prep["current_candidate_source_sha256"]!=live_src["source_sha256"] or (
       prep["current_native_sha256"]!=live_bin["sha256"]):
        raise ValueError("C8 release preparation is stale for this native source")
    if (arc["source_sha256"]!=live_src["source_sha256"] or
        arc["native_binary_sha256"]!=live_bin["sha256"]):
        raise ValueError("Arc stress run not from current source/native")
    if previous["native_binary_sha256"]!=original["native_binary_sha256"]:
        raise ValueError("old comparison binary differs from original C5 source")
    if previous["source_sha256"]!=original["candidate_source_sha256"]:
        raise ValueError("old source physical reference is stale")
    if previous["source_checkpoint_sha256"]!=arc["source_checkpoint_sha256"] or (
       previous["source_checkpoint_sha256"]!=bridge["new_arc_checkpoint_sha256"] or
       previous["driver_identity"]!=arc["driver_identity"]):
        raise ValueError("old and Arc did not begin from bit-identical physical state")
    if previous["matrix_sha256"]!=arc["matrix_sha256"]:
        raise ValueError("physical matrix differs")
    result={}
    for run in (previous,arc):
        variant=run["variant"]
        if variant in result:
            raise ValueError("duplicate variant")
        e=re.search(r"phase=([^,]+), required_bytes=(\d+), budget_bytes=(\d+)",run["error"] or "")
        if e is None:
            raise ValueError("not the expected native storage budget diagnostic")
        required=int(e.group(2))
        cap=int(e.group(3))
        if not (required>cap>0):
            raise ValueError("invalid structural budget diagnosis")
        if run["status"]!="FAILED_BudgetExceeded" or run["final_checkpoint_sha256"] is not None or (
           run["final_time_s"] is not None):
            raise ValueError("budget failure being confused with successful full step")
        if not (0<run["process_peak_rss_bytes"]<run["process_address_space_limit_bytes"]==8*1024**3):
            raise ValueError("process RSS exhaustion vs structural budget not distinguished")
        if (run["initial_time_s"],run["target_time_s"],run["resident_stock"])!=(25600.0,25650.0,100000):
            raise ValueError("source clock or original population changed")
        if not run["source_roundtrip_byte_identical"]:
            raise ValueError("source native checkpoint could not roundtrip")
        result[variant]={
            "status":run["status"],
            "error_phase":e.group(1),
            "native_required_bytes":required,
            "native_budget_bytes":cap,
            "native_excess_bytes":required-cap,
            "process_rss_bytes":run["process_peak_rss_bytes"],
            "process_address_space_limit_bytes":run["process_address_space_limit_bytes"],
            "elapsed_s":run["elapsed_s"],
            "source_sha256":run["source_sha256"],
            "loaded_native_binary_sha256":run["native_binary_sha256"],
            "original_25600_checkpoint_sha256":run["source_checkpoint_sha256"],
            "receipt_sha256":hashlib.sha256((a/(("old_prearc" if variant=="old" else variant)+"_25650.json")).read_bytes()).hexdigest(),
        }
    old=result["old"];candidate=result["arc"]
    if old["native_budget_bytes"]!=candidate["native_budget_bytes"]:
        raise ValueError("candidate changed the original internal storage ceiling")
    if (old["error_phase"]!=candidate["error_phase"] or
        old["error_phase"]!="packet interval packing"):
        raise ValueError("not comparing the same native packet packing failure type")

    source=(root/"crates/metroflow-rust/src/v1_road.rs").read_text()
    static_support=(
        "out.vector_capacity_bytes += packet.parts.allocated_bytes();" in source and
        "rows: Arc<Vec<CorePart>>" in source and
        "Mixed(Arc<Vec<Part>>)" in source
    )
    if not static_support:
        raise ValueError("source no longer supports stated conservative Arc accounting risk")
    result_obj={
       "schema":"V03_ARC_25650_BUDGET_BLOCK_DIAGNOSTIC_20261120_V1",
       "status":"BOTH_FAILED_INTERNAL_PACKET_PACKING_BUDGET",
       "old_and_candidate_source_checkpoint_byte_identical":True,
       "original_case":"valley_weekday_s7",
       "original_residents":100000,
       "attempted_simulated_interval_s":[25600,25650],
       "physical_target_reached_by_either":False,
       "two_variants":result,
       "arc_rss_saved_bytes":old["process_rss_bytes"]-candidate["process_rss_bytes"],
       "arc_rss_saved_fraction":1-candidate["process_rss_bytes"]/old["process_rss_bytes"],
       "arc_elapsed_relative_to_old":candidate["elapsed_s"]/old["elapsed_s"],
       "structural_budget_same_bytes":old["native_budget_bytes"],
       "original_process_8GiB_cap_unchanged":True,
       "original_source_plan_19_of_21":True,
       "actual_current_native_3_city_calendar_prep":"3_OF_3",
       "original_24hour_9_run_acceptance":"0_OF_9_BLOCKED",
       "source_supported_potential_Arc_duplicate_part_capacity_count":static_support,
       "causal_attribution_Arc_double_count_caused_25650_failure":"UNRESOLVED",
       "causal_attribution_distinct_packet_genealogy_growth":"SUPPORTED_BY_PRIOR_TRACE_NOT_PROVED_SOLE_CAUSE",
       "not_claimed":"Both executions terminated before the 25650 checkpoint; no physical output at that exact clock was verified.",
       "next_scientific_action":"Derive/test unique Arc backing allocation accounting and exact packet genealogy compression under unchanged physical FIFO/clock/8GiB limit; do not inflate budget.",
    }
    return result_obj


def main()->None:
    result=audit()
    out=ROOT/"artifacts/v03_fifo_service_stream_20261120/C10_25650_STRESS_VERDICT.json"
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n")
    print(json.dumps({
        "old_excess_bytes":result["two_variants"]["old"]["native_excess_bytes"],
        "arc_excess_bytes":result["two_variants"]["arc"]["native_excess_bytes"],
        "arc_rss_saved_MB":round(result["arc_rss_saved_bytes"]/10**6,3),
        "arc_time_ratio":round(result["arc_elapsed_relative_to_old"],5),
        "V03":"BLOCKED_0_OF_9"
    },sort_keys=True))


if __name__=="__main__":
    main()
