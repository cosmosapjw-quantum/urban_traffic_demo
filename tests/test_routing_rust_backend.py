from __future__ import annotations

import numpy as np
import pytest


def _make_routing_fixture():
    from metroflow.city.graph import Node, RoadClass, RoadLink, build_road_network_csr
    from metroflow.flow.state import LinkState

    road_csr = build_road_network_csr(
        nodes=(Node(1), Node(2), Node(3), Node(4)),
        links=(
            RoadLink(10, 1, 2, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
            RoadLink(11, 2, 4, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
            RoadLink(12, 1, 3, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
            RoadLink(13, 3, 4, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
        ),
    )
    link_state = LinkState(
        queue_vehicles=(0.0, 0.0, 0.0, 0.0),
        inflow_vehicles=(0.0, 0.0, 0.0, 0.0),
        outflow_vehicles=(0.0, 0.0, 0.0, 0.0),
        travel_time_cost=(50.0, 1.0, 1.0, 1.0),
        capacity_veh_per_tick=(5.0, 5.0, 5.0, 5.0),
        incident_capacity_multiplier=(1.0, 1.0, 1.0, 1.0),
    )
    return road_csr, link_state


def _make_turn_restricted_fixture():
    from metroflow.city.graph import (
        Node,
        RoadClass,
        RoadLink,
        TurnMovement,
        TurnType,
        build_road_network_csr,
    )
    from metroflow.flow.state import LinkState

    road_csr = build_road_network_csr(
        nodes=(Node(1), Node(2), Node(3), Node(4)),
        links=(
            RoadLink(10, 1, 2, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
            RoadLink(11, 2, 4, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
            RoadLink(12, 2, 3, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
            RoadLink(13, 3, 4, RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
        ),
        turns=(
            TurnMovement(10, 11, TurnType.U_TURN_FORBIDDEN),
            TurnMovement(10, 12, TurnType.THROUGH),
            TurnMovement(12, 13, TurnType.THROUGH),
        ),
    )
    link_state = LinkState(
        queue_vehicles=(0.0, 0.0, 0.0, 0.0),
        inflow_vehicles=(0.0, 0.0, 0.0, 0.0),
        outflow_vehicles=(0.0, 0.0, 0.0, 0.0),
        travel_time_cost=(1.0, 1.0, 5.0, 1.0),
        capacity_veh_per_tick=(5.0, 5.0, 5.0, 5.0),
        incident_capacity_multiplier=(1.0, 1.0, 1.0, 1.0),
    )
    return road_csr, link_state


def test_explicit_rust_routing_backend_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    from metroflow.routing import dynamic_potential

    road_csr, link_state = _make_routing_fixture()

    def unavailable(**_kwargs):
        raise RuntimeError("Rust CPU routing backend unavailable")

    monkeypatch.setattr(
        dynamic_potential,
        "compute_dynamic_potential_node_costs_rust",
        unavailable,
        raising=False,
    )

    with pytest.raises(RuntimeError, match="Rust CPU routing backend unavailable"):
        dynamic_potential.compute_dynamic_potential_state(
            road_csr,
            destination_node_id=4,
            link_state=link_state,
            routing_backend="rust_cpu",
        )


def test_auto_routing_backend_falls_back_to_baseline_when_rust_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.routing import dynamic_potential

    road_csr, link_state = _make_routing_fixture()
    baseline = dynamic_potential.compute_dynamic_potential_state(
        road_csr,
        destination_node_id=4,
        link_state=link_state,
        routing_backend="baseline",
    )

    def unavailable(**_kwargs):
        raise RuntimeError("Rust CPU routing backend unavailable")

    monkeypatch.setattr(
        dynamic_potential,
        "compute_dynamic_potential_node_costs_rust",
        unavailable,
        raising=False,
    )
    monkeypatch.setattr(dynamic_potential, "rust_routing_backend_available", lambda: True)

    automatic = dynamic_potential.compute_dynamic_potential_state(
        road_csr,
        destination_node_id=4,
        link_state=link_state,
        routing_backend="auto",
    )

    np.testing.assert_allclose(automatic.node_cost_to_go, baseline.node_cost_to_go)
    assert automatic.metadata["routing_backend"] == "baseline"
    assert automatic.metadata["routing_backend_fallback"] == "rust_cpu_failed"


def test_auto_routing_backend_skips_incomplete_rust_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.routing import dynamic_potential

    road_csr, link_state = _make_routing_fixture()

    def fail_if_called(**_kwargs):
        raise AssertionError("incomplete rust routing backend must not be called")

    monkeypatch.setattr(
        dynamic_potential,
        "rust_routing_backend_available",
        lambda: False,
    )
    monkeypatch.setattr(
        dynamic_potential,
        "compute_dynamic_potential_node_costs_rust",
        fail_if_called,
        raising=False,
    )

    automatic = dynamic_potential.compute_dynamic_potential_state(
        road_csr,
        destination_node_id=4,
        link_state=link_state,
        routing_backend="auto",
    )

    assert automatic.metadata["routing_backend"] == "baseline"
    assert automatic.metadata["routing_backend_fallback"] == "rust_cpu_unavailable"


def test_rust_routing_backend_uses_wrapper_output(monkeypatch: pytest.MonkeyPatch) -> None:
    from metroflow.routing import dynamic_potential

    road_csr, link_state = _make_routing_fixture()
    baseline = dynamic_potential.compute_dynamic_potential_state(
        road_csr,
        destination_node_id=4,
        link_state=link_state,
        routing_backend="baseline",
    )
    calls = []

    def fake_rust(**kwargs):
        calls.append(kwargs)
        return baseline.node_cost_to_go.copy()

    monkeypatch.setattr(
        dynamic_potential,
        "compute_dynamic_potential_node_costs_rust",
        fake_rust,
        raising=False,
    )

    accelerated = dynamic_potential.compute_dynamic_potential_state(
        road_csr,
        destination_node_id=4,
        link_state=link_state,
        routing_backend="rust_cpu",
    )

    np.testing.assert_allclose(accelerated.node_cost_to_go, baseline.node_cost_to_go)
    assert calls
    assert calls[0]["destination_node_index"] == road_csr.node_id_to_index[4]
    assert accelerated.metadata["routing_backend"] == "rust_cpu"


def test_rust_routing_backend_matches_baseline_when_extension_is_available() -> None:
    from metroflow.backends.rust_cpu import rust_routing_backend_available
    from metroflow.routing import dynamic_potential

    if not rust_routing_backend_available():
        pytest.skip("_metroflow_rust extension is not importable")

    road_csr, link_state = _make_routing_fixture()
    baseline = dynamic_potential.compute_dynamic_potential_state(
        road_csr,
        destination_node_id=4,
        link_state=link_state,
        routing_backend="baseline",
    )
    accelerated = dynamic_potential.compute_dynamic_potential_state(
        road_csr,
        destination_node_id=4,
        link_state=link_state,
        routing_backend="rust_cpu",
    )

    np.testing.assert_allclose(accelerated.node_cost_to_go, baseline.node_cost_to_go)


def test_explicit_rust_next_link_score_backend_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.routing import dynamic_potential

    road_csr, link_state = _make_routing_fixture()
    potential = dynamic_potential.compute_dynamic_potential_state(
        road_csr,
        destination_node_id=4,
        link_state=link_state,
        routing_backend="baseline",
    )

    def unavailable(**_kwargs):
        raise RuntimeError("Rust CPU routing backend unavailable")

    monkeypatch.setattr(
        dynamic_potential,
        "compute_next_link_action_costs_rust",
        unavailable,
        raising=False,
    )

    with pytest.raises(RuntimeError, match="Rust CPU routing backend unavailable"):
        dynamic_potential.score_legal_next_links(
            road_csr,
            potential,
            current_node_id=1,
            routing_backend="rust_cpu",
        )


def test_auto_next_link_score_backend_falls_back_to_baseline_when_rust_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.routing import dynamic_potential

    road_csr, link_state = _make_routing_fixture()
    potential = dynamic_potential.compute_dynamic_potential_state(
        road_csr,
        destination_node_id=4,
        link_state=link_state,
        routing_backend="baseline",
    )

    def unavailable(**_kwargs):
        raise RuntimeError("Rust CPU routing backend unavailable")

    monkeypatch.setattr(
        dynamic_potential,
        "compute_next_link_action_costs_rust",
        unavailable,
        raising=False,
    )

    automatic = dynamic_potential.score_legal_next_links(
        road_csr,
        potential,
        current_node_id=1,
        routing_backend="auto",
    )

    assert automatic.candidate_link_ids == (12, 10)
    assert automatic.best_link_id == 12
    assert automatic.action_costs == (2.0, 51.0)


def test_rust_next_link_score_backend_matches_baseline_when_extension_is_available() -> None:
    from metroflow.backends.rust_cpu import rust_routing_backend_available
    from metroflow.routing import dynamic_potential

    if not rust_routing_backend_available():
        pytest.skip("_metroflow_rust extension is not importable")

    road_csr, link_state = _make_routing_fixture()
    potential = dynamic_potential.compute_dynamic_potential_state(
        road_csr,
        destination_node_id=4,
        link_state=link_state,
        routing_backend="baseline",
    )
    baseline = dynamic_potential.score_legal_next_links(
        road_csr,
        potential,
        current_node_id=1,
        routing_backend="baseline",
    )
    accelerated = dynamic_potential.score_legal_next_links(
        road_csr,
        potential,
        current_node_id=1,
        routing_backend="rust_cpu",
    )

    assert accelerated == baseline


def test_explicit_rust_greedy_route_backend_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.routing import dynamic_potential

    road_csr, link_state = _make_routing_fixture()
    potential = dynamic_potential.compute_dynamic_potential_state(
        road_csr,
        destination_node_id=4,
        link_state=link_state,
        routing_backend="baseline",
    )

    def unavailable(**_kwargs):
        raise RuntimeError("Rust CPU routing backend unavailable")

    monkeypatch.setattr(
        dynamic_potential,
        "compute_greedy_route_candidate_rust",
        unavailable,
        raising=False,
    )

    with pytest.raises(RuntimeError, match="Rust CPU routing backend unavailable"):
        dynamic_potential.build_greedy_route_candidate(
            road_csr,
            potential,
            origin_node_id=1,
            routing_backend="rust_cpu",
        )


def test_auto_greedy_route_backend_falls_back_to_baseline_when_rust_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.routing import dynamic_potential

    road_csr, link_state = _make_routing_fixture()
    potential = dynamic_potential.compute_dynamic_potential_state(
        road_csr,
        destination_node_id=4,
        link_state=link_state,
        routing_backend="baseline",
    )

    def unavailable(**_kwargs):
        raise RuntimeError("Rust CPU routing backend unavailable")

    monkeypatch.setattr(
        dynamic_potential,
        "compute_greedy_route_candidate_rust",
        unavailable,
        raising=False,
    )

    assert dynamic_potential.build_greedy_route_candidate(
        road_csr,
        potential,
        origin_node_id=1,
        routing_backend="auto",
    ) == (12, 13)


def test_auto_greedy_route_backend_skips_incomplete_rust_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.routing import dynamic_potential

    road_csr, link_state = _make_routing_fixture()
    potential = dynamic_potential.compute_dynamic_potential_state(
        road_csr,
        destination_node_id=4,
        link_state=link_state,
        routing_backend="baseline",
    )

    def fail_if_called(**_kwargs):
        raise AssertionError("incomplete rust routing backend must not be called")

    monkeypatch.setattr(
        dynamic_potential,
        "rust_routing_backend_available",
        lambda: False,
    )
    monkeypatch.setattr(
        dynamic_potential,
        "compute_greedy_route_candidate_rust",
        fail_if_called,
        raising=False,
    )

    assert dynamic_potential.build_greedy_route_candidate(
        road_csr,
        potential,
        origin_node_id=1,
        routing_backend="auto",
    ) == (12, 13)


def test_rust_greedy_route_backend_matches_baseline_with_forbidden_turns() -> None:
    from metroflow.backends.rust_cpu import rust_routing_backend_available
    from metroflow.routing import dynamic_potential

    if not rust_routing_backend_available():
        pytest.skip("_metroflow_rust extension is not importable")

    road_csr, link_state = _make_turn_restricted_fixture()
    potential = dynamic_potential.compute_dynamic_potential_state(
        road_csr,
        destination_node_id=4,
        link_state=link_state,
        routing_backend="baseline",
    )
    baseline = dynamic_potential.build_greedy_route_candidate(
        road_csr,
        potential,
        origin_node_id=1,
        routing_backend="baseline",
    )
    accelerated = dynamic_potential.build_greedy_route_candidate(
        road_csr,
        potential,
        origin_node_id=1,
        routing_backend="rust_cpu",
    )

    assert baseline == (10, 12, 13)
    assert accelerated == baseline


def test_greedy_route_topology_cache_ignores_stale_legacy_network_id_key() -> None:
    from metroflow.routing import dynamic_potential

    road_csr, link_state = _make_turn_restricted_fixture()
    potential = dynamic_potential.compute_dynamic_potential_state(
        road_csr,
        destination_node_id=4,
        link_state=link_state,
        routing_backend="baseline",
    )
    dynamic_potential._OUTGOING_LINK_LOOKUP_CACHE.clear()
    dynamic_potential._TURN_SUCCESSOR_CACHE.clear()
    legacy_weak_key = (id(road_csr), int(road_csr.node_count), int(road_csr.link_count))
    dynamic_potential._OUTGOING_LINK_LOOKUP_CACHE[legacy_weak_key] = (
        (0, 2),
        (1,),
        (3,),
        (),
    )

    path = dynamic_potential.build_greedy_route_candidate(
        road_csr,
        potential,
        origin_node_id=1,
        routing_backend="baseline",
    )

    assert path == (10, 12, 13)


def test_route_candidate_refresh_passes_routing_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    from metroflow.routing import candidates
    from metroflow.routing import dynamic_potential

    road_csr, link_state = _make_routing_fixture()
    baseline = dynamic_potential.compute_dynamic_potential_state(
        road_csr,
        destination_node_id=4,
        link_state=link_state,
        routing_backend="baseline",
    )
    calls = []
    greedy_calls = []

    def fake_compute_dynamic_potential_state(**kwargs):
        calls.append(kwargs["routing_backend"])
        return baseline

    def fake_build_greedy_route_candidate(**kwargs):
        greedy_calls.append(kwargs["routing_backend"])
        return (12, 13)

    def fake_route_candidate_metadata_rust(**_kwargs):
        return (2.0,), (1.0,)

    monkeypatch.setattr(
        candidates,
        "compute_dynamic_potential_state",
        fake_compute_dynamic_potential_state,
    )
    monkeypatch.setattr(
        candidates,
        "build_greedy_route_candidate",
        fake_build_greedy_route_candidate,
    )
    monkeypatch.setattr(
        candidates,
        "compute_route_candidate_metadata_rust",
        fake_route_candidate_metadata_rust,
        raising=False,
    )

    candidate_set = candidates.refresh_od_route_candidate_set(
        None,
        road_csr=road_csr,
        link_state=link_state,
        od_key=(1, 4),
        origin_node_id=1,
        destination_node_id=4,
        current_tick=0,
        routing_backend="rust_cpu",
    )

    assert calls == ["rust_cpu"]
    assert greedy_calls == ["rust_cpu"]
    assert candidate_set.candidate_paths == ((12, 13),)


def test_ranked_route_candidate_set_uses_explicit_rust_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.routing import candidates
    from metroflow.routing import dynamic_potential

    road_csr, link_state = _make_routing_fixture()
    baseline = dynamic_potential.compute_dynamic_potential_state(
        road_csr,
        destination_node_id=4,
        link_state=link_state,
        routing_backend="baseline",
    )
    calls = []

    def fake_compute_dynamic_potential_state(**kwargs):
        assert kwargs["routing_backend"] == "rust_cpu"
        return baseline

    def fake_ranked_route_candidates_rust(**kwargs):
        calls.append(kwargs)
        return ((12, 13), (10, 11))

    def fake_route_candidate_metadata_rust(**_kwargs):
        return (2.0, 51.0), (1.0, 1.0)

    monkeypatch.setattr(
        candidates,
        "compute_dynamic_potential_state",
        fake_compute_dynamic_potential_state,
    )
    monkeypatch.setattr(
        candidates,
        "compute_ranked_route_candidates_rust",
        fake_ranked_route_candidates_rust,
        raising=False,
    )
    monkeypatch.setattr(
        candidates,
        "compute_route_candidate_metadata_rust",
        fake_route_candidate_metadata_rust,
        raising=False,
    )

    candidate_set = candidates.create_route_candidate_set(
        road_csr=road_csr,
        link_state=link_state,
        od_key=(1, 4),
        origin_node_id=1,
        destination_node_id=4,
        current_tick=0,
        max_candidates=2,
        routing_backend="rust_cpu",
    )

    assert calls
    assert calls[0]["max_candidates"] == 2
    assert calls[0]["origin_node_index"] == road_csr.node_id_to_index[1]
    assert candidate_set.candidate_paths == ((12, 13), (10, 11))
    assert candidate_set.metadata["candidate_enumeration_backend"] == "rust_cpu_ranked_k"


def test_route_candidate_set_uses_explicit_rust_metadata_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.routing import candidates
    from metroflow.routing import dynamic_potential

    road_csr, link_state = _make_routing_fixture()
    baseline = dynamic_potential.compute_dynamic_potential_state(
        road_csr,
        destination_node_id=4,
        link_state=link_state,
        routing_backend="baseline",
    )
    calls = []

    def fake_compute_dynamic_potential_state(**kwargs):
        assert kwargs["routing_backend"] == "rust_cpu"
        return baseline

    def fake_ranked_route_candidates_rust(**_kwargs):
        return ((12, 13), (10, 11))

    def fake_route_candidate_metadata_rust(**kwargs):
        calls.append(kwargs)
        return (2.0, 51.0), (1.0, 1.0)

    monkeypatch.setattr(
        candidates,
        "compute_dynamic_potential_state",
        fake_compute_dynamic_potential_state,
    )
    monkeypatch.setattr(
        candidates,
        "compute_ranked_route_candidates_rust",
        fake_ranked_route_candidates_rust,
        raising=False,
    )
    monkeypatch.setattr(
        candidates,
        "compute_route_candidate_metadata_rust",
        fake_route_candidate_metadata_rust,
        raising=False,
    )

    candidate_set = candidates.create_route_candidate_set(
        road_csr=road_csr,
        link_state=link_state,
        od_key=(1, 4),
        origin_node_id=1,
        destination_node_id=4,
        current_tick=0,
        max_candidates=2,
        routing_backend="rust_cpu",
    )

    assert calls
    assert calls[0]["candidate_paths"] == ((12, 13), (10, 11))
    assert candidate_set.metadata["candidate_path_costs"] == (2.0, 51.0)
    assert candidate_set.metadata["candidate_path_size_factors"] == (1.0, 1.0)
    assert candidate_set.metadata["candidate_metadata_backend"] == "rust_cpu_candidate_metadata"


def test_auto_route_candidate_metadata_falls_back_to_host_when_rust_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.routing import candidates
    from metroflow.routing import dynamic_potential

    road_csr, link_state = _make_routing_fixture()
    baseline = dynamic_potential.compute_dynamic_potential_state(
        road_csr,
        destination_node_id=4,
        link_state=link_state,
        routing_backend="baseline",
    )

    def fake_compute_dynamic_potential_state(**_kwargs):
        return baseline

    def fake_ranked_route_candidates_rust(**_kwargs):
        return ((12, 13), (10, 11))

    def fake_route_candidate_metadata_rust(**_kwargs):
        raise RuntimeError("Rust CPU routing backend failed: synthetic metadata failure")

    monkeypatch.setattr(
        candidates,
        "compute_dynamic_potential_state",
        fake_compute_dynamic_potential_state,
    )
    monkeypatch.setattr(candidates, "rust_routing_backend_available", lambda: True)
    monkeypatch.setattr(
        candidates,
        "compute_ranked_route_candidates_rust",
        fake_ranked_route_candidates_rust,
        raising=False,
    )
    monkeypatch.setattr(
        candidates,
        "compute_route_candidate_metadata_rust",
        fake_route_candidate_metadata_rust,
        raising=False,
    )

    candidate_set = candidates.create_route_candidate_set(
        road_csr=road_csr,
        link_state=link_state,
        od_key=(1, 4),
        origin_node_id=1,
        destination_node_id=4,
        current_tick=0,
        max_candidates=2,
        routing_backend="auto",
    )

    assert candidate_set.metadata["candidate_path_costs"] == (2.0, 51.0)
    assert candidate_set.metadata["candidate_path_size_factors"] == (1.0, 1.0)
    assert candidate_set.metadata["candidate_metadata_backend"] == "python_host_candidate_metadata"


def test_rust_ranked_route_backend_matches_baseline_when_extension_is_available() -> None:
    from metroflow.backends.rust_cpu import rust_routing_backend_available
    from metroflow.routing import candidates

    if not rust_routing_backend_available():
        pytest.skip("_metroflow_rust extension with ranked routing is not importable")

    road_csr, link_state = _make_routing_fixture()
    baseline = candidates.create_route_candidate_set(
        road_csr=road_csr,
        link_state=link_state,
        od_key=(1, 4),
        origin_node_id=1,
        destination_node_id=4,
        current_tick=0,
        max_candidates=2,
        routing_backend="baseline",
    )
    accelerated = candidates.create_route_candidate_set(
        road_csr=road_csr,
        link_state=link_state,
        od_key=(1, 4),
        origin_node_id=1,
        destination_node_id=4,
        current_tick=0,
        max_candidates=2,
        routing_backend="rust_cpu",
    )

    assert accelerated.candidate_paths == baseline.candidate_paths
    assert accelerated.metadata["candidate_path_costs"] == baseline.metadata[
        "candidate_path_costs"
    ]
    assert accelerated.metadata["candidate_path_size_factors"] == baseline.metadata[
        "candidate_path_size_factors"
    ]
    assert accelerated.metadata["candidate_enumeration_backend"] == "rust_cpu_ranked_k"
    assert accelerated.metadata["candidate_metadata_backend"] == "rust_cpu_candidate_metadata"


def test_route_candidate_refresh_records_effective_routing_backend_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from metroflow.routing import candidates
    from metroflow.routing.dynamic_potential import DynamicPotentialState

    road_csr, link_state = _make_routing_fixture()

    def fake_compute_dynamic_potential_state(**_kwargs):
        return DynamicPotentialState(
            destination_node_id=4,
            destination_node_index=road_csr.node_id_to_index[4],
            node_cost_to_go=(2.0, 1.0, 1.0, 0.0),
            link_travel_time_cost=link_state.travel_time_cost,
            blocked_link_mask=(False, False, False, False),
            metadata={
                "routing_backend": "baseline",
                "routing_backend_requested": "auto",
                "routing_backend_fallback": "rust_cpu_unavailable",
            },
        )

    def fake_build_greedy_route_candidate(**_kwargs):
        return (12, 13)

    monkeypatch.setattr(
        candidates,
        "compute_dynamic_potential_state",
        fake_compute_dynamic_potential_state,
    )
    monkeypatch.setattr(
        candidates,
        "build_greedy_route_candidate",
        fake_build_greedy_route_candidate,
    )

    candidate_set = candidates.refresh_od_route_candidate_set(
        None,
        road_csr=road_csr,
        link_state=link_state,
        od_key=(1, 4),
        origin_node_id=1,
        destination_node_id=4,
        current_tick=0,
        routing_backend="auto",
    )

    assert candidate_set.metadata["routing_backend"] == "baseline"
    assert candidate_set.metadata["routing_backend_requested"] == "auto"
    assert candidate_set.metadata["routing_backend_fallback"] == "rust_cpu_unavailable"
