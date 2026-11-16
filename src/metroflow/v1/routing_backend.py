"""Explicit V1 migration selection; the Python implementation is the oracle."""
import os
from ..active_suffix.routing import candidate_paths


def routing_search(arcs, costs, allowed_turns):
    backend = os.environ.get('METROFLOW_V1_ROUTING_BACKEND', 'python_oracle')
    if backend == 'rust':
        from .native_routing import NativeRoutingGraph
        return NativeRoutingGraph(arcs, costs, allowed_turns).search
    if backend != 'python_oracle':
        raise ValueError('routing backend must be python_oracle or rust')

    def search(origin, destination, k=3, expansion_budget=2000):
        return candidate_paths(arcs, costs, origin, destination, k,
                               expansion_budget, allowed_turns)
    return search
