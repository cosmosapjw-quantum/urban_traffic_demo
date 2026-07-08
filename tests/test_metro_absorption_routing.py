from importlib import import_module


def make_csr_and_link_state():
    graph = import_module("metroflow.city.graph")
    flow_state = import_module("metroflow.flow.state")
    csr = graph.build_road_network_csr(
        nodes=(graph.Node(1), graph.Node(2), graph.Node(3), graph.Node(4)),
        links=(
            graph.RoadLink(10, 1, 2, graph.RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
            graph.RoadLink(11, 2, 4, graph.RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
            graph.RoadLink(12, 1, 3, graph.RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
            graph.RoadLink(13, 3, 4, graph.RoadClass.ARTERIAL, 100.0, 10.0, 5.0),
        ),
        turns=(
            graph.TurnMovement(10, 11, graph.TurnType.THROUGH),
            graph.TurnMovement(12, 13, graph.TurnType.THROUGH),
        ),
    )
    link_state = flow_state.LinkState(
        queue_vehicles=(0.0, 0.0, 0.0, 0.0),
        inflow_vehicles=(0.0, 0.0, 0.0, 0.0),
        outflow_vehicles=(0.0, 0.0, 0.0, 0.0),
        travel_time_cost=(50.0, 1.0, 1.0, 1.0),
        capacity_veh_per_tick=(5.0, 5.0, 5.0, 5.0),
        incident_capacity_multiplier=(1.0, 1.0, 1.0, 1.0),
    )
    return graph, csr, link_state


def test_advanced_dynamic_potential_prefers_less_congested_path():
    _graph, csr, link_state = make_csr_and_link_state()
    dynamic_potential = import_module("metroflow.routing.dynamic_potential")

    potential = dynamic_potential.compute_dynamic_potential_state(
        csr,
        destination_node_id=4,
        link_state=link_state,
    )
    path = dynamic_potential.build_greedy_route_candidate(
        csr,
        potential,
        origin_node_id=1,
    )

    assert path == (12, 13)


def test_route_candidate_refresh_reuses_until_interval_or_incident():
    _graph, csr, link_state = make_csr_and_link_state()
    candidates = import_module("metroflow.routing.candidates")

    policy = candidates.RouteCandidateRefreshPolicy(refresh_interval_ticks=8)
    first = candidates.refresh_od_route_candidate_set(
        None,
        road_csr=csr,
        link_state=link_state,
        od_key=("z1", "z4"),
        origin_node_id=1,
        destination_node_id=4,
        current_tick=0,
        policy=policy,
    )
    reused = candidates.refresh_od_route_candidate_set(
        first,
        road_csr=csr,
        link_state=link_state,
        od_key=("z1", "z4"),
        origin_node_id=1,
        destination_node_id=4,
        current_tick=1,
        policy=policy,
    )

    assert reused is first
    assert first.candidate_paths == ((12, 13),)


def test_route_candidate_set_builds_ranked_diverse_baseline_paths():
    _graph, csr, link_state = make_csr_and_link_state()
    candidates = import_module("metroflow.routing.candidates")

    candidate_set = candidates.create_route_candidate_set(
        road_csr=csr,
        link_state=link_state,
        od_key=("z1", "z4"),
        origin_node_id=1,
        destination_node_id=4,
        current_tick=0,
        max_candidates=2,
    )

    assert candidate_set.candidate_ids == (0, 1)
    assert candidate_set.candidate_paths == ((12, 13), (10, 11))
    assert candidate_set.metadata["candidate_generation_mode"] == "baseline_ranked_k"
    assert candidate_set.metadata["max_candidates_returned"] == 2


def test_policy_mixer_falls_back_when_adaptive_scores_are_invalid():
    policy_blend = import_module("metroflow.learning.policy_blend")
    policy_mixer = import_module("metroflow.routing.policy_mixer")
    config = import_module("metroflow.sim.config")

    result = policy_mixer.mix_route_candidate_scores(
        baseline_scores=(5.0, 2.0, 3.0),
        adaptive_scores=(1.0, float("nan"), 6.0),
        blend_state=policy_blend.PolicyBlendState(lambda_mix=0.2, baseline_only_mode=False),
        target_lambda=0.4,
        bounds=config.LearningMixBounds(lambda_min=0.0, lambda_max=1.0),
    )

    assert result.selected_index == 1
    assert result.blend_state.baseline_only_mode is True
    assert result.blend_state.fallback_reason == policy_blend.PolicyBlendFallbackReason.INVALID_OUTPUT


def test_reroute_policy_respects_cooldown():
    behavior_profiles = import_module("metroflow.routing.behavior_profiles")
    reroute_policy = import_module("metroflow.routing.reroute_policy")
    profile = behavior_profiles.RouteChoiceProfile(
        behavior_profile_id=2,
        delay_sensitivity=1.0,
        reroute_willingness=0.9,
        persistence_bias=0.0,
        exploration_bias=0.2,
    )

    decision = reroute_policy.decide_reroute_vs_persist(
        profile=profile,
        current_remaining_cost=12.0,
        candidate_remaining_cost=6.0,
        incident_active=True,
        reroute_cooldown_ticks=2,
    )

    assert decision.should_reroute is False
    assert decision.reason is reroute_policy.RerouteDecisionReason.COOLDOWN
    assert decision.next_reroute_cooldown_ticks == 1
