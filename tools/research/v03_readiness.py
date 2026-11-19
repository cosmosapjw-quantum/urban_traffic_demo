#!/usr/bin/env python3
"""Evidence-bound V03 physical preflight readiness. Never executes full days.

No new DAG nodes, source demand prior values, physical tolerance or RSS budget
are introduced. It reads the existing authoritative V03 plan/release matrix
and optionally fresh original full-calendar preparation receipts.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"src"))
sys.path.insert(0,str(ROOT))
from metroflow.v1.v03_readiness import assess_v03_readiness
from tools.v1_plan import validate
from tools.run_v1_local_acceptance import candidate_provenance
from metroflow.v1.native_engine import native_binary_provenance


def sha256(path:Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def observed_host():
    mem={}
    for ln in Path("/proc/meminfo").read_text().splitlines():
        if ":" in ln:
            key,val=ln.split(":",1)
            fields=val.split()
            if fields and fields[0].isdigit():
                mem[key]=int(fields[0])*1024 if len(fields)>1 and fields[1]=="kB" else int(fields[0])
    cpu=next((x.split(":",1)[1].strip() for x in Path("/proc/cpuinfo").read_text().splitlines()
              if x.startswith("model name")),platform.processor())
    total=mem.get("MemTotal")
    return {
        "physical_memory_bytes":total,
        "memory_available_bytes":mem.get("MemAvailable"),
        "swap_free_bytes":mem.get("SwapFree"),
        "cpu_model":cpu,
        "logical_cores":os.cpu_count(),
        "python":platform.python_version(),
        "reference_host_RAM_match":bool(total is not None and
            abs(total-64*1024**3) <= 2*1024**3),
        "host_identity_limitation":"observed host is not guaranteed to match planned Ryzen5900X/64GiB",
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan",default="docs/v1/PLAN.json")
    parser.add_argument("--matrix",default="scenarios/v1/release_matrix.json")
    parser.add_argument("--prep-dir",default=None,
        help="directory of exact original <case>.prepare.json receipts; optional")
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    planfile=Path(args.plan) if Path(args.plan).is_absolute() else ROOT/args.plan
    matrixfile=Path(args.matrix) if Path(args.matrix).is_absolute() else ROOT/args.matrix
    plan=json.loads(planfile.read_bytes())
    matrix=json.loads(matrixfile.read_bytes())
    # The original release plan validator independently verifies node IDs,
    # acyclicity, contract mapping and source-pinned scoped evidence hashes.
    validate(plan,release=False)
    receipts=[]
    if args.prep_dir is not None:
        directory=Path(args.prep_dir)
        directory=directory if directory.is_absolute() else ROOT/directory
        for case in matrix["cases"]:
            file=directory/(case["id"]+".prepare.json")
            if file.is_file():
                receipts.append(json.loads(file.read_bytes()))
    live_source_sha=None
    live_binary_sha=None
    if receipts:
        live_source=candidate_provenance()
        live_binary=native_binary_provenance()
        if live_source.get("status")!="MEASURED" or live_binary.get("status")!="MEASURED":
            raise ValueError("original candidate/native hash unavailable; refuse claimed preparation readiness")
        live_source_sha=live_source["source_sha256"]
        live_binary_sha=live_binary["sha256"]
    readout=assess_v03_readiness(
        plan,matrix,matrix_sha256=sha256(matrixfile),
        preparation_receipts=receipts,
        live_candidate_source_sha256=live_source_sha,
        live_native_binary_sha256=live_binary_sha,
    )
    readout["observed_host"]=observed_host()
    readout["source_file_sha256"]={
        "plan":sha256(planfile),"release_matrix":sha256(matrixfile)}
    readout["measurement_context"]={
        "observed_at_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "branch_commit":subprocess.check_output(["git","rev-parse","HEAD"],
                                                 cwd=ROOT,text=True).strip(),
        "source":"actual repository plan, matrix, optional whole-native prepare receipts",
        "not_fitted_parameters":"none introduced in scorer",
        "live_candidate_source_sha256":live_source_sha,
        "live_native_binary_sha256":live_binary_sha,
        "acceptance_not_promoted":True,
    }
    target=Path(args.output)
    target=target if target.is_absolute() else ROOT/target
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(readout,ensure_ascii=False,indent=2,sort_keys=True)+"\n")
    print(json.dumps({
        "dag":str(readout["dag"]["completed"])+"/"+str(readout["dag"]["total"]),
        "original_V03_calendar_preparation":
            str(readout["v03"]["calendar_preparation_verified"])+"/"+
            str(readout["v03"]["calendar_preparation_total"]),
        "full_24h_runs":
            str(readout["v03"]["completed_full_day_runs"])+"/"+
            str(readout["v03"]["required_full_day_runs"]),
        "V03":readout["v03"]["status"],
        "observed_RAM_GiB":round(readout["observed_host"]["physical_memory_bytes"]/1024**3,2),
    },sort_keys=True))


if __name__=="__main__":
    main()
