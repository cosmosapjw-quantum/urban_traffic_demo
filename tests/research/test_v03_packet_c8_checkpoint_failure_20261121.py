"""Original 100k V03 source road and postroad success, last checkpointability blocker."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
R6=ROOT/"artifacts/v03_packet_lifetime_20261121/C6_100K_10S_25700.json"
R8=ROOT/"artifacts/v03_packet_lifetime_20261121/C8_100K_10S_25700.json"
ORIG=ROOT/"artifacts/v03_persistent_keyset_20261121/C8_KEYSET_CROSS_BINARY_25690.json"

def read(p):return json.loads(p.read_bytes())

def test_same_sha_original_100k_input_and_actual_binary_change():
    a,b,source=read(R6),read(R8),read(ORIG)
    assert a["input_checkpoint_sha256"]==b["input_checkpoint_sha256"]==source["final_checkpoint_sha256"]
    assert a["input_mass_ledger"]==b["input_mass_ledger"]==source["completed_mass_ledger"]
    assert b["starting_checkpoint_roundtrip_exact"] is True
    assert b["current_source_dirty"] is False
    assert b["current_native_binary_sha256"]!=a["current_native_binary_sha256"]
    assert b["current_candidate_source_sha256"]!=a["current_candidate_source_sha256"]
    assert b["current_driver_identity"]==a["current_driver_identity"]
    assert b["original_matrix_sha256"]==a["original_matrix_sha256"]
    assert b["native_process_cap_bytes"]==8*1024**3
    assert b["budget_mode"]=="DEFAULT"

def test_prior_road_and_postroad_guards_all_passed_but_commit_checkpoint_failed():
    a,b=read(R6),read(R8)
    assert a["trace_sites"]["road_post:continuous keyset allocation"]["exceeded"]==1
    for key in ("road_work:transfer candidates","road_work:entry interval split",
                "road_work:packet interval packing","road_work:indexed sweep preflight",
                "road_post:event candidate materialize after road",
                "road_post:continuous keyset allocation"):
        assert b["trace_sites"][key]["exceeded"]==0
        assert b["trace_sites"][key]["calls"]>0
    old=b["trace_sites"]["journey_commit:checkpointability"]
    assert old["exceeded"]==old["calls"]==1
    assert old["max_required"]==6040190408
    assert old["limit_at_max"]==5789366871
    assert old["max_required"]-old["limit_at_max"]==250823537
    assert b["status"]=="BLOCKED_RESOURCE"
    assert "checkpointability" in b["error"]["message"]
    assert b["completed_time_s"] is None
    assert b["completed_mass_ledger"] is None
    assert b["final_checkpoint_sha256"] is None
    assert b["original_full_day_acceptance"]=="BLOCKED_0_OF_9"

def test_original_checkpoint_terms_show_original_owner_max_overcharge():
    b=read(R8)
    t=b["trace_sites"]["journey_commit:checkpointability"]["terms_at_max"]
    assert t["input_road"]==t["current_road"]==545136024
    assert t["candidate_road"]==635238976
    assert t["decoded_road"]==635282176
    assert t["journey_retained_input"]==t["old_journey"]==228929368
    assert t["new_journey"]==260270208
    assert t["decoded_journey"]==263109816
    assert t["input_event"]==t["current_event"]==795376576
    assert t["candidate_event"]==923664576
    assert t["road_decode_scratch"]==574020704
    assert t["validation_scratch"]==393211568
    assert t["call_binding_reserve"]==82704900
    # A candidate + a future checkpoint decoder cannot both be new physical
    # state during one phase. Still charge the larger of them.
    road=t["input_road"]+t["current_road"]+max(t["candidate_road"],t["decoded_road"])
    journey=t["journey_retained_input"]+t["old_journey"]+max(
        t["new_journey"],t["decoded_journey"])
    events=t["input_event"]+t["current_event"]+t["candidate_event"]
    scratch=max(t["validation_scratch"]-t["call_binding_reserve"],t["road_decode_scratch"])
    assert road==1725554224 and journey==720968552
    assert events==2514417728 and scratch==574020704
    assert road+journey+events+scratch==5534961208
    assert b["trace_sites"]["journey_commit:checkpointability"]["limit_at_max"]-(
        road+journey+events+scratch)==254405663
