#!/usr/bin/env python3
"""Current Arc-backed original V03 100k preflight, no full-day acceptance."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"src")]
from tools.run_v1_local_acceptance import candidate_provenance
from metroflow.v1.native_engine import native_binary_provenance
from metroflow.v1.v03_readiness import assess_v03_readiness


def main()->None:
    art=ROOT/"artifacts/v03_fifo_service_stream_20261120"
    matrix_file=ROOT/"scenarios/v1/release_matrix.json"
    matrix_bytes=matrix_file.read_bytes()
    matrix=json.loads(matrix_bytes)
    plan=json.loads((ROOT/"docs/v1/PLAN.json").read_bytes())
    source=candidate_provenance()
    native=native_binary_provenance()
    if source.get("status")!="MEASURED" or source.get("source_dirty") is not False:
        raise ValueError("candidate source identity missing or dirty")
    if native.get("status")!="MEASURED":
        raise ValueError("compiled native identity missing")
    sha=hashlib.sha256(matrix_bytes).hexdigest()
    receipts=[]
    city={}
    for case in matrix["cases"]:
        name=case["id"]
        f=art/"arc_preparation"/(name+".prepare.json")
        receipt=json.loads(f.read_bytes())
        if receipt["case"]!=name:
            raise ValueError("misbound source case")
        receipts.append(receipt)
        city[name]={
            "planned_legs":receipt["calendar"]["legs"],
            "resident_stock":receipt["calendar"]["resident_stock"],
            "wall_s":receipt["wall_s"],
            "peak_rss_bytes":receipt["peak_rss_bytes"],
            "status":receipt["status"],
            "native_sha256":receipt["native_binary_sha256"],
            "source_sha256":receipt["candidate_source_sha256"],
            "receipt_sha256":hashlib.sha256(f.read_bytes()).hexdigest(),
        }
    current=assess_v03_readiness(
        plan,matrix,matrix_sha256=sha,preparation_receipts=receipts,
        live_candidate_source_sha256=source["source_sha256"],
        live_native_binary_sha256=native["sha256"],
    )
    old=[
        json.loads((art/"preparation"/(case["id"]+".prepare.json")).read_bytes())
        for case in matrix["cases"]
    ]
    older=assess_v03_readiness(
        plan,matrix,matrix_sha256=sha,preparation_receipts=old,
        live_candidate_source_sha256=source["source_sha256"],
        live_native_binary_sha256=native["sha256"],
    )
    if (current["v03"]["calendar_preparation_verified"]!=3 or
        older["v03"]["calendar_preparation_verified"]!=0 or
        current["v03"]["completed_full_day_runs"]!=0):
        raise ValueError("invalid V03 source-bound readiness after Arc implementation")
    if sum(x["planned_legs"] for x in city.values())!=8461965:
        raise ValueError("demand source has changed")
    result={
       "schema":"V03_ARC_PACKET_CANDIDATE_SOURCE_PINNED_PREFLIGHT_V1",
       "current_native_sha256":native["sha256"],
       "current_candidate_source_sha256":source["source_sha256"],
       "original_matrix_sha256":sha,
       "original_plan_version":plan["version"],
       "original_100k_city_preparation":{"completed":3,"total":3},
       "old_pre_arc_receipts_rejected":3,
       "original_full_day_runs":{"completed":0,"required":9},
       "project_dag":{"completed_scoped":19,"total":21},
       "case_receipts":city,
       "total_planned_legs":8461965,
       "model_parameter_fitted_for_prep":False,
       "resource_budget_changed":False,
       "physics_execution_scoped_prefix":"NOT_EXECUTED_IN_THIS_PREPARATION",
       "V03":"BLOCKED",
    }
    out=art/"C8_ARC_PREP_VERIFIED.json"
    out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"dag":"19/21","arc_prep":"3/3",
                      "full_day":"0/9","native":native["sha256"]},sort_keys=True))

if __name__=="__main__":
    main()
