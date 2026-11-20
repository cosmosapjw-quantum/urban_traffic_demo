"""Source-bound current default compact-Mark Rust 100k city calendar readiness."""
import hashlib
import json
from pathlib import Path

from metroflow.v1.native_engine import native_binary_provenance
from tools.run_v1_local_acceptance import candidate_provenance
from metroflow.v1.v03_readiness import assess_v03_readiness

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_composed_events_20261120"


def test_new_native_exact_original_population_three_case_input_preparation():
    record=json.loads((ART/"C5_CURRENT_V03_READINESS.json").read_bytes())
    source=candidate_provenance()
    binary=native_binary_provenance()
    assert source["source_dirty"] is False
    assert record["measurement_context"]["live_candidate_source_sha256"]==source["source_sha256"]
    assert record["measurement_context"]["live_native_binary_sha256"]==binary["sha256"]
    assert record["v03"]["calendar_preparation_verified"]==3
    assert record["v03"]["dependency_nodes_completed"]==3
    assert record["v03"]["completed_full_day_runs"]==0
    assert record["v03"]["required_full_day_runs"]==9
    assert record["v03"]["status"]=="BLOCKED"
    assert record["dag"]["completed"]==19 and record["dag"]["total"]==21
    total=0
    cases={"river_weekday_s17":5093765,
           "coastal_weekend_s41":2449750,
           "valley_weekday_s7":918450}
    for case,expected_legs in cases.items():
        obj=json.loads((ART/"C5_preparation"/(case+".prepare.json")).read_bytes())
        assert obj["case"]==case
        assert obj["status"]=="WHOLE_CALENDAR_PREPARED"
        assert obj["calendar"]["resident_stock"]==100000
        assert obj["calendar"]["legs"]==expected_legs
        assert obj["simulated_s"]==obj["horizon_s"]==0
        assert obj["native_binary_sha256"]==binary["sha256"]
        assert obj["candidate_source_sha256"]==source["source_sha256"]
        assert obj["peak_rss_bytes"]<8*1024**3
        assert obj["wall_s"]<7200
        total+=expected_legs
    assert total==8461965


def test_old_arc_owner_version_preparation_receipts_rejected_by_new_source():
    matrix_file=ROOT/"scenarios/v1/release_matrix.json"
    data=matrix_file.read_bytes()
    matrix=json.loads(data)
    plan=json.loads((ROOT/"docs/v1/PLAN.json").read_bytes())
    previous=ROOT/"artifacts/v03_fifo_unique_accounting_20261120/C9_preparation"
    receipts=[json.loads((previous/(c["id"]+".prepare.json")).read_bytes())
              for c in matrix["cases"]]
    x=assess_v03_readiness(
        plan,matrix,
        matrix_sha256=hashlib.sha256(data).hexdigest(),
        preparation_receipts=receipts,
        live_candidate_source_sha256=candidate_provenance()["source_sha256"],
        live_native_binary_sha256=native_binary_provenance()["sha256"],
    )
    assert x["v03"]["calendar_preparation_verified"]==0
    assert x["v03"]["completed_full_day_runs"]==0
    assert all(v["status"]=="REJECTED_EVIDENCE" for v in x["case_preparation"].values())
