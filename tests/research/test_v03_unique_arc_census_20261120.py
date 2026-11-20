"""Exact observed one-state Arc identity census at original V03 100k snapshots.

No budget gate changes and no claim of inter-state alias or 24h release.
"""
from pathlib import Path
import hashlib
import json

from tools.run_v1_local_acceptance import candidate_provenance
from metroflow.v1.native_engine import native_binary_provenance

ROOT=Path(__file__).resolve().parents[2]
RECORD=ROOT/"artifacts/v03_fifo_unique_accounting_20261120/C2_ACTUAL_25600_BACKING_CENSUS.json"


def test_actual_100k_snapshots_have_no_intra_state_duplicate_backing():
    x=json.loads(RECORD.read_bytes())
    assert x["original_model_physics_advanced"] is False
    assert x["road_work_budget_modified"] is False
    assert x["original_native_internal_budget_bytes"]==5242806391
    assert x["original_24h_completed_runs"]==0
    assert x["current_native_sha256"]==native_binary_provenance()["sha256"]
    assert x["current_source_sha256"]==candidate_provenance()["source_sha256"]
    for tm,owners,parts in [("25300",2027,155485),("25600",158498,8049883)]:
        m=x["measurements"][tm]
        c=m["arc_backing_census"]
        assert m["road_packet_rows"]==parts
        assert m["road_packet_count"]==owners
        assert c["owner_count"]==c["unique_backing_count"]==owners
        assert c["duplicate_payload_bytes"]==0
        assert c["owner_payload_bytes"]==c["unique_payload_bytes"]
        assert c["unique_arc_control_allowance_bytes"]==96*owners
        assert c["unique_payload_bytes"]<=m["road_vector_capacity_bytes_per_owner"]
        assert len(m["original_source_checkpoint_sha256"])==64


def test_source_identity_and_unchanged_compressed_checkpoint_file_hash():
    x=json.loads(RECORD.read_bytes())
    previous=Path("/home/cosmosapjw/worktrees/urban-traffic-v03-service-stream-20261120")
    p=previous/"artifacts/v03_fifo_service_stream_20261120/arc_prefix/valley_weekday_s7.native_arc_25600.final.bin"
    assert p.is_file()
    h=hashlib.sha256()
    with p.open("rb") as f:
        for buf in iter(lambda:f.read(4*1024*1024),b""):
            h.update(buf)
    assert h.hexdigest()==x["measurements"]["25600"]["original_source_checkpoint_sha256"]
    assert p.stat().st_size==866763962
