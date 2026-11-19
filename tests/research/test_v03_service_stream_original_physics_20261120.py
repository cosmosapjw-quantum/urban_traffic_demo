"""Original native V03 served-stream checkpoint vs prechange physical source."""
import hashlib
import json
from pathlib import Path

from metroflow.v1.native_engine import native_binary_provenance
from tools.run_v1_local_acceptance import candidate_provenance

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_fifo_service_stream_20261120/prefix"
REF=ROOT/"artifacts/v03_fifo_lineage_coding_20261119/prefix"


def test_actual_100k_valley_native_25300_byte_and_ledger_identity():
    now=json.loads((ART/"valley_weekday_s7.native_stream_25300.json").read_bytes())
    ref=json.loads((REF/"valley_weekday_s7.native_shadow_25300.json").read_bytes())
    assert now["status"]==ref["status"]=="EXECUTED_FOR_REVIEW"
    assert now["simulated_s"]==ref["simulated_s"]==25300
    assert now["engine_backend"]==ref["engine_backend"]=="rust_whole"
    assert now["report"]["calendar"]==ref["report"]["calendar"]
    assert now["report"]["execution"]["ledger"]==ref["report"]["execution"]["ledger"]
    assert now["source_sha256"]==ref["source_sha256"]
    assert now["patch_sha256"]==ref["patch_sha256"]
    assert now["matrix_sha256"]==ref["matrix_sha256"]
    assert now["driver_identity"]==ref["driver_identity"]
    assert now["candidate_source_sha256"]==candidate_provenance()["source_sha256"]
    assert now["native_binary_sha256"]==native_binary_provenance()["sha256"]
    assert now["candidate_source_sha256"]!=ref["candidate_source_sha256"]
    assert now["native_binary_sha256"]!=ref["native_binary_sha256"]
    assert now["final_checkpoint_sha256"]==ref["final_checkpoint_sha256"]
    assert now["final_checkpoint_sha256"]=="7bcbd4e7eb04d8e0014524fa815a29c56b7873c5f3bb12c37a231caa648f32e1"
    binary=ART/"valley_weekday_s7.native_stream_25300.final.bin"
    assert hashlib.sha256(binary.read_bytes()).hexdigest()==now["final_checkpoint_sha256"]
    assert now["peak_rss_bytes"]<8*1024**3
    assert now["wall_s"]<7200
    assert now["report"]["execution"]["ledger"]["vehicles"]["requested"]>0
    assert now["report"]["execution"]["ledger"]["vehicles"]["released"]>0


def test_original_24hour_release_remains_blocked_even_with_prefix():
    x=json.loads((ROOT/"artifacts/v03_fifo_service_stream_20261120/C3_CURRENT_V03_READINESS.json").read_bytes())
    assert x["v03"]["calendar_preparation_verified"]==3
    assert x["v03"]["completed_full_day_runs"]==0
    assert x["v03"]["required_full_day_runs"]==9
    assert x["v03"]["ready_for_release"] is False
    assert x["v03"]["status"]=="BLOCKED"
    assert (x["dag"]["completed"],x["dag"]["total"])==(19,21)
