"""Arc packet clone: original V03 cross-version checkpoint and physics replay."""
import hashlib
import json
from pathlib import Path

from metroflow.v1.native_engine import native_binary_provenance
from tools.run_v1_local_acceptance import candidate_provenance

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_fifo_service_stream_20261120"


def test_actual_original_arc_native_25300_to_25600_checkpoint_and_ledgers():
    path=ART/"arc_prefix/C9_ARC_PHYSICAL_REPLAY.json"
    row=json.loads(path.read_bytes())
    assert row["status"]=="BYTE_IDENTICAL_SCOPED"
    assert row["source_timestamp"]==25300
    assert row["destination_timestamp"]==25600
    assert row["original_full_day_accepted"] is False
    assert row["original_86400s_day_required"]==86400
    assert row["original_source_model"]=="RUST_WHOLE_100000_VALLEY"
    assert row["cross_binary_restore_save_25300_byte_equal"] is True
    assert row["mass_ledger_exact_equal"] is True
    assert row["full_checkpoint_byte_equal"] is True
    assert row["new_arc_checkpoint_sha256"]==row["reference_25600_checkpoint_sha256"]
    assert row["new_arc_checkpoint_bytes"]==row["reference_25600_checkpoint_bytes"]
    assert row["new_arc_binary_sha256"]==native_binary_provenance()["sha256"]
    assert row["current_arc_candidate_source_sha256"]==candidate_provenance()["source_sha256"]
    output=ART/"arc_prefix/valley_weekday_s7.native_arc_25600.final.bin"
    assert hashlib.sha256(output.read_bytes()).hexdigest()==row["new_arc_checkpoint_sha256"]
    assert row["new_arc_process_peak_rss_bytes"]<8*1024**3
    assert row["address_space_limit_bytes"]<=8*1024**3


def test_source_stale_previous_25600_receipt_is_not_current_preparation():
    now=json.loads((ART/"C8_ARC_PREP_VERIFIED.json").read_bytes())
    assert now["old_pre_arc_receipts_rejected"]==3
    assert now["original_100k_city_preparation"]=={"completed":3,"total":3}
    assert now["original_full_day_runs"]=={"completed":0,"required":9}
    assert now["V03"]=="BLOCKED"
