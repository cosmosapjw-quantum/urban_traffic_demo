"""Synthetic KCMB 86400s fixed-state finite network is NOT V03 release.

Original V03 demands remain 100k residents in 3 cities and 9 accepted runs.
These tests concern two tiny geometrically distinct kinetic traffic models.
"""
import json
import math
from pathlib import Path

from metroflow.v1.native_engine import native_binary_provenance

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_composed_events_20261120"


def test_kinetic_rust_network_24h_synthetic_mass_conservation_and_fixed_state():
    r=json.loads((ART/"C10_KCMB_SYNTHETIC_24H.json").read_bytes())
    assert r["original_V03_100000_resident_city_simulated"] is False
    assert r["original_V03_full_day_release_accepted"] is False
    assert r["physical_model_not_exact_original_FIFO_checkpoint"] is True
    assert r["simulated_one_day_in_a_synthetic_three_or_five_link_network"] is True
    assert r["number_of_simulated_seconds"]==86400
    assert r["current_compiled_native_sha256"]==native_binary_provenance()["sha256"]
    a=r["cases"]["shared_single_lane"]
    b=r["cases"]["dedicated_physical_turn_pockets"]
    assert (a["physical_link_count"],b["physical_link_count"])==(3,5)
    assert (a["state_scalars"],b["state_scalars"])==(42,66)
    for row in (a,b):
        assert row["native_backend"]=="Rust KCMB node and kinetic network"
        assert row["scalar_state_capacity_has_constant_size"] is True
        assert row["simulated_ticks"]==172800
        assert row["simulated_duration_s"]==86400
        assert row["route_count"]==2
        assert all(math.isclose(v,3456.,abs_tol=1e-6)
                   for v in row["source_offered_veh_per_route"])
        assert row["checkpoint_same_model_exact_reload"] is True
        assert 0<row["checkpoint_bytes"]<4096
        assert 0<row["elapsed_wall_s"]<7200
        assert row["max_reported_step_mass_ledger_error_veh"]<1e-6
        assert row["independent_mass_and_lane_storage_checks"]==174
        assert row["microphysics_parameter_fit"] is False
        for ix in range(2):
            assert row["final_pending"][ix]>=0
            assert row["final_completed"][ix]>=0
            assert row["final_completed"][ix]<=row["final_released"][ix]+1e-8
            assert row["final_released"][ix]<=row["source_offered_veh_per_route"][ix]+1e-8


def test_full_day_synthetic_is_not_a_100k_urban_source_bound_legacy_acceptance():
    r=json.loads((ART/"C10_KCMB_SYNTHETIC_24H.json").read_bytes())
    assert "not urban observational demand" in r["physical_traffic_sources"]
    assert len(r["cases"])==2
    assert r["cases"]["shared_single_lane"]["checkpoint_bytes"]==613
    assert r["cases"]["dedicated_physical_turn_pockets"]["checkpoint_bytes"]==802
    assert r["original_V03_100000_resident_city_simulated"] is False
    assert r["original_V03_full_day_release_accepted"] is False
