"""New Arc-native full-city calendar receipts must carry current source hashes."""
import hashlib
import json
from pathlib import Path
from metroflow.v1.native_engine import native_binary_provenance
from tools.run_v1_local_acceptance import candidate_provenance

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_fifo_service_stream_20261120"


def test_current_arc_native_three_100k_city_calendar_receipts():
    record=json.loads((ART/"C8_ARC_PREP_VERIFIED.json").read_bytes())
    source=candidate_provenance()["source_sha256"]
    native=native_binary_provenance()["sha256"]
    assert record["current_candidate_source_sha256"]==source
    assert record["current_native_sha256"]==native
    assert record["old_pre_arc_receipts_rejected"]==3
    assert record["original_100k_city_preparation"]=={"completed":3,"total":3}
    assert record["original_full_day_runs"]=={"completed":0,"required":9}
    assert record["project_dag"]=={"completed_scoped":19,"total":21}
    assert record["total_planned_legs"]==8461965
    assert record["V03"]=="BLOCKED"
    assert record["model_parameter_fitted_for_prep"] is False
    for case,row in record["case_receipts"].items():
        path=ART/"arc_preparation"/(case+".prepare.json")
        assert hashlib.sha256(path.read_bytes()).hexdigest()==row["receipt_sha256"]
        assert row["resident_stock"]==100000
        assert row["native_sha256"]==native
        assert row["source_sha256"]==source
        assert row["status"]=="WHOLE_CALENDAR_PREPARED"
        assert row["peak_rss_bytes"]<8*1024**3
