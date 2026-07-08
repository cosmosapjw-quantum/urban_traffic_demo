from dataclasses import replace

from metroflow.core.state import GraphState, TrafficState, make_empty_world_state
from metroflow.traffic.routing import (
    CandidatePath,
    GeneralizedCostWeights,
    ODRouteChoiceResult,
    ODRouteEvaluationRequest,
    ReroutePolicy,
    candidate_path_k,
    choose_route,
    deterministic_reroute,
    evaluate_od_route_set,
    generalized_cost,
    path_size_factor,
    should_reroute,
)
from metroflow.traffic import routing as routing_module


def make_materialized_graph(num_edges: int) -> GraphState:
    return GraphState(
        num_nodes=max(num_edges + 1, 0),
        num_edges=num_edges,
        edge_src=tuple(range(num_edges)),
        edge_dst=tuple(range(1, num_edges + 1)),
        edge_class=("road",) * num_edges,
    )


def make_routing_world(edge_travel_time: tuple[float, ...]):
    num_edges = len(edge_travel_time)
    return replace(
        make_empty_world_state(seed=7),
        graph=make_materialized_graph(num_edges),
        traffic=TrafficState(
            step=3,
            edge_queue=(0.0,) * num_edges,
            edge_stock=(1.0,) * num_edges,
            edge_travel_time=edge_travel_time,
        ),
    )


def make_two_path_world():
    return replace(
        make_empty_world_state(seed=7),
        graph=GraphState(
            num_nodes=4,
            num_edges=4,
            edge_src=(0, 1, 0, 2),
            edge_dst=(1, 3, 2, 3),
            edge_class=("road", "road", "road", "road"),
        ),
        traffic=TrafficState(
            step=3,
            edge_queue=(0.0, 0.0, 0.0, 0.0),
            edge_stock=(1.0, 1.0, 1.0, 1.0),
            edge_travel_time=(50.0, 1.0, 1.0, 1.0),
        ),
    )


def test_path_size_factor_positive():
    ps = path_size_factor((2.0, 3.0), (1, 2))
    assert ps > 0.0


def test_candidate_path_k_is_deterministic_and_bounded():
    paths = (
        CandidatePath(path_id=3, edge_ids=(4, 5), path_size=0.9),
        CandidatePath(path_id=1, edge_ids=(1, 2), path_size=1.2),
        CandidatePath(path_id=2, edge_ids=(2, 3), path_size=1.1),
    )

    selected = candidate_path_k(paths, k=2)

    assert tuple(path.path_id for path in selected) == (1, 2)


def test_generalized_cost_respects_explicit_weights():
    cost = generalized_cost(10.0, 2.0, event_delay=3.0, turn_penalty=1.0)
    assert cost == 16.0


def test_generalized_cost_includes_density_delay_when_weighted():
    cost = generalized_cost(
        10.0,
        2.0,
        event_delay=3.0,
        turn_penalty=1.0,
        density_delay=4.0,
    )

    assert cost == 16.0

    weighted = generalized_cost(
        10.0,
        2.0,
        event_delay=3.0,
        turn_penalty=1.0,
        density_delay=4.0,
        weights=GeneralizedCostWeights(density_weight=0.5),
    )

    assert weighted == 18.0


def test_generalized_cost_rejects_negative_density_delay():
    try:
        generalized_cost(10.0, 2.0, density_delay=-1.0)
    except ValueError as exc:
        assert "non-negative" in str(exc)
    else:
        raise AssertionError("expected negative density delay to fail")


def test_should_reroute_hard_event():
    pol = ReroutePolicy()
    assert should_reroute(True, 10.0, 10.0, 0, pol) is True


def test_should_reroute_refractory():
    pol = ReroutePolicy(eta_degradation_threshold=0.2, refractory_steps=5)
    assert should_reroute(False, 13.0, 10.0, 5, pol) is True
    assert should_reroute(False, 13.0, 10.0, 4, pol) is False


def test_deterministic_reroute_falls_back_to_best_candidate():
    paths = (
        CandidatePath(path_id=1, edge_ids=(1, 2), path_size=1.0),
        CandidatePath(path_id=2, edge_ids=(3, 4), path_size=1.4),
    )

    choice = deterministic_reroute(
        current_path_id=9,
        candidates=paths,
        expected_costs=(15.0, 12.0),
        hard_event_on_route=True,
        eta_now=14.0,
        eta_ref=10.0,
        steps_since_last_reroute=0,
        policy=ReroutePolicy(),
        k=2,
    )

    assert choice.rerouted is True
    assert choice.path_id == 2


def test_choose_route_keeps_costs_paired_with_unsorted_candidates():
    paths = (
        CandidatePath(path_id=2, edge_ids=(3, 4), path_size=1.0),
        CandidatePath(path_id=1, edge_ids=(1, 2), path_size=1.0),
    )

    choice = choose_route(paths, expected_costs=(5.0, 50.0), k=2)

    assert choice.path_id == 2


