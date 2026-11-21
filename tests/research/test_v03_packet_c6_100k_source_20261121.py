"""Original Valley 100k live Part+Mark release and exact next phase blocker."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BEFORE=ROOT/"artifacts/v03_keyset_continuous_20261121/C9_100K_10S_25700.json"
AFTER=ROOT/"artifacts/v03_packet_lifetime_20261121/C6_100K_10S_25700.json"
INPUT=ROOT/"artifacts/v03_persistent_keyset_20261121/C8_KEYSET_CROSS_BINARY_25690.json"

def read(p):return json.loads(p.read_bytes())

def test_input_original_100k_checkpoint_ledger_and_native_identity_are_real():
    old,new,src=read(BEFORE),read(AFTER),read(INPUT)
    assert new["starting_checkpoint_roundtrip_exact"] is True
    assert new["input_checkpoint_sha256"]==old["input_checkpoint_sha256"]==src["final_checkpoint_sha256"]
    assert new["input_checkpoint_size_bytes"]==src["final_checkpoint_bytes"]==2949231402
    assert new["input_mass_ledger"]==old["input_mass_ledger"]==src["completed_mass_ledger"]
    assert new["current_driver_identity"]==old["current_driver_identity"]
    assert new["original_matrix_sha256"]==old["original_matrix_sha256"]
    assert new["current_candidate_source_sha256"] !=old["current_candidate_source_sha256"]
    assert new["current_native_binary_sha256"] !=old["current_native_binary_sha256"]
    assert new["current_source_dirty"] is False
    assert new["native_process_cap_bytes"]==8*1024**3
    assert new["budget_mode"]=="DEFAULT"

def test_actual_early_original_packet_and_split_guards_cleared_due_live_drop():
    old,new=read(BEFORE),read(AFTER)
    assert old["status"]==new["status"]=="BLOCKED_RESOURCE"
    assert old["trace_sites"]["road_work:entry interval split"]["exceeded"]==1
    for phase in ("road_work:entry interval split","road_work:transfer candidates",
                  "road_work:packet interval packing",
                  "road_work:indexed sweep preflight",
                  "road_post:event candidate materialize after road"):
        r=new["trace_sites"][phase]
        assert r["exceeded"]==0 and r["calls"]>0
    rows=new["trace_counters"]["road_work.expired_source_rows"]
    payload=new["trace_counters"]["road_work.expired_source_payload_bytes"]
    assert rows==[1586,14237351,591287]
    assert payload==[1586,801955840,33116160]
    # This really deletes the old physically backed source Part AND Mark
    # pages; it is NOT a fabricated budget credit for retained FIFO packets.

def test_next_postroad_block_not_called_a_completed_25700s_state():
    new=read(AFTER)
    fail=new["trace_sites"]["road_post:continuous keyset allocation"]
    assert fail["calls"]==fail["exceeded"]==1
    assert fail["max_required"]==5108407968
    assert fail["limit_at_max"]==5087563191
    assert fail["max_required"]-fail["limit_at_max"]==20844777
    assert fail["terms_at_max"]["road_owner_max"]==745155216
    assert new["status"]=="BLOCKED_RESOURCE"
    assert "continuous keyset allocation" in new["error"]["message"]
    assert new["completed_time_s"] is None
    assert new["completed_mass_ledger"] is None
    assert new["final_checkpoint_sha256"] is None
    assert new["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
