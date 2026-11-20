"""Source-bound actual simultaneous Arc-ownership census (NOT budget gate)."""
import json
from pathlib import Path
from tools.run_v1_local_acceptance import candidate_provenance
from metroflow.v1.native_engine import native_binary_provenance

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/"artifacts/v03_fifo_unique_accounting_20261120/C4_ACTUAL_25600_CROSS_SNAPSHOT_UNION.json"


def test_exact_cross_snapshot_payload_alias_on_original_100k_valley():
    obj=json.loads(DATA.read_bytes())
    # Historic C4 receipt belongs to its own compiled binary, not current C9.
    assert obj["current_source_sha256"]=="5fab49213d660b069866b3a4c0fa296657237dc1c2645f14e75802bf31c06d32"
    assert obj["current_native_sha256"]=="57b7ac3104adce4ba0bf68f09ff9bc62e9996a3255ea65f4e369329e92ec5c31"
    assert obj["current_source_sha256"]!=candidate_provenance()["source_sha256"]
    assert obj["current_native_sha256"]!=native_binary_provenance()["sha256"]
    assert obj["original_model_physics_advanced"] is False
    assert obj["road_work_budget_modified"] is False
    assert obj["original_native_internal_budget_bytes"]==5242806391
    for timestamp,owners,rows,payload in (
        ("25300",2027,155485,4975520),
        ("25600",158498,8049883,257596256),
    ):
        state=obj["measurements"][timestamp]
        one=state["arc_backing_census"]
        two=state["committed_plus_supplied_arc_union_census"]
        assert state["road_packet_rows"]==rows
        assert one["owner_count"]==one["unique_backing_count"]==owners
        assert one["duplicate_payload_bytes"]==0
        assert one["unique_payload_bytes"]==payload
        assert two["owner_count"]==2*owners
        assert two["unique_backing_count"]==owners
        assert two["owner_payload_bytes"]==2*payload
        assert two["unique_payload_bytes"]==payload
        assert two["duplicate_payload_bytes"]==payload
        assert two["owner_payload_bytes"]-two["unique_payload_bytes"]==payload
        assert two["unique_arc_control_allowance_bytes"]==96*owners


def test_no_unverified_claim_of_three_states_or_budget_admission():
    obj=json.loads(DATA.read_bytes())
    assert "no candidate/interval scratch" in obj["claim_scope"]
    assert obj["original_24h_completed_runs"]==0
    assert obj["original_24h_required_runs"]==9
    assert obj["observed_state_times_s"]==[25300,25600]
