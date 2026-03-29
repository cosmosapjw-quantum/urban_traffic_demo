from metroflow.traffic.routing import (
    CandidatePath,
    ReroutePolicy,
    candidate_path_k,
    choose_route,
    deterministic_reroute,
    generalized_cost,
    path_size_factor,
    should_reroute,
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
