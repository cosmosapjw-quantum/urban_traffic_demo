from __future__ import annotations

import math

import pytest

from metroflow.pure_traffic.ctm import (
    CTMConfig,
    LinkSpec,
    MovementSpec,
    NetworkSpec,
    VehicleRequest,
    initialize_state,
    simulate,
    step,
)
from metroflow.pure_traffic.scenarios import build_diamond_bottleneck_scenario


def _single_link_network() -> NetworkSpec:
    return NetworkSpec(
        links=(
            LinkSpec(
                link_id="road",
                tail="o",
                head="d",
                length_m=600.0,
                lanes=1,
                free_speed_mps=15.0,
                wave_speed_mps=5.0,
                jam_density_veh_per_km_lane=150.0,
                capacity_veh_per_hour_lane=1800.0,
            ),
        ),
        movements=(MovementSpec("road", None, capacity_veh_per_hour=1800.0),),
        coordinates={"o": (0.0, 0.0), "d": (1.0, 0.0)},
    )


def test_single_link_mass_conservation_and_finite_free_flow_time() -> None:
    network = _single_link_network()
    requests = tuple(
        VehicleRequest(vehicle_id=i, release_tick=i, route=("road",)) for i in range(6)
    )
    result = simulate(network, requests, CTMConfig(tick_seconds=10.0), ticks=30)

    assert result.final_state.completed_count == 6
    assert result.final_state.mass_balance_error == 0
    assert all(t >= 40.0 for t in result.completed_travel_times_s)
    assert all(math.isfinite(t) for t in result.completed_travel_times_s)


