#!/usr/bin/env python3
"""Read-only source-pinned original V03 current native whole-city preparation."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'src')]

from tools.run_v1_local_acceptance import candidate_provenance
from metroflow.v1.native_engine import native_binary_provenance

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_fifo_service_stream_20261120"
MATRIX=ROOT/"scenarios/v1/release_matrix.json"
PLAN=ROOT/"docs/v1/PLAN.json"

def sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    matrix=json.loads(MATRIX.read_bytes())
    plan=json.loads(PLAN.read_bytes())
    rr=json.loads((ART/"C3_CURRENT_V03_READINESS.json").read_bytes())
    src=candidate_provenance()
    lib=native_binary_provenance()
    assert src["status"]==lib["status"]=="MEASURED"
    assert src.get("source_dirty") is False
    assert rr["v03"]["calendar_preparation_verified"]==len(matrix["cases"])==3
    assert rr["v03"]["completed_full_day_runs"]==0
    assert rr["v03"]["required_full_day_runs"]==9
    assert (rr["dag"]["completed"],rr["dag"]["total"])==(19,21)
    assert rr["v03"]["status"]=="BLOCKED" and not rr["v03"]["ready_for_release"]
    assert rr["measurement_context"]["live_candidate_source_sha256"]==src["source_sha256"]
    assert rr["measurement_context"]["live_native_binary_sha256"]==lib["sha256"]
    rows={}
    for case in matrix["cases"]:
        id=case["id"]
        file=ART/"preparation"/(id+".prepare.json")
        obj=json.loads(file.read_bytes())
        assert obj["status"]=="WHOLE_CALENDAR_PREPARED" and obj["calendar"]["resident_stock"]==100000
        assert obj["matrix_sha256"]==sha(MATRIX)
        assert obj["candidate_source_sha256"]==src["source_sha256"]
        assert obj["native_binary_sha256"]==lib["sha256"]
        assert obj["candidate"]["source_dirty"] is False
        assert obj["horizon_s"]==obj["simulated_s"]==0
        assert 0<=obj["wall_s"]<matrix["limits"]["wall_s"]
        assert 0<=obj["peak_rss_bytes"]<matrix["limits"]["peak_rss_bytes"]
        rows[id]={
           "planned_legs":obj["calendar"]["legs"],
           "resident_stock":obj["calendar"]["resident_stock"],
           "wall_s":obj["wall_s"],
           "peak_rss_bytes":obj["peak_rss_bytes"],
           "source_sha256":obj["candidate_source_sha256"],
           "binary_sha256":obj["native_binary_sha256"],
           "receipt_sha256":sha(file),
        }
    assert sum(v["planned_legs"] for v in rows.values())==8461965
    result={
      "schema":"V03_STREAMED_SERVED_SOURCE_BOUND_PREPARATION_V1",
      "branch":"research/v03-fifo-service-stream-20261120",
      "parent_code_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
      "source_sha256":src["source_sha256"],
      "native_binary_sha256":lib["sha256"],
      "release_matrix_sha256":sha(MATRIX),
      "plan_sha256":sha(PLAN),
      "case_receipts":rows,
      "total_planned_legs":8461965,
      "dags":{"scoped_completed":19,"total":21,"v03_dependencies":3},
      "original_100k_city_preparations":{"completed":3,"total":3},
      "original_full_day_acceptance":{"completed":0,"required":9},
      "v03_status":"BLOCKED",
      "claim":"source-pinned calendar preparation ONLY, not execution of full-day physics",
      "new_fitted_microphysical_coefficients":[],
    }
    target=ART/"C3_SOURCE_BOUND_PREPARATION.json"
    target.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"source_sha256":src["source_sha256"],"native_sha256":lib["sha256"],
                      "cases":len(rows),"planned_legs":result["total_planned_legs"],
                      "dag":"19/21","v03":"BLOCKED_0/9"},sort_keys=True))

if __name__=="__main__":
    main()
