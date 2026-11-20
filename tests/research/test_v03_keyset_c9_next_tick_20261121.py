"""Current-source native 25690->25700 original Valley resource guard receipt."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_persistent_keyset_20261121"
BEFORE=ART/"C8_KEYSET_CROSS_BINARY_25690.json"
NEXT=ART/"C9_SAME_NATIVE_25700.json"


def read(p):
    return json.loads(p.read_bytes())


def test_current_source_wiring_checkpoint_full_wire_and_mass_ledger():
    original=read(BEFORE);nxt=read(NEXT)
    assert original["status"]=="EXECUTED_ORIGINAL_100K_KEYSET_25690_CROSS_BINARY"
    assert nxt["input_checkpoint_sha256"]==original["final_checkpoint_sha256"]
    assert nxt["input_checkpoint_size_bytes"]==original["final_checkpoint_bytes"]
    assert nxt["starting_checkpoint_roundtrip_exact"] is True
    assert nxt["input_mass_ledger"]==original["completed_mass_ledger"]
    assert nxt["current_candidate_source_sha256"]==original["current_candidate_source_sha256"]
    assert nxt["current_native_binary_sha256"]==original["current_native_binary_sha256"]
    assert nxt["current_source_dirty"] is False
    assert nxt["current_driver_identity"]==original["current_driver_identity"]
    assert nxt["original_matrix_sha256"]==original["original_matrix_sha256"]
    assert nxt["native_process_cap_bytes"]==8*1024**3
    assert nxt["budget_mode"]=="DEFAULT"
    assert nxt["start_time_s"]==25690.0
    assert nxt["end_time_s"]==25700.0


def test_25700_original_physical_did_not_complete():
    nxt=read(NEXT)
    assert nxt["status"]=="BLOCKED_RESOURCE"
    guard=nxt["trace_sites"]["road_work:transfer candidates"]
    t=guard["terms_at_max"]
    assert guard["calls"]==162851
    assert guard["exceeded"]==1
    assert guard["max_required"]==5_087_573_352
    assert guard["limit_at_max"]==5_087_563_191
    assert guard["max_required"]-guard["limit_at_max"]==10_161
    r=t["incoming_rows"]
    n=1586
    # Original source uses real 64-row Part/Mark pages plus the bounded
    # Vec-of-pages descriptor capacity, not the old doubled flat Vec charge.
    incoming=(r+63*n)*(48+16)+2*(r//64+int(r%64!=0)+n)*(24+24)
    assert incoming==777_121_952
    assert guard["max_required"]==(
        t["base"]+t["event_bytes"]+incoming+
        t["interval_retained"]+t["interval_transient"]+t["extra"]
    )
    assert t["incoming_rows"]==11_764_502
    assert "transfer candidates" in nxt["error"]["message"]
    assert nxt["completed_time_s"] is None
    assert nxt["completed_mass_ledger"] is None
    assert nxt["final_checkpoint_sha256"] is None
    assert nxt["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
