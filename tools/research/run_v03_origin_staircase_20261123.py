#!/usr/bin/env python3
"""Execute original active-window 10/20/40-second continuations sequentially."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
EXPECTED_END_SHA="c8335535408e13266bb4b5f15b10d0854701e644421ae3e8183d7c468d9183c9"


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed-checkpoint",required=True,type=Path)
    p.add_argument("--out-dir",required=True,type=Path)
    p.add_argument("--child-wall-limit-s",type=int,default=1800)
    a=p.parse_args()
    if not 0<a.child_wall_limit_s<=7200:
        raise ValueError("bounded child deadline must not exceed original 7200s")
    if os.environ.get("METROFLOW_EXPERIMENTAL_ARC_PAIR_BUDGET") is not None:
        raise ValueError("experimental override is forbidden")
    out=a.out_dir.resolve()
    out.mkdir(parents=True,exist_ok=True)
    manifest=out/"staircase.json"
    if manifest.exists():
        raise ValueError("refuse to overwrite an existing staircase")
    receipt=ROOT/"artifacts/v03_event_store_envelope_20261123/R8e_active_replay_25650_requested_10s.json"
    checkpoint=a.seed_checkpoint.resolve()
    run={
        "schema":"V03_ORIGIN_ACTIVE_WINDOW_STAIRCASE_V1",
        "created_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "physical_dt_s":10,"native_call_cadence":"tick",
        "start_time_s":25660,"requested_windows_s":[10,20,40],
        "start_from_historical_checkpoint":True,
        "current_candidate_from_time_zero_verified":False,
        "child_wall_limit_s":a.child_wall_limit_s,
        "full_day_campaign_credit":0,"stages":[],
        "status":"RUNNING",
    }
    def save():
        manifest.write_text(json.dumps(run,indent=2)+"\n")
    save()
    env=dict(os.environ,METROFLOW_BUDGET_TRACE="off",
             PYTHONPATH=str(ROOT/"native_binding")+":"+str(ROOT/"src")+":"+str(ROOT),
             OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MKL_NUM_THREADS="1")
    clock=25660
    for duration in (10,20,40):
        target=out/f"from_{clock}_duration_{duration}.json"
        log=target.with_suffix(".log")
        cmd=[sys.executable,str(ROOT/"tools/research/v03_origin_validation_horizon_20261123.py"),
             "--start-receipt",str(receipt),"--start-checkpoint",str(checkpoint),
             "--duration-s",str(duration),"--out",str(target)]
        start=time.perf_counter()
        item={"duration_s":duration,"start_time_s":clock,"command":cmd,"receipt":str(target),"log":str(log)}
        try:
            with log.open("w") as stream:
                result=subprocess.run(cmd,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,
                                      timeout=a.child_wall_limit_s,check=False)
            item["process_exit_code"]=result.returncode
        except subprocess.TimeoutExpired:
            item["process_exit_code"]=None
            item["status"]="EXPLORATORY_DEADLINE"
        item["external_wall_s"]=time.perf_counter()-start
        if target.exists():
            r=json.loads(target.read_bytes())
            item.update(status=r["status"],valid_advanced_duration_s=r["valid_advanced_duration_s"],
                        completed_time_s=r["completed_time_s"],peak_rss_bytes=r["peak_rss_bytes"],
                        receipt_wall_s=r["wall_total_including_full_preparation_and_checkpoint_io_s"],
                        final_checkpoint_sha256=r["final_checkpoint_sha256"],
                        final_checkpoint_bytes=r["final_checkpoint_bytes"],
                        current_candidate_source_sha256=r["current_candidate_source_sha256"],
                        current_native_binary_sha256=r["current_native_binary_sha256"])
        run["stages"].append(item)
        save()
        print(json.dumps(item),flush=True)
        if (item.get("process_exit_code")!=0 or item.get("status")!="EXECUTED_CURRENT_SOURCE_CONTINUOUS_HORIZON"
                or item.get("valid_advanced_duration_s")!=duration
                or item.get("completed_time_s")!=clock+duration):
            run["status"]="BLOCKED_WITH_PRESERVED_PRIOR_PREFIX"
            save()
            return 2
        clock+=duration
        receipt,checkpoint=target,target.with_suffix(".final.bin")
    run["completed_time_s"]=clock
    run["valid_linked_duration_s"]=clock-run["start_time_s"]
    run["last_checkpoint_sha256"]=item["final_checkpoint_sha256"]
    run["byte_identical_to_historical_25730"]=(clock==25730 and item["final_checkpoint_sha256"]==EXPECTED_END_SHA)
    run["status"]=("COMPLETED_STAIRCASE_EXACT_WIRE" if run["byte_identical_to_historical_25730"]
                   else "COMPLETED_PHYSICS_BUT_BYTE_MISMATCH")
    save()
    return 0 if run["byte_identical_to_historical_25730"] else 2


if __name__=="__main__":
    raise SystemExit(main())
