"""Routing package public exports."""

from __future__ import annotations

from importlib import import_module

from metroflow.routing.dynamic_potential import (
    BaselineNextLinkScores,
    DynamicPotentialState,
    build_greedy_route_candidate,
    compute_dynamic_potential_state,
    compute_next_link_action_costs_core,
    score_legal_next_links,
)

__all__ = [
    "DynamicPotentialState",
    "BaselineNextLinkScores",
    "RouteChoiceProfile",
    "generate_route_choice_profiles",
    "build_route_choice_profiles",
    "sample_behavior_profile_ids",
    "RerouteDecisionReason",
    "RerouteDecision",
    "compute_reroute_trigger_score",
    "decide_reroute_vs_persist",
    "RouteCandidateSet",
    "RouteCandidateRefreshPolicy",
    "create_route_candidate_set",
    "build_route_candidate_set",
    "refresh_od_route_candidate_set",
    "should_refresh_route_candidate_set",
    "RoutingDecisionMixResult",
    "normalize_route_preference_scores_core",
    "mix_route_candidate_scores_core",
    "select_mixed_route_index_core",
    "mix_route_candidate_scores",
    "build_routing_decision_mix",
    "select_mixed_route_index",
    "choose_mixed_route_index",
    "compute_dynamic_potential_state",
    "compute_next_link_action_costs_core",
    "score_legal_next_links",
    "build_greedy_route_candidate",
]

_LAZY_EXPORTS = {
    "RouteChoiceProfile": ("metroflow.routing.behavior_profiles", "RouteChoiceProfile"),
    "generate_route_choice_profiles": ("metroflow.routing.behavior_profiles", "generate_route_choice_profiles"),
    "build_route_choice_profiles": ("metroflow.routing.behavior_profiles", "build_route_choice_profiles"),
    "sample_behavior_profile_ids": ("metroflow.routing.behavior_profiles", "sample_behavior_profile_ids"),
    "RerouteDecisionReason": ("metroflow.routing.reroute_policy", "RerouteDecisionReason"),
    "RerouteDecision": ("metroflow.routing.reroute_policy", "RerouteDecision"),
    "compute_reroute_trigger_score": ("metroflow.routing.reroute_policy", "compute_reroute_trigger_score"),
    "decide_reroute_vs_persist": ("metroflow.routing.reroute_policy", "decide_reroute_vs_persist"),
    "RouteCandidateSet": ("metroflow.routing.candidates", "RouteCandidateSet"),
    "RouteCandidateRefreshPolicy": ("metroflow.routing.candidates", "RouteCandidateRefreshPolicy"),
    "create_route_candidate_set": ("metroflow.routing.candidates", "create_route_candidate_set"),
    "build_route_candidate_set": ("metroflow.routing.candidates", "build_route_candidate_set"),
    "refresh_od_route_candidate_set": ("metroflow.routing.candidates", "refresh_od_route_candidate_set"),
    "should_refresh_route_candidate_set": ("metroflow.routing.candidates", "should_refresh_route_candidate_set"),
    "RoutingDecisionMixResult": ("metroflow.routing.policy_mixer", "RoutingDecisionMixResult"),
    "normalize_route_preference_scores_core": ("metroflow.routing.policy_mixer", "normalize_route_preference_scores_core"),
    "mix_route_candidate_scores_core": ("metroflow.routing.policy_mixer", "mix_route_candidate_scores_core"),
    "select_mixed_route_index_core": ("metroflow.routing.policy_mixer", "select_mixed_route_index_core"),
    "mix_route_candidate_scores": ("metroflow.routing.policy_mixer", "mix_route_candidate_scores"),
    "build_routing_decision_mix": ("metroflow.routing.policy_mixer", "build_routing_decision_mix"),
    "select_mixed_route_index": ("metroflow.routing.policy_mixer", "select_mixed_route_index"),
    "choose_mixed_route_index": ("metroflow.routing.policy_mixer", "choose_mixed_route_index"),
}


def __getattr__(name: str):
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
