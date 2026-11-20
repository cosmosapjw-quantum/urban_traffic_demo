"""Original Valley 100k keyset codec source-bound physical regression evidence."""
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
A=ROOT/"artifacts/v03_persistent_keyset_20261121"
OLD=A/"C2_BASELINE_25690.json"
NEW=A/"C8_KEYSET_CROSS_BINARY_25690.json"
CENSUS=A/"C6_REAL_KEYSET_CENSUS_25680.json"


def read(p):
    return json.loads(p.read_bytes())


def test_same_original_25680_checkpoint_cross_native_replay_is_exact():
    old,new=read(OLD),read(NEW)
    assert old["status"]=="BLOCKED_RESOURCE"
    assert new["status"]=="EXECUTED_ORIGINAL_100K_KEYSET_25690_CROSS_BINARY"
    assert old["input_checkpoint_sha256"]==new["input_checkpoint_sha256"]
    assert old["input_checkpoint_size_bytes"]==new["input_checkpoint_size_bytes"]
    assert new["starting_checkpoint_roundtrip_exact"] is True
    assert old["input_mass_ledger"]==new["input_mass_ledger"]
    assert old["current_driver_identity"]==new["current_driver_identity"]
    assert old["original_matrix_sha256"]==new["original_matrix_sha256"]
    assert new["previous_candidate_source_sha256"]==old["current_candidate_source_sha256"]
    assert new["previous_native_binary_sha256"]==old["current_native_binary_sha256"]
    assert new["current_candidate_source_sha256"]!=old["current_candidate_source_sha256"]
    assert new["current_native_binary_sha256"]!=old["current_native_binary_sha256"]
    assert new["current_source_dirty"] is False
    assert new["cross_binary_origin"] is True
    assert new["native_process_cap_bytes"]==8*1024**3
    assert new["budget_mode"]=="DEFAULT"
    assert new["start_time_s"]==25680.0
    assert new["end_time_s"]==new["completed_time_s"]==25690.0
    assert new["error"] is None
    assert new["original_full_day_acceptance"]=="BLOCKED_0_OF_9"


def test_exact_net_keyset_storage_is_real_and_old_guard_cleared():
    old,new,scan=read(OLD),read(NEW),read(CENSUS)
    assert scan["road_cell_parts"]==new["actual_decoded_road_part_count"]==25_644_407
    assert scan["road_vector_capacity_bytes"]==630_789_784
    assert new["actual_decoded_road_vector_capacity_bytes"]==454_935_400
    assert scan["road_vector_capacity_bytes"]-new["actual_decoded_road_vector_capacity_bytes"]==175_854_384
    base_old=old["trace_sites"]["road_base:components"]["terms_at_max"]["base"] if "base" in old["trace_sites"]["road_base:components"]["terms_at_max"] else old["trace_sites"]["road_base:components"]["max_required"]
    base_new=new["trace_sites"]["road_base:components"]["max_required"]
    assert base_old==2_897_009_152
    assert base_new==2_369_446_000
    assert base_old-base_new==3*175_854_384
    assert old["trace_sites"]["road_work:transfer candidates"]["exceeded"]==1
    assert new["trace_sites"]["road_work:transfer candidates"]["exceeded"]==0
    for site in ("road_work:entry interval split","road_work:indexed sweep preflight",
                 "road_post:event candidate materialize after road"):
        r=new["trace_sites"][site]
        assert r["exceeded"]==0 and r["calls"]>0


def test_completed_25690_checkpoint_and_physical_conservation_are_genuine():
    new=read(NEW)
    assert new["final_checkpoint_bytes"]==2_949_231_402
    assert new["final_checkpoint_sha256"]=="db5b6b53f728d892ad53b9e7126d08e73b877f055e2e6e78443f1c0851b7bd10"
    assert new["completed_time_s"]==25690.0
    for unit in ("persons","vehicles","cargo_kg"):
        row=new["completed_mass_ledger"][unit]
        assert all(math.isfinite(x) for x in row.values())
        tol=1e-9*max(1.,abs(row["requested"]),abs(row["released"]))
        assert abs(row["requested"]-row["released"]-row["pending"])<=tol
        assert abs(row["released"]-row["completed"]-row["active"])<=tol
