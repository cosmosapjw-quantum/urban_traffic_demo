#!/usr/bin/env python3
"""Source-bound ORIGINAL V03 readiness after test-only lineage shadow prototype.

No change to original physics, resident demand, acceptance thresholds or
traffic coefficients. This tool refuses stale binary/source receipts and
distinguishes local checkpoint bytes from mere upstream receipt statements.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"src")]

from metroflow.v1.v03_readiness import assess_v03_readiness
from metroflow.v1.native_engine import native_binary_provenance
from tools.run_v1_local_acceptance import candidate_provenance


BASE="8e891b907f3f85e9ae8ff7c86a1b8836f4341815"
ROOT_MAIN="01c80b432344f94209daaa198bb1eb007839fc7f"
ART="artifacts/v03_fifo_lineage_coding_20261119"
SOURCE_PATH="crates/metroflow-rust/src/v1_road.rs"
TEST_HOOK=(
    "// Shadow-only experiment; the original V03 road kernel and checkpoint layout\n"
    "// remain unchanged in non-test native builds.\n"
    "#[cfg(test)]\n"
    '#[path = "v1_lineage_shadow.rs"]\n'
    "mod lineage_shadow;\n"
)


def _sha_bytes(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def _load(path:Path)->dict:
    return json.loads(path.read_bytes())


def _git(root:Path,*args:str)->str:
    return subprocess.check_output(
        ("git",*args),cwd=root,stderr=subprocess.DEVNULL,text=True).strip()


def audit_current(root:Path)->dict:
    root=Path(root).resolve()
    if not root.is_dir():
        raise ValueError("source root not available")
    artifact=root/ART
    matrix_file=root/"scenarios/v1/release_matrix.json"
    plan_file=root/"docs/v1/PLAN.json"
    matrix=_load(matrix_file)
    plan=_load(plan_file)
    matrix_sha=_sha_bytes(matrix_file)
    current_source=candidate_provenance()
    current_binary=native_binary_provenance()
    if (current_source.get("status")!="MEASURED" or
        current_binary.get("status")!="MEASURED" or
        current_source.get("source_dirty") is not False):
        raise ValueError("current source/native content identity not clean and measurable")
    current_source_sha=current_source["source_sha256"]
    current_native_sha=current_binary["sha256"]
    if not (len(current_source_sha)==len(current_native_sha)==64):
        raise ValueError("unusable native/source SHA identities")

    new_receipts=[]
    per_city={}
    for case in matrix["cases"]:
        key=case["id"]
        file=artifact/"preparation"/(key+".prepare.json")
        receipt=_load(file)
        if receipt.get("case")!=key:
            raise ValueError("whole original city case binding differs")
        new_receipts.append(receipt)
        cal=receipt.get("calendar",{})
        live=(receipt.get("candidate_source_sha256")==current_source_sha and
              receipt.get("native_binary_sha256")==current_native_sha and
              receipt.get("matrix_sha256")==matrix_sha)
        per_city[key]={
           "status":receipt.get("status"),
           "planned_leg_records":cal.get("legs"),
           "resident_stock":cal.get("resident_stock"),
           "wall_s":receipt.get("wall_s"),
           "peak_rss_bytes":receipt.get("peak_rss_bytes"),
           "source_binary_sha_matches_live":live,
           "receipt_sha256":_sha_bytes(file),
        }

    readiness=assess_v03_readiness(
        plan,matrix,matrix_sha256=matrix_sha,
        preparation_receipts=new_receipts,
        live_candidate_source_sha256=current_source_sha,
        live_native_binary_sha256=current_native_sha,
    )
    if readiness["v03"]["calendar_preparation_verified"]!=len(matrix["cases"]):
        raise ValueError("current-source original 100k preparation not fully verified")
    if not all(x["source_binary_sha_matches_live"] for x in per_city.values()):
        raise ValueError("current native/source release preparation mismatch")
    if not all(x["status"]=="WHOLE_CALENDAR_PREPARED" and x["resident_stock"]==100000
               for x in per_city.values()):
        raise ValueError("original full-city demand or preparation status mismatch")
    total_legs=sum(x["planned_leg_records"] for x in per_city.values())

    # The previously published binary and source SHA receipts are intentionally
    # stale after the new isolated research branch introduces the shadow code.
    previous_receipts=[
        _load(root/"artifacts/v03_fifo_interval_sweep_20261119/preparation"/
              (case["id"]+".prepare.json")) for case in matrix["cases"]
    ]
    prior=assess_v03_readiness(
        plan,matrix,matrix_sha256=matrix_sha,
        preparation_receipts=previous_receipts,
        live_candidate_source_sha256=current_source_sha,
        live_native_binary_sha256=current_native_sha,
    )
    old_credit=prior["v03"]["calendar_preparation_verified"]

    original_path=root/SOURCE_PATH
    original_text=subprocess.check_output(
        ("git","show",f"{BASE}:{SOURCE_PATH}"),
        cwd=root,stderr=subprocess.DEVNULL,
    ).decode("utf-8")
    current_text=original_path.read_text()
    only_test_guard=(
        current_text.count(TEST_HOOK)==1 and
        current_text.replace(TEST_HOOK,"")==original_text
    )
    if not only_test_guard:
        raise ValueError("original native road source differs beyond cfg(test) shadow guard")
    # The original unmodified main is available on the authorized user's
    # remote machine. A clean clone elsewhere should not invent a local
    # main-checkout comparison when that separate directory is absent.
    original_main=root.parents[1]/"Dropbox"/"personal_projects"/"urban_traffic_demo"
    original_main_status="NOT_ACCESSIBLE_ON_THIS_HOST"
    if original_main.is_dir():
        if _git(original_main,"rev-parse","HEAD")!=ROOT_MAIN:
            raise ValueError("original production main checkout SHA changed")
        original_main_status="VERIFIED_UNCHANGED"

    original_reference=_load(
        root/"artifacts/v03_fifo_interval_sweep_20261119/prefix/"
             "valley_weekday_s7.native_sweep_25300.json"
    )
    new_receipt_file=artifact/"prefix/valley_weekday_s7.native_shadow_25300.json"
    new_physical=_load(new_receipt_file)
    same_ledger=(
        original_reference["report"]["execution"]["ledger"]==
        new_physical["report"]["execution"]["ledger"]
    )
    same_calendar=(
        original_reference["report"]["calendar"]==
        new_physical["report"]["calendar"]
    )
    same_checkpoint=(
        original_reference["final_checkpoint_sha256"]==
        new_physical["final_checkpoint_sha256"]
    )
    if not all((same_ledger,same_calendar,same_checkpoint)):
        raise ValueError("original actual 25,300s physics differs from source baseline")
    if (new_physical["status"]!="EXECUTED_FOR_REVIEW" or
        new_physical["simulated_s"]!=25300 or
        new_physical["native_binary_sha256"]!=current_native_sha or
        new_physical["candidate_source_sha256"]!=current_source_sha or
        new_physical["peak_rss_bytes"]>matrix["limits"]["peak_rss_bytes"]):
        raise ValueError("original 100k scoped physics source or resource binding invalid")
    local_binary=artifact/"prefix/valley_weekday_s7.native_shadow_25300.final.bin"
    bytes_verified=False
    if local_binary.is_file():
        if _sha_bytes(local_binary)!=new_physical["final_checkpoint_sha256"]:
            raise ValueError("local original checkpoint binary differs from source receipt")
        bytes_verified=True

    benchmark=_load(artifact/"C8_SYNTHETIC_BENCHMARK.json")
    if len(benchmark["runs"])!=5:
        raise ValueError("original finite shadow prototype benchmark run count differs")
    if _git(root,"branch","--show-current")!="research/v03-fifo-lineage-coding-20261119":
        raise ValueError("wrong research branch for source-bound V03 receipt")
    outcome={
        "schema":"V03_SHADOW_LINEAGE_C10_SOURCE_BOUND_20261120_V1",
        "status":"CURRENT_SOURCE_100K_PREFLIGHT_VERIFIED_PHYSICS_SCOPED",
        "source_branch":"research/v03-fifo-lineage-coding-20261119",
        "source_commit":_git(root,"rev-parse","HEAD"),
        "original_main_commit":ROOT_MAIN,
        "original_main_checkout_status":original_main_status,
        "baseline_source_commit":BASE,
        "candidate_source_sha256":current_source_sha,
        "native_binary_sha256":current_native_sha,
        "matrix_sha256":matrix_sha,
        "source_plan_sha256":_sha_bytes(plan_file),
        "production_original_road_source_byte_equivalence_after_cfg_test_strip":only_test_guard,
        "shadow_module_test_only":True,
        "shadow_default_v03_network_integration":False,
        "readiness":readiness,
        "prepared_residents_per_case":100000,
        "total_planned_leg_records":total_legs,
        "per_city":per_city,
        "old_prep_reused_count":old_credit,
        "old_prep_rejected_count":len(previous_receipts)-old_credit,
        "original_physics_prefix":{
            "source_type":"ORIGINAL_V03_WHOLE_NATIVE",
            "case":"valley_weekday_s7",
            "simulated_s":25300.0,
            "checkpoint_sha256":new_physical["final_checkpoint_sha256"],
            "baseline_checkpoint_sha256":original_reference["final_checkpoint_sha256"],
            "mass_ledger_exact_match":same_ledger,
            "calendar_exact_match":same_calendar,
            "native_binary_is_current":True,
            "local_checkpoint_bytes_verified":bytes_verified,
            "local_checkpoint_retained_in_git":False,
            "wall_s":new_physical["wall_s"],
            "peak_rss_bytes":new_physical["peak_rss_bytes"],
            "original_full_day_accepted":False,
            "source_receipt_sha256":_sha_bytes(new_receipt_file),
        },
        "shadow_synthetic_benchmark":{
            "median_retained_storage_ratio":benchmark["median_storage_ratio"],
            "median_build_only_speed_ratio":benchmark["median_build_speed_ratio"],
            "median_stream_vs_eager_scan_ratio":benchmark["median_stream_vs_eager_scan_ratio"],
            "claim":"synthetic immutable composition sharing, not source-bound whole-city V03 speedup",
        },
        "code_review":{
            "consumer_transactional_rollback":"NOT_IMPLEMENTED",
            "original_destination_priority_adaptor":"NOT_IMPLEMENTED",
            "original_incoming_and_marks_compressed_consumer":"NOT_IMPLEMENTED",
            "checkpoint_native_compact_format":"NOT_IMPLEMENTED",
            "whole_network_FIFO_shadow_integration":"NOT_IMPLEMENTED",
        },
        "original_full_release":"BLOCKED_0_OF_9",
        "unmodified_original_24h_horizon_s":matrix["horizon_s"],
        "unmodified_original_rss_cap_bytes":matrix["limits"]["peak_rss_bytes"],
        "unmodified_original_wall_cap_s":matrix["limits"]["wall_s"],
        "no_fitted_microphysical_or_source_parameters":True,
    }
    return outcome


def main()->None:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output",required=True)
    args=ap.parse_args()
    result=audit_current(ROOT)
    p=Path(args.output)
    p=p if p.is_absolute() else ROOT/p
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    summary={
        "original_DAG":str(result["readiness"]["dag"]["completed"])+"/"+
                       str(result["readiness"]["dag"]["total"]),
        "new_native_3_city_preparation":str(result["readiness"]["v03"]["calendar_preparation_verified"])+"/3",
        "scoped_valley_25300_checkpoint_bit_identity":result["original_physics_prefix"]["mass_ledger_exact_match"] and
            result["original_physics_prefix"]["checkpoint_sha256"]==
            result["original_physics_prefix"]["baseline_checkpoint_sha256"],
        "original_full_day_accepted":"0/9",
        "V03":result["readiness"]["v03"]["status"],
    }
    print(json.dumps(summary,sort_keys=True))


if __name__=="__main__":
    main()
