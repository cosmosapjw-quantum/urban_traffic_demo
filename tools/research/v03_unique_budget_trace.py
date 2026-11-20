#!/usr/bin/env python3
"""Read-only original V03 25600->25650 failure phase dissection.

Must start process with METROFLOW_BUDGET_TRACE=record. NEVER use observe.
The native physical budget and original 8GiB address space remain enforced.
"""
from pathlib import Path
import hashlib
import json
import os
import resource
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"src")]
PREV=Path("/home/cosmosapjw/worktrees/urban-traffic-v03-service-stream-20261120")
ART=ROOT/"artifacts/v03_fifo_unique_accounting_20261120"
from tools.run_v1_local_acceptance import prepare,candidate_provenance,_ledger_error
from metroflow.v1.native_engine import native_binary_provenance
from _metroflow_rust import budget_trace_snapshot


def digest(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for c in iter(lambda:f.read(4*1024*1024),b""):
            h.update(c)
    return h.hexdigest()


def main():
    if os.environ.get("METROFLOW_BUDGET_TRACE")!="record":
        raise ValueError("only record mode is authorized, observe could bypass budget")
    matrix_bytes=(ROOT/"scenarios/v1/release_matrix.json").read_bytes()
    matrix=json.loads(matrix_bytes)
    baseline=PREV/"artifacts/v03_fifo_service_stream_20261120/arc_prefix"
    chk=baseline/"valley_weekday_s7.native_arc_25600.final.bin"
    ref=json.loads((baseline/"C9_ARC_PHYSICAL_REPLAY.json").read_bytes())
    assert digest(chk)==ref["new_arc_checkpoint_sha256"]
    assert matrix_bytes==(PREV/"scenarios/v1/release_matrix.json").read_bytes()
    assert matrix["population"]==100000 and matrix["horizon_s"]==86400
    assert matrix["limits"]["peak_rss_bytes"]==8*1024**3
    current_src=candidate_provenance()
    current_binary=native_binary_provenance()
    assert current_src["status"]==current_binary["status"]=="MEASURED"
    assert current_src["source_dirty"] is False
    os.environ.update(
        METROFLOW_V1_ENGINE_BACKEND="rust_whole",
        METROFLOW_V1_NATIVE_THREADS="1",
        METROFLOW_V1_STORAGE_POLICY="bounded_bytes_v1",
    )
    limit=matrix["limits"]["peak_rss_bytes"]
    soft,hard=resource.getrlimit(resource.RLIMIT_AS)
    if soft!=resource.RLIM_INFINITY:
        limit=min(limit,soft)
    resource.setrlimit(resource.RLIMIT_AS,(limit,hard))
    case=next(c for c in matrix["cases"] if c["id"]=="valley_weekday_s7")
    driver,meta=prepare(case,matrix,10.0)
    assert driver.identity==ref["driver_identity"] if "driver_identity" in ref else True
    snap=driver.load(chk)
    assert snap.time_s==25600.
    assert _ledger_error(driver.report(snap),25600,population=100000) is None
    before=driver.debug_state(snap)
    assert before["road"]["arc_backing_census"]["duplicate_payload_bytes"]==0
    trace_begin=budget_trace_snapshot(reset=True)
    assert trace_begin["mode"]=="record" and trace_begin["alloc_counting"] is False
    start=time.perf_counter()
    status="UNRESOLVED"
    issue=None
    try:
        end=driver.advance(snap,25650.0)
        status="REACHED_25650"
        assert end.time_s==25650.
    except Exception as exc:
        issue={"type":type(exc).__name__,"message":str(exc)}
        status="ORIGINAL_NATIVE_ERROR"
    wall=time.perf_counter()-start
    trace=budget_trace_snapshot(reset=False)
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    sites=trace["sites"]
    failing=sites.get("road_work:packet interval packing")
    if failing is None:
        raise ValueError("actual original interval packing guard not recorded")
    result={
      "schema":"V03_ACTUAL_25650_NATIVE_BUDGET_TERMS_DIAGNOSTIC_20261120_V1",
      "status":status,
      "error":issue,
      "trace_mode":"record_only_never_observe",
      "trace_alloc_counting_enabled":trace["alloc_counting"],
      "source_sha256":current_src["source_sha256"],
      "loaded_native_sha256":current_binary["sha256"],
      "source_checkpoint_sha256":ref["new_arc_checkpoint_sha256"],
      "original_100k_city":"valley_weekday_s7",
      "initial_time_s":25600.,
      "target_time_s":25650.,
      "original_process_address_space_limit_bytes":limit,
      "original_24hour_runs_completed":0,
      "runtime_wall_s":wall,
      "process_peak_rss_bytes":rss,
      "initial_road_arc_one_state":before["road"]["arc_backing_census"],
      "initial_road_arc_committed_plus_snapshot":before["road"]["arc_committed_snapshot_union_census"],
      "failing_road_work_guard":failing,
      "all_native_budget_trace_sites":sites,
      "trace_counters":trace["counters"],
      "claim_scope":"failed physical step's maximum structural terms under record-only tracing; no success checkpoint if error",
      "physics_rates_tuned":False,
      "road_work_budget_modified":False,
    }
    ART.mkdir(exist_ok=True,parents=True)
    dest=ART/"C5_REAL_25650_PHASE_BUDGET_TRACE.json"
    dest.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n")
    print(json.dumps({"status":status,"wall_s":round(wall,3),"rss_gib":round(rss/1024**3,3),
                      "packing_required":failing.get("max_required"),
                      "native_limit":failing.get("limit_at_max"),
                      "packing_components":failing.get("terms_at_max"),
                      "trace_exceeded":failing.get("exceeded"),"error":issue},sort_keys=True),flush=True)


if __name__=="__main__":
    main()
