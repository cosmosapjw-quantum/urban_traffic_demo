#!/usr/bin/env python3
"""Same compiled native, same physical source: default vs opt-in pair credit.

Experiment ONLY. Original internal road work cap is never raised. Both runs
must start from the same byte-verified Valley 25600 checkpoint under the exact
100k release source, driver and 8GiB process limit.
"""
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"src")]
PREV=Path("/home/cosmosapjw/worktrees/urban-traffic-v03-service-stream-20261120")
ART=ROOT/"artifacts/v03_composed_events_20261120"

from tools.run_v1_local_acceptance import prepare,candidate_provenance,_ledger_error
from metroflow.v1.native_engine import native_binary_provenance
from _metroflow_rust import budget_trace_snapshot


def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(4*1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def run()->dict:
    if os.environ.get("METROFLOW_BUDGET_TRACE")!="record":
        raise ValueError("record mode required; observe would bypass native budget")
    mode=os.environ.get("METROFLOW_EXPERIMENTAL_ARC_PAIR_BUDGET")
    if mode not in (None,"source_pair_only"):
        raise ValueError("unexpected native budget experimental mode")
    label="PAIR_EXPERIMENT" if mode=="source_pair_only" else "ORIGINAL_DEFAULT"
    matrix_path=ROOT/"scenarios/v1/release_matrix.json"
    data=matrix_path.read_bytes()
    matrix=json.loads(data)
    case=next(c for c in matrix["cases"] if c["id"]=="valley_weekday_s7")
    assert matrix["population"]==100000
    assert matrix["horizon_s"]==86400
    assert matrix["limits"]["peak_rss_bytes"]==8*1024**3
    old=PREV/"artifacts/v03_fifo_service_stream_20261120/arc_prefix"
    input_bin=old/"valley_weekday_s7.native_arc_25600.final.bin"
    ref=json.loads((old/"C9_ARC_PHYSICAL_REPLAY.json").read_bytes())
    original=json.loads((PREV/"artifacts/v03_fifo_service_stream_20261120/prefix/valley_weekday_s7.native_stream_25300.json").read_bytes())
    expected=ref["new_arc_checkpoint_sha256"]
    assert sha(input_bin)==expected
    assert ref["matrix_sha256"]==hashlib.sha256(data).hexdigest()
    assert original["source_sha256"]==ref["physical_source_sha256"] if "physical_source_sha256" in ref else True
    live_src=candidate_provenance()
    live_native=native_binary_provenance()
    if live_src.get("status")!="MEASURED" or live_src.get("source_dirty") is not False:
        raise ValueError("candidate source dirty or unmeasured")
    if live_native.get("status")!="MEASURED":
        raise ValueError("native binary unmeasured")
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
    start=time.perf_counter()
    driver,meta=prepare(case,matrix,10.0)
    assert driver.identity==original["driver_identity"]
    assert meta["source_sha256"]==original["source_sha256"]
    assert meta["patch_sha256"]==original["patch_sha256"]
    state=driver.load(input_bin)
    if state.time_s!=25600 or _ledger_error(driver.report(state),25600,population=100000):
        raise ValueError("original 25600 source state and mass ledger invalid")
    debug=driver.debug_state(state)
    assert debug["road"]["arc_backing_census"]["duplicate_payload_bytes"]==0
    union=debug["road"]["arc_committed_snapshot_union_census"]
    assert union["duplicate_payload_bytes"]>0
    trace_begin=budget_trace_snapshot(reset=True)
    assert trace_begin["mode"]=="record"
    error=None
    end=None
    mass_ledger=None
    final_sha=None
    checkpoint_bytes=None
    try:
        end=driver.advance(state,25650.0)
        assert end.time_s==25650.
        report=driver.report(end)
        mass_error=_ledger_error(report,25650,population=100000)
        if mass_error is not None:
            raise ValueError("original 25650 physical mass ledger changed: "+mass_error)
        mass_ledger=report["execution"]["ledger"]
        output=ART/("C2_"+label+"_25650.final.bin")
        driver.save(output,end)
        final_sha=sha(output)
        checkpoint_bytes=output.stat().st_size
        status="EXECUTED_SOURCE_BOUND_25650_SCOPED"
    except Exception as exc:
        error={"type":type(exc).__name__,"message":str(exc)}
        status="BLOCKED_"+type(exc).__name__
    elapsed=time.perf_counter()-start
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    trace=budget_trace_snapshot(reset=False)
    record={
      "schema":"V03_NATIVE_COMPACT_MARK_REPLAY_SOURCE_BOUND_20261120_V1",
      "mode":label,
      "experiment_env":mode or "OFF",
      "original_native_cap_bytes":5242806391,
      "original_8GiB_process_cap_bytes":limit,
      "source_sha256":live_src["source_sha256"],
      "loaded_native_sha256":live_native["sha256"],
      "original_input_checkpoint_sha256":expected,
      "original_matrix_sha256":hashlib.sha256(data).hexdigest(),
      "original_driver_identity":driver.identity,
      "original_100k_valley":True,
      "original_86400s_day":86400,
      "requested_end_s":25650.,
      "reached_end_s":end.time_s if end is not None else None,
      "status":status,
      "error":error,
      "mass_ledger":mass_ledger,
      "final_checkpoint_sha256":final_sha,
      "checkpoint_bytes":checkpoint_bytes,
      "checkpoint_binary_local_only":True,
      "reported_initial_cross_state_arc_duplicate_payload_bytes":union["duplicate_payload_bytes"],
      "elapsed_s":elapsed,
      "peak_rss_bytes":rss,
      "trace_mode":"record_not_observe",
      "trace_guard_sites":trace["sites"],
      "trace_counters":trace["counters"],
      "new_fitted_physical_parameters":[],
      "original_24h_runs_accepted":0,
      "claim_limit":"opt-in experimental native admission, no production release or universal live-set safety proof",
    }
    ART.mkdir(parents=True,exist_ok=True)
    path=ART/("C2_"+label+"_25650.json")
    path.write_text(json.dumps(record,indent=2,sort_keys=True,ensure_ascii=False)+"\n")
    print(json.dumps({
      "mode":label,"status":status,"time":record["reached_end_s"],"wall_s":round(elapsed,2),
      "rss_gib":round(rss/1024**3,3),"checkpoint_mb":round(checkpoint_bytes/1024**2,2) if checkpoint_bytes else None,
      "arc_credit_trace":trace.get("counters",{}).get("arc.experimental_paired_credit"),
      "error":error,
    },sort_keys=True),flush=True)
    return record


if __name__=="__main__":
    run()