def test_spillback_reaches_source_and_blocks_admission() -> None:
    network = NetworkSpec(
        links=(
            LinkSpec("up", "o", "m", 450.0, 1, 15.0, 5.0, 150.0, 1800.0),
            LinkSpec("down", "m", "d", 300.0, 1, 15.0, 5.0, 150.0, 360.0),
        ),
        movements=(
            MovementSpec("up", "down", capacity_veh_per_hour=1800.0),
            MovementSpec("down", None, capacity_veh_per_hour=360.0),
        ),
        coordinates={"o": (0.0, 0.0), "m": (1.0, 0.0), "d": (2.0, 0.0)},
    )
    requests = tuple(
        VehicleRequest(vehicle_id=i, release_tick=i // 3, route=("up", "down"))
        for i in range(180)
    )
    result = simulate(network, requests, CTMConfig(tick_seconds=10.0), ticks=70)

    assert max(snapshot.pending_count for snapshot in result.snapshots) > 0
    assert max(snapshot.link_occupancy_ratio["up"] for snapshot in result.snapshots) > 0.65
    assert result.final_state.mass_balance_error == 0


def test_weighted_fair_merge_avoids_starvation_and_remains_work_conserving() -> None:
    network = NetworkSpec(
        links=(
            LinkSpec("a", "oa", "m", 300.0, 1, 15.0, 5.0, 150.0, 1800.0, priority_weight=2.0),
            LinkSpec("b", "ob", "m", 300.0, 1, 15.0, 5.0, 150.0, 1800.0, priority_weight=1.0),
            LinkSpec("out", "m", "d", 300.0, 1, 15.0, 5.0, 150.0, 1080.0),
        ),
        movements=(
            MovementSpec("a", "out", capacity_veh_per_hour=1800.0),
            MovementSpec("b", "out", capacity_veh_per_hour=1800.0),
            MovementSpec("out", None, capacity_veh_per_hour=1080.0),
        ),
        coordinates={"oa": (0.0, 1.0), "ob": (0.0, -1.0), "m": (1.0, 0.0), "d": (2.0, 0.0)},
    )
    requests = []
    vehicle_id = 0
    for tick in range(45):
        for _ in range(2):
            requests.append(VehicleRequest(vehicle_id, tick, ("a", "out")))
            vehicle_id += 1
        requests.append(VehicleRequest(vehicle_id, tick, ("b", "out")))
        vehicle_id += 1
    result = simulate(network, tuple(requests), CTMConfig(tick_seconds=10.0), ticks=100)

    served_a = result.cumulative_movement_flow[("a", "out")]
    served_b = result.cumulative_movement_flow[("b", "out")]
    assert served_a > 0 and served_b > 0
    assert 1.55 <= served_a / served_b <= 2.45
    assert result.node_holding_events == 0
    assert result.final_state.mass_balance_error == 0


def test_movement_fifo_serves_open_turn_behind_blocked_turn() -> None:
    scenario = build_diamond_bottleneck_scenario(seed=11, vehicles=40)
    state = initialize_state(scenario.network, scenario.requests, scenario.config)
    for _ in range(25):
        state, snapshot = step(
            scenario.network,
            scenario.requests,
            scenario.config,
            state,
            incidents=scenario.incidents,
        )
    assert snapshot.cumulative_movement_flow[("in", "lower_a")] > 0
    assert snapshot.cumulative_movement_flow[("in", "upper_a")] >= 0
    assert state.mass_balance_error == 0


def test_replay_fingerprint_is_deterministic() -> None:
    scenario = build_diamond_bottleneck_scenario(seed=29, vehicles=50)
    first = simulate(
        scenario.network,
        scenario.requests,
        scenario.config,
        ticks=80,
        incidents=scenario.incidents,
    )
    second = simulate(
        scenario.network,
        scenario.requests,
        scenario.config,
        ticks=80,
        incidents=scenario.incidents,
    )
    assert first.fingerprint == second.fingerprint
    assert first.snapshots == second.snapshots


def test_invalid_cfl_is_rejected() -> None:
    with pytest.raises(ValueError, match="CFL"):
        initialize_state(
            NetworkSpec(
                links=(
                    LinkSpec("road", "o", "d", 100.0, 1, 40.0, 30.0, 150.0, 1800.0),
                ),
                movements=(MovementSpec("road", None, capacity_veh_per_hour=1800.0),),
                coordinates={"o": (0.0, 0.0), "d": (1.0, 0.0)},
            ),
            (),
            CTMConfig(tick_seconds=10.0, forced_cell_count_by_link={"road": 2}),
        )


def test_simulate_accepts_a_valid_preloaded_initial_state() -> None:
    network = _single_link_network()
    requests = tuple(
        VehicleRequest(vehicle_id=i, release_tick=0, route=("road",))
        for i in range(3)
    )
    empty = initialize_state(network, requests, CTMConfig(tick_seconds=10.0))
    from dataclasses import replace

    preloaded = replace(
        empty,
        cells=(((0, 1, 2), (), (), ()),),
        admitted_ticks=(0, 0, 0),
        released_count=3,
        cumulative_source_admissions=(3,),
    )
    result = simulate(
        network,
        requests,
        CTMConfig(tick_seconds=10.0),
        ticks=8,
        initial_state=preloaded,
    )
    assert result.final_state.completed_count == 3
    assert result.final_state.mass_balance_error == 0


def test_preloaded_state_rejects_vehicle_on_wrong_route_link() -> None:
    network = NetworkSpec(
        links=(
            LinkSpec("up", "o", "m", 150.0, 1, 15.0, 5.0, 200.0, 900.0),
            LinkSpec("down", "m", "d", 150.0, 1, 15.0, 5.0, 200.0, 900.0),
        ),
        movements=(
            MovementSpec("up", "down", capacity_veh_per_hour=900.0),
            MovementSpec("down", None, capacity_veh_per_hour=900.0),
        ),
    )
    requests = (VehicleRequest(0, 0, ("up", "down")),)
    config = CTMConfig(tick_seconds=10.0)
    empty = initialize_state(network, requests, config)
    from dataclasses import replace

    wrong = replace(
        empty,
        cells=(((),), ((0,),)),
        admitted_ticks=(0,),
        released_count=1,
        cumulative_source_admissions=(1, 0),
    )
    with pytest.raises(ValueError, match="current route link"):
        simulate(network, requests, config, ticks=0, initial_state=wrong)


def test_weighted_node_policy_matches_two_to_one_merge_priority() -> None:
    from metroflow.pure_traffic.scenarios import build_weighted_merge_scenario

    lex = build_weighted_merge_scenario(node_policy="lexicographic")
    lex_result = simulate(
        lex.network,
        lex.requests,
        lex.config,
        ticks=10,
        initial_state=lex.initial_state,
    )
    fair = build_weighted_merge_scenario(node_policy="weighted_fair")
    fair_result = simulate(
        fair.network,
        fair.requests,
        fair.config,
        ticks=10,
        initial_state=fair.initial_state,
    )

    assert lex_result.cumulative_movement_flow[("b", "out")] == 0
    assert fair_result.cumulative_movement_flow[("a", "out")] == 20
    assert fair_result.cumulative_movement_flow[("b", "out")] == 10
    assert fair_result.node_holding_events == 0


def test_movement_age_priority_prevents_minority_turn_starvation() -> None:
    from metroflow.pure_traffic.scenarios import build_priority_diverge_scenario

    no_age = build_priority_diverge_scenario(movement_age_priority=False)
    no_age_result = simulate(
        no_age.network,
        no_age.requests,
        no_age.config,
        ticks=15,
        initial_state=no_age.initial_state,
    )
    with_age = build_priority_diverge_scenario(movement_age_priority=True)
    with_age_result = simulate(
        with_age.network,
        with_age.requests,
        with_age.config,
        ticks=15,
        initial_state=with_age.initial_state,
    )

    assert no_age_result.cumulative_movement_flow[("approach", "minor")] == 0
    assert with_age_result.cumulative_movement_flow[("approach", "minor")] >= 6
    assert max(with_age_result.final_state.movement_wait_ticks[:2]) <= 1


def test_two_by_two_node_solver_reaches_the_exact_maximum_throughput() -> None:
    from dataclasses import replace

    network = NetworkSpec(
        links=(
            LinkSpec("a", "oa", "j", 150.0, 2, 15.0, 5.0, 200.0, 900.0),
            LinkSpec("b", "ob", "j", 150.0, 2, 15.0, 5.0, 200.0, 900.0),
            LinkSpec("x", "j", "dx", 150.0, 2, 15.0, 5.0, 200.0, 900.0),
            LinkSpec("y", "j", "dy", 150.0, 2, 15.0, 5.0, 200.0, 900.0),
        ),
        movements=(
            MovementSpec("a", "x", 3600.0),
            MovementSpec("a", "y", 3600.0),
            MovementSpec("b", "x", 3600.0),
            MovementSpec("b", "y", 3600.0),
            MovementSpec("x", None, 3600.0),
            MovementSpec("y", None, 3600.0),
        ),
    )
    requests: list[VehicleRequest] = []
    for first in ("a", "b"):
        for index in range(10):
            target = "x" if index % 2 == 0 else "y"
            requests.append(VehicleRequest(len(requests), 0, (first, target)))
    request_tuple = tuple(requests)
    config = CTMConfig(tick_seconds=10.0, node_policy="weighted_fair")
    empty = initialize_state(network, request_tuple, config)
    a_ids = tuple(request.vehicle_id for request in request_tuple if request.route[0] == "a")
    b_ids = tuple(request.vehicle_id for request in request_tuple if request.route[0] == "b")
    preloaded = replace(
        empty,
        cells=((a_ids,), (b_ids,), ((),), ((),)),
        admitted_ticks=tuple(0 for _ in request_tuple),
        released_count=len(request_tuple),
        cumulative_source_admissions=(10, 10, 0, 0),
    )
    result = simulate(
        network,
        request_tuple,
        config,
        ticks=1,
        initial_state=preloaded,
    )
    node_flow = sum(
        result.cumulative_movement_flow[key]
        for key in (("a", "x"), ("a", "y"), ("b", "x"), ("b", "y"))
    )
    assert node_flow == 10
    assert result.node_holding_events == 0
    assert result.final_state.mass_balance_error == 0


def test_pure_traffic_import_does_not_require_numpy_or_accelerators() -> None:
    import os
    from pathlib import Path
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    script = """
import sys
for name in ('numpy', 'jax', 'cupy', 'torch'):
    sys.modules[name] = None
import metroflow.pure_traffic as pure_traffic
assert pure_traffic.CTMConfig().tick_seconds == 10.0
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src")
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