def test_deterministic_reroute_keeps_costs_paired_with_unsorted_candidates():
    paths = (
        CandidatePath(path_id=2, edge_ids=(3, 4), path_size=1.0),
        CandidatePath(path_id=1, edge_ids=(1, 2), path_size=1.0),
    )

    choice = deterministic_reroute(
        current_path_id=9,
        candidates=paths,
        expected_costs=(5.0, 50.0),
        hard_event_on_route=True,
        eta_now=14.0,
        eta_ref=10.0,
        steps_since_last_reroute=0,
        policy=ReroutePolicy(),
        k=2,
    )

    assert choice.rerouted is True
    assert choice.path_id == 2


def test_evaluate_od_route_set_returns_truthful_od_route_choice():
    world = make_routing_world((4.0, 4.0, 3.0))
    candidates = (
        CandidatePath(path_id=20, edge_ids=(0, 1), path_size=1.0),
        CandidatePath(path_id=10, edge_ids=(2,), path_size=1.0),
    )

    result = evaluate_od_route_set(
        world,
        origin_id="origin-a",
        destination_id="destination-b",
        candidates=candidates,
        k=2,
    )

    assert result == ODRouteChoiceResult(
        name="od_route_choice",
        origin_id="origin-a",
        destination_id="destination-b",
        path_id=10,
        observed_cost=3.0,
        utility=-3.0,
        rerouted=False,
    )


def test_evaluate_od_route_set_rejects_invalid_route_set_inputs():
    world = make_routing_world((2.0, 3.0))

    try:
        evaluate_od_route_set(
            world,
            origin_id="o",
            destination_id="d",
            candidates=tuple(),
            k=1,
        )
    except ValueError as exc:
        assert "candidate" in str(exc).lower()
    else:
        raise AssertionError("expected empty candidate set to fail")

    try:
        evaluate_od_route_set(
            world,
            origin_id="o",
            destination_id="d",
            candidates=(CandidatePath(path_id=1, edge_ids=(0,)),),
            k=0,
        )
    except ValueError as exc:
        assert "k" in str(exc).lower()
    else:
        raise AssertionError("expected non-positive k to fail")

    try:
        evaluate_od_route_set(
            world,
            origin_id="o",
            destination_id="d",
            candidates=(CandidatePath(path_id=1, edge_ids=(9,)),),
            k=1,
        )
    except ValueError as exc:
        assert "edge" in str(exc).lower()
    else:
        raise AssertionError("expected out-of-range edge id to fail")


def test_evaluate_od_route_set_changes_choice_when_network_costs_change():
    candidates = (
        CandidatePath(path_id=1, edge_ids=(0, 1), path_size=1.0),
        CandidatePath(path_id=2, edge_ids=(2,), path_size=1.0),
    )

    first_world = make_routing_world((6.0, 6.0, 20.0))
    second_world = make_routing_world((9.0, 9.0, 5.0))

    first_choice = evaluate_od_route_set(
        first_world,
        origin_id="o",
        destination_id="d",
        candidates=candidates,
        k=2,
    )
    second_choice = evaluate_od_route_set(
        second_world,
        origin_id="o",
        destination_id="d",
        candidates=candidates,
        k=2,
    )

    assert first_choice.path_id == 1
    assert second_choice.path_id == 2


def test_evaluate_od_route_set_is_deterministic_and_read_only_with_unsorted_candidates():
    world = make_routing_world((8.0, 1.0, 6.0))
    candidates = (
        CandidatePath(path_id=2, edge_ids=(2,), path_size=1.0),
        CandidatePath(path_id=1, edge_ids=(0, 1), path_size=1.0),
    )
    request = ODRouteEvaluationRequest(
        origin_id="origin-a",
        destination_id="destination-b",
        candidates=candidates,
        k=2,
        world=world,
    )

    first_choice = evaluate_od_route_set(
        request.world,
        origin_id=request.origin_id,
        destination_id=request.destination_id,
        candidates=request.candidates,
        k=request.k,
        weights=request.weights,
    )
    second_choice = evaluate_od_route_set(
        request.world,
        origin_id=request.origin_id,
        destination_id=request.destination_id,
        candidates=request.candidates,
        k=request.k,
        weights=request.weights,
    )

    assert first_choice == second_choice
    assert first_choice.path_id == 2
    assert request.world == world


def test_dynamic_potential_candidate_prefers_lower_current_travel_time():
    world = make_two_path_world()

    potential = routing_module.compute_dynamic_potential_state(world, destination_node=3)
    candidate = routing_module.build_dynamic_potential_candidate(
        world,
        origin_node=0,
        destination_node=3,
        path_id=10,
    )

    assert potential.node_cost_to_go[0] == 2.0
    assert candidate == CandidatePath(path_id=10, edge_ids=(2, 3), path_size=1.0)


def test_dynamic_potential_candidate_respects_blocked_edges():
    world = make_two_path_world()

    candidate = routing_module.build_dynamic_potential_candidate(
        world,
        origin_node=0,
        destination_node=3,
        blocked_edge_ids=(2,),
    )

    assert candidate == CandidatePath(path_id=0, edge_ids=(0, 1), path_size=1.0)


def test_dynamic_potential_candidate_returns_none_when_unreachable():
    world = make_two_path_world()

    candidate = routing_module.build_dynamic_potential_candidate(
        world,
        origin_node=0,
        destination_node=3,
        blocked_edge_ids=(0, 2),
    )

    assert candidate is None
