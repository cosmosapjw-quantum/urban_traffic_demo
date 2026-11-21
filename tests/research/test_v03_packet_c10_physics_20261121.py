"""Original Valley 100k V03 packet-lifetime 25700 and escalating source-bound proof."""
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
A=ROOT/"artifacts/v03_packet_lifetime_20261121"
PREV=ROOT/"artifacts/v03_persistent_keyset_20261121/C8_KEYSET_CROSS_BINARY_25690.json"
FAILED=A/"C8_100K_10S_25700.json"
SUCCESS=A/"C10_ORIGINAL_100K_10S_25700.json"
TWENTY=A/"C10_100K_CONTINUOUS_20S.json"
EIGHTY=A/"C10_100K_ESCALATING_80S_FROM_25650.json"

def load(p):return json.loads(p.read_bytes())

def test_actual_original_25700_checkpoint_full_mass_and_source_contract():
    prev,old,new=load(PREV),load(FAILED),load(SUCCESS)
    assert old["status"]=="BLOCKED_RESOURCE"
    assert new["status"]=="EXECUTED_ORIGINAL_100K_KEYSET_25700_CROSS_BINARY"
    assert new["start_time_s"]==25690.0
    assert new["completed_time_s"]==new["end_time_s"]==25700.0
    assert new["input_checkpoint_sha256"]==old["input_checkpoint_sha256"]==prev["final_checkpoint_sha256"]
    assert new["input_checkpoint_size_bytes"]==prev["final_checkpoint_bytes"]==2949231402
    assert new["starting_checkpoint_roundtrip_exact"] is True
    assert new["input_mass_ledger"]==prev["completed_mass_ledger"]
    assert new["current_driver_identity"]==prev["current_driver_identity"]
    assert new["original_matrix_sha256"]==prev["original_matrix_sha256"]
    assert new["current_candidate_source_sha256"]!=prev["current_candidate_source_sha256"]
    assert new["current_native_binary_sha256"]!=prev["current_native_binary_sha256"]
    assert new["current_source_dirty"] is False
    assert new["native_process_cap_bytes"]==8*1024**3
    assert new["budget_mode"]=="DEFAULT"
    assert new["final_checkpoint_bytes"]==3405043386
    assert new["final_checkpoint_sha256"]=="ac7a209c6adfd594c791d1ac4b5b33c6e013ae73b7b594e42121115c89bd8369"
    assert new["error"] is None
    assert new["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
    for unit in ("persons","vehicles","cargo_kg"):
        v=new["completed_mass_ledger"][unit]
        assert all(math.isfinite(t) for t in v.values())
        tol=1e-9*max(1.,abs(v["requested"]),abs(v["released"]))
        assert abs(v["requested"]-v["released"]-v["pending"])<=tol
        assert abs(v["released"]-v["completed"]-v["active"])<=tol

def test_actual_100k_original_road_postroad_and_checkpointability_all_pass():
    old,new=load(FAILED),load(SUCCESS)
    assert old["trace_sites"]["journey_commit:checkpointability"]["exceeded"]==1
    for name in ("road_work:transfer candidates","road_work:entry interval split",
                 "road_work:packet interval packing","road_work:indexed sweep preflight",
                 "road_post:event candidate materialize after road",
                 "road_post:continuous keyset allocation","journey_commit:checkpointability"):
        x=new["trace_sites"][name]
        assert x["exceeded"]==0
        assert x["calls"]>0
        assert x["max_required"]<=x["limit_at_max"]
    cp=new["trace_sites"]["journey_commit:checkpointability"]
    assert cp["max_required"]==5534961208
    assert cp["limit_at_max"]==5789366871
    assert cp["terms_at_max"]["phase_road_charge"]==1725554224
    assert cp["terms_at_max"]["phase_journey_charge"]==720968552
    assert cp["terms_at_max"]["phase_event_charge"]==2514417728
    assert cp["max_required"]==(
        cp["terms_at_max"]["phase_road_charge"]
        +cp["terms_at_max"]["phase_journey_charge"]
        +cp["terms_at_max"]["phase_event_charge"]
        +cp["terms_at_max"]["road_decode_scratch"])
    assert new["trace_counters"]["road_work.expired_source_rows"][1]==14237351
    assert new["trace_counters"]["road_work.expired_source_payload_bytes"][1]==801955840

def test_20s_restarted_and_80s_requested_stop_on_first_unresolved_guard():
    done,short,long=load(SUCCESS),load(TWENTY),load(EIGHTY)
    assert short["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert short["previous_full_checkpoint_sha256"]==done["final_checkpoint_sha256"]
    assert short["previous_mass_ledger"]==done["completed_mass_ledger"]
    assert short["status"]=="BLOCKED_RESOURCE"
    assert short["requested_duration_s"]==20
    assert short["valid_advanced_duration_s"]==0.0
    assert short["completed_time_s"]==25700.0
    assert short["blocked_target_time_s"]==25710.0
    s=short["trace_sites"]["road_work:transfer candidates"]
    assert s["exceeded"]==1
    assert s["max_required"]-s["limit_at_max"]==6609
    assert long["status"]=="BLOCKED_RESOURCE_WITH_VALID_PREFIX"
    assert long["start_time_s"]==25650.0
    assert long["requested_duration_s"]==80
    assert long["valid_advanced_duration_s"]==40.0
    assert long["completed_time_s"]==25690.0
    assert long["blocked_target_time_s"]==25700.0
    assert long["error"]["phase"]=="ADVANCE_TO_25700"
    assert "transfer candidates" in long["error"]["message"]
    assert long["trace_sites"]["road_work:transfer candidates"]["exceeded"]==1
    assert long["trace_sites"]["road_work:transfer candidates"]["max_required"]-(
        long["trace_sites"]["road_work:transfer candidates"]["limit_at_max"])==11513
    assert long["final_checkpoint_sha256"]==done["input_checkpoint_sha256"]
    assert long["completed_mass_ledger"]==done["input_mass_ledger"]
    assert long["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert long["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
    assert long["native_process_cap_bytes"]==8*1024**3
    assert long["current_native_binary_sha256"]==done["current_native_binary_sha256"]
    assert long["current_candidate_source_sha256"]==done["current_candidate_source_sha256"]
    assert [x["completed_time_s"] for x in long["completed_step_wall_s"]]==[25660.,25670.,25680.,25690.]
    assert all(0<x["wall_s"]<7200 for x in long["completed_step_wall_s"])
    assert long["wall_total_including_full_preparation_and_checkpoint_io_s"]>sum(
        s["wall_s"] for s in long["completed_step_wall_s"])
