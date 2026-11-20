#!/usr/bin/env python3
"""Read-only original 100k Valley key-list census; no traffic evolution."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"src")]

from tools.run_v1_local_acceptance import (
    prepare, candidate_provenance, _ledger_error, file_sha256,
)
from metroflow.v1.native_engine import native_binary_provenance


def run() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--previous-receipt",type=Path,required=True)
    p.add_argument("--checkpoint",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    matrix_path=ROOT/"scenarios/v1/release_matrix.json"
    raw_matrix=matrix_path.read_bytes()
    matrix=json.loads(raw_matrix)
    digest=hashlib.sha256(raw_matrix).hexdigest()
    assert matrix["population"]==100000 and matrix["horizon_s"]==86400
    assert matrix["limits"]["peak_rss_bytes"]==8*1024**3
    assert matrix["limits"]["wall_s"]==7200
    case=next(x for x in matrix["cases"] if x["id"]=="valley_weekday_s7")
    previous=json.loads(a.previous_receipt.read_bytes())
    assert previous["status"]=="EXECUTED_ORIGINAL_100K_25680_CROSS_BINARY"
    assert previous["original_matrix_sha256"]==digest
    assert previous["completed_time_s"]==25680.
    assert a.checkpoint.is_file()
    assert a.checkpoint.stat().st_size==previous["final_checkpoint_bytes"]
    assert file_sha256(a.checkpoint)==previous["final_checkpoint_sha256"]
    source=candidate_provenance()
    native=native_binary_provenance()
    assert source["status"]=="MEASURED" and source["source_dirty"] is False
    assert native["status"]=="MEASURED"
    assert Path(native["path"]).resolve().parent==(ROOT/"native_binding").resolve()
    os.environ.update(
        METROFLOW_V1_ENGINE_BACKEND="rust_whole",
        METROFLOW_V1_NATIVE_THREADS="1",
        METROFLOW_V1_STORAGE_POLICY="bounded_bytes_v1",
    )
    limit=matrix["limits"]["peak_rss_bytes"]
    soft,hard=resource.getrlimit(resource.RLIMIT_AS)
    if soft!=resource.RLIM_INFINITY:
        limit=min(limit,soft)
    if hard!=resource.RLIM_INFINITY:
        limit=min(limit,hard)
    resource.setrlimit(resource.RLIMIT_AS,(limit,hard))
    started=time.perf_counter()
    driver,meta=prepare(case,matrix,10.0)
    assert driver.identity==previous["current_driver_identity"]
    assert meta["source_sha256"] and meta["patch_sha256"]
    state=driver.load(a.checkpoint)
    assert state.time_s==25680.
    report=driver.report(state)
    assert _ledger_error(report,25680.,population=100000) is None
    assert report["execution"]["ledger"]==previous["completed_mass_ledger"]
    debug=driver.debug_state(state)
    road=debug["road"]
    counts=road["ordered_keyset_census"]
    assert counts["uniform_packet_owners"]==road["uniform_packets"]
    assert counts["distinct_uniform_backings"]<=counts["uniform_packet_owners"]
    assert counts["distinct_keysets"]<=counts["distinct_uniform_backings"]
    assert counts["repeated_key_rows"]*8==counts["potential_saved_key_payload_bytes"]
    assert counts["keyset_len_ge_8_repeat_rows"]<=counts["repeated_key_rows"]
    assert counts["total_uniform_rows"]<=road["uniform_parts"]
    result={
      "schema":"V03_100K_ORDERED_KEYSET_SOURCE_CENSUS_20261121_V1",
      "created_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
      "case":"valley_weekday_s7",
      "source_time_s":state.time_s,
      "historical_checkpoint_sha256":previous["final_checkpoint_sha256"],
      "historical_checkpoint_bytes":previous["final_checkpoint_bytes"],
      "source_sha256":source["source_sha256"],
      "source_dirty":source["source_dirty"],
      "source_commit":source.get("git_commit"),
      "native_sha256":native["sha256"],
      "matrix_sha256":digest,
      "driver_identity":driver.identity,
      "process_limit_bytes":limit,
      "road_cell_parts":road["cell_parts"],
      "road_cell_packets":road["cell_packets"],
      "road_uniform_parts":road["uniform_parts"],
      "road_uniform_packets":road["uniform_packets"],
      "road_vector_capacity_bytes":road["vector_capacity_bytes"],
      "keyset_census":counts,
      "scientific_scope":"read-only independently backed ordered u32 key arrays; does not merge mass/birth/cohorts",
      "original_full_day_acceptance":"BLOCKED_0_OF_9",
      "wall_s":time.perf_counter()-started,
      "peak_rss_bytes":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
    }
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+"\n")
    print(json.dumps({
      "status":"ORIGINAL_100K_KEYSET_CENSUS",
      "uniform_packets":road["uniform_packets"],
      "rows":counts["total_uniform_rows"],
      "repeated_key_rows":counts["repeated_key_rows"],
      "potential_saved_key_payload_bytes":counts["potential_saved_key_payload_bytes"],
      "max_tag":counts["max_tag"],
      "max_offset":counts["max_offset"],
      "wall_s":round(result["wall_s"],3)},sort_keys=True),flush=True)


if __name__=="__main__":
    run()
