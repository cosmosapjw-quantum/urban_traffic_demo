"""Original V03 actual Mark-compressed default replay is byte-identical.

Compare two different compiled binaries, same source-bound 100k Valley input.
The new binary did not use experimental Arc-pair budget credit.
"""
from pathlib import Path
import hashlib
import json

from metroflow.v1.native_engine import native_binary_provenance
from tools.run_v1_local_acceptance import candidate_provenance

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_composed_events_20261120"
PRIOR=Path("/home/cosmosapjw/worktrees/urban-traffic-v03-unique-accounting-20261120/artifacts/v03_fifo_unique_accounting_20261120")


def test_default_mark_25650_matches_original_earlier_optin_checkpoint_and_ledger():
    c=json.loads((ART/"C2_ORIGINAL_DEFAULT_25650.json").read_bytes())
    r=json.loads((PRIOR/"C8_PAIR_EXPERIMENT_25650.json").read_bytes())
    assert c["status"]=="EXECUTED_SOURCE_BOUND_25650_SCOPED"
    assert c["experiment_env"]=="OFF"
    assert c["original_24h_runs_accepted"]==0
    assert c["reached_end_s"]==25650.
    assert c["original_native_cap_bytes"]==r["original_native_cap_bytes"]==5242806391
    assert c["original_8GiB_process_cap_bytes"]==r["original_8GiB_process_cap_bytes"]==8*1024**3
    assert c["loaded_native_sha256"]!=r["loaded_native_sha256"]
    assert c["loaded_native_sha256"]==native_binary_provenance()["sha256"]
    assert c["source_sha256"]==candidate_provenance()["source_sha256"]
    assert c["original_input_checkpoint_sha256"]==r["original_input_checkpoint_sha256"]
    assert c["original_driver_identity"]==r["original_driver_identity"]
    assert c["original_matrix_sha256"]==r["original_matrix_sha256"]
    assert c["final_checkpoint_sha256"]==r["final_checkpoint_sha256"]
    assert c["checkpoint_bytes"]==r["checkpoint_bytes"]==1683486650
    assert c["mass_ledger"]==r["mass_ledger"]
    assert c["trace_counters"]["arc.experimental_paired_credit"]==[5,0,0]
    path=ART/"C2_ORIGINAL_DEFAULT_25650.final.bin"
    sha=hashlib.sha256()
    with path.open("rb") as inp:
        for chunk in iter(lambda:inp.read(4*1024*1024),b""):
            sha.update(chunk)
    assert sha.hexdigest()==c["final_checkpoint_sha256"]
    assert c["peak_rss_bytes"]<8*1024**3


def test_original_whole_24h_acceptance_did_not_occur():
    c=json.loads((ART/"C2_ORIGINAL_DEFAULT_25650.json").read_bytes())
    assert c["original_86400s_day"]==86400
    assert c["original_24h_runs_accepted"]==0
    assert c["reached_end_s"]<86400
