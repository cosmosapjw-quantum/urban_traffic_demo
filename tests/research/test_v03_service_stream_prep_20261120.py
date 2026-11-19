"""Original V03 100k preparation must come from this exact native source/binary."""
import hashlib
import json
from pathlib import Path

from metroflow.v1.v03_readiness import assess_v03_readiness
from metroflow.v1.native_engine import native_binary_provenance
from tools.run_v1_local_acceptance import candidate_provenance

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_fifo_service_stream_20261120"


def test_current_served_stream_native_preparations_three_cities_not_full_day():
    x=json.loads((ART/"C3_SOURCE_BOUND_PREPARATION.json").read_bytes())
    assert x["original_100k_city_preparations"]=={"completed":3,"total":3}
    assert x["original_full_day_acceptance"]=={"completed":0,"required":9}
    assert x["dags"]=={"scoped_completed":19,"total":21,"v03_dependencies":3}
    assert x["total_planned_legs"]==8461965
    assert x["source_sha256"]==candidate_provenance()["source_sha256"]
    assert x["native_binary_sha256"]==native_binary_provenance()["sha256"]
    for case,receipt in x["case_receipts"].items():
        raw=ART/"preparation"/(case+".prepare.json")
        assert hashlib.sha256(raw.read_bytes()).hexdigest()==receipt["receipt_sha256"]
        assert receipt["resident_stock"]==100000
        assert receipt["peak_rss_bytes"]<8*1024**3


def test_old_native_receipts_are_not_accepted_for_current_binary():
    original=ROOT/"artifacts/v03_fifo_lineage_coding_20261119/preparation"
    matrix_bytes=(ROOT/"scenarios/v1/release_matrix.json").read_bytes()
    matrix=json.loads(matrix_bytes)
    plan=json.loads((ROOT/"docs/v1/PLAN.json").read_bytes())
    rows=[json.loads((original/(case["id"]+".prepare.json")).read_bytes())
          for case in matrix["cases"]]
    r=assess_v03_readiness(
        plan,matrix,
        matrix_sha256=hashlib.sha256(matrix_bytes).hexdigest(),
        preparation_receipts=rows,
        live_candidate_source_sha256=candidate_provenance()["source_sha256"],
        live_native_binary_sha256=native_binary_provenance()["sha256"],
    )
    assert r["v03"]["calendar_preparation_verified"]==0
    assert r["v03"]["completed_full_day_runs"]==0
    assert all(x["status"]=="REJECTED_EVIDENCE"
               for x in r["case_preparation"].values())
