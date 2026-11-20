"""Conservative network moment alternative, physically distinct lane/turn models.

Research variant: bounded synthetic test, NOT original V03 full-day acceptance.
"""
import json
from pathlib import Path
import math
from metroflow.v1.native_engine import native_binary_provenance

ROOT=Path(__file__).resolve().parents[2]
FILE=ROOT/"artifacts/v03_composed_events_20261120/C4_KCMB_PHYSICAL_ALTERNATIVES.json"


def test_physically_real_separate_turn_pockets_unblock_green_route():
    r=json.loads(FILE.read_bytes())
    assert r["strict_original_V03_FIFOnetwork_legacy_checkpoint_equivalent"] is False
    assert r["original_V03_full_day_acceptance_credit"]==0
    assert r["original_100k_resident_city_simulated"] is False
    assert r["added_physical_lane_metres"]==30
    assert r["one_step_red_A_green_B"]["shared_A_out"]==0
    assert r["one_step_red_A_green_B"]["pocket_A_out"]==0
    assert r["one_step_red_A_green_B"]["shared_B_out"]==0
    assert r["one_step_red_A_green_B"]["pocket_B_out"]>0
    assert r["simulation_dt_s"]==0.5
    assert r["simulated_duration_s"]==600
    assert r["Rust_KCMB_backend_binary_sha256"]=="60bb008b4ef6e34203a625e73193d51f25cf7651ef70ba83594d2c2ae29250ed"
    assert r["Rust_KCMB_backend_binary_sha256"]!=native_binary_provenance()["sha256"]


def test_multi_route_kinetic_state_and_ledger_do_not_grow_with_partial_packets():
    r=json.loads(FILE.read_bytes())
    a=r["results"]["one_shared_lane"]
    b=r["results"]["two_physical_turn_pockets"]
    assert a["physical_link_count"]==3
    assert b["physical_link_count"]==5
    assert a["state_scalars"]==42
    assert b["state_scalars"]==66
    assert all(math.isclose(x,24.0,abs_tol=1e-9) for x in a["total_offered_by_route"])
    assert a["total_offered_by_route"]==b["total_offered_by_route"]
    assert a["max_step_mass_error_veh"]<1e-9
    assert b["max_step_mass_error_veh"]<1e-9
    assert 0<a["state_serialized_bytes"]<4096
    assert 0<b["state_serialized_bytes"]<4096
    assert a["model_id"]!=b["model_id"]
    assert a["source_and_signal_test_is_synthetic"] is True
    assert b["source_and_signal_test_is_synthetic"] is True
    assert r["sample_parameters"].endswith("not fitted from observations")
