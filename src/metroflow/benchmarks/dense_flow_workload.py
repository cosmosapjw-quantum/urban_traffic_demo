"""Reusable deterministic dense-flow workload and comparison helpers."""

from __future__ import annotations

import hashlib
from time import perf_counter_ns
from typing import Mapping

import numpy as np

from metroflow.flow.engine import FlowUpdateBackend, update_link_node_flow
from metroflow.flow.state import LinkState, NodeState

__all__ = [
    "build_dense_flow_jax_inputs",
    "build_dense_flow_scale_state",
    "fingerprint_flow_output",
    "flow_output_arrays",
    "max_abs_flow_output_diff",
    "run_flow_update_steps",
]


def build_dense_flow_scale_state(
    *,
    link_count: int,
    turns_per_link: int,
    seed: int,
) -> tuple[LinkState, NodeState]:
    rng = np.random.default_rng(int(seed))
    link_count = int(link_count)
    turns_per_link = int(turns_per_link)
    if link_count < 2:
        raise ValueError("link_count must be >= 2")
    if turns_per_link < 1:
        raise ValueError("turns_per_link must be >= 1")
    turn_count = link_count * turns_per_link
    queue = rng.uniform(0.0, 6.0, size=link_count).astype(np.float32)
    capacity = rng.uniform(1.0, 8.0, size=link_count).astype(np.float32)
    base_travel = rng.uniform(1.0, 4.0, size=link_count).astype(np.float32)
    from_idx = np.repeat(np.arange(link_count, dtype=np.int32), turns_per_link)
    offsets = np.tile(np.arange(1, turns_per_link + 1, dtype=np.int32), link_count)
    to_idx = np.asarray((from_idx + offsets) % link_count, dtype=np.int32)
    turn_demand = rng.uniform(0.05, 3.0, size=turn_count).astype(np.float32)
    turn_priority = rng.uniform(0.5, 2.0, size=turn_count).astype(np.float32)
    turn_is_forbidden = ((np.arange(turn_count, dtype=np.int32) + int(seed)) % 29) == 0
    signal_timer = rng.integers(0, 4, size=link_count, dtype=np.int32)
    link_state = LinkState.from_internal_arrays(
        queue_vehicles=queue,
        inflow_vehicles=np.zeros((link_count,), dtype=np.float32),
        outflow_vehicles=np.zeros((link_count,), dtype=np.float32),
        travel_time_cost=base_travel,
        capacity_veh_per_tick=capacity,
        incident_capacity_multiplier=np.ones((link_count,), dtype=np.float32),
        capacity_violation_flags=np.zeros((link_count,), dtype=np.bool_),
        metadata={"free_flow_travel_time_cost": base_travel},
    )
    node_state = NodeState.from_internal_arrays(
        turn_from_link_index=from_idx,
        turn_to_link_index=to_idx,
        turn_demand=turn_demand,
        turn_supply=np.zeros((turn_count,), dtype=np.float32),
        turn_flow=np.zeros((turn_count,), dtype=np.float32),
        signal_phase_index=np.zeros((link_count,), dtype=np.int32),
        signal_phase_timer=signal_timer,
        metadata={
            "turn_base_priority": turn_priority,
            "turn_is_forbidden": turn_is_forbidden,
        },
    )
    return link_state, node_state


def build_dense_flow_jax_inputs(
    link_state: LinkState,
    node_state: NodeState,
) -> dict[str, np.ndarray]:
    """Return normalized host arrays for the optional JAX experiment boundary."""

    return {
        "queue_vehicles": np.asarray(link_state.queue_vehicles, dtype=np.float32),
        "effective_capacity_vehicles": np.asarray(
            link_state.effective_capacity_vehicles,
            dtype=np.float32,
        ),
        "base_travel_time_cost": np.asarray(
            link_state.metadata["free_flow_travel_time_cost"],
            dtype=np.float32,
        ),
        "turn_from_link_index": np.asarray(
            node_state.turn_from_link_index,
            dtype=np.int32,
        ),
        "turn_to_link_index": np.asarray(
            node_state.turn_to_link_index,
            dtype=np.int32,
        ),
        "turn_demand": np.asarray(node_state.turn_demand, dtype=np.float32),
        "turn_priority": np.asarray(
            node_state.metadata["turn_base_priority"],
            dtype=np.float32,
        ),
        "turn_is_forbidden": np.asarray(
            node_state.metadata["turn_is_forbidden"],
            dtype=np.bool_,
        ),
        "signal_phase_timer": np.asarray(
            node_state.signal_phase_timer,
            dtype=np.int32,
        ),
    }


def run_flow_update_steps(
    link_state: LinkState,
    node_state: NodeState,
    *,
    num_steps: int,
    flow_backend: FlowUpdateBackend,
) -> tuple[LinkState, NodeState, int]:
    current_link = link_state
    current_node = node_state
    start_ns = perf_counter_ns()
    for _ in range(int(num_steps)):
        result = update_link_node_flow(
            current_link,
            current_node,
            validate=False,
            flow_backend=flow_backend,
        )
        current_link = result.link_state
        current_node = result.node_state
    return current_link, current_node, max(0, perf_counter_ns() - start_ns)


def flow_output_arrays(
    link_state: LinkState,
    node_state: NodeState,
) -> dict[str, np.ndarray]:
    return {
        "queue_vehicles": np.asarray(link_state.queue_vehicles, dtype=np.float32),
        "inflow_vehicles": np.asarray(link_state.inflow_vehicles, dtype=np.float32),
        "outflow_vehicles": np.asarray(link_state.outflow_vehicles, dtype=np.float32),
        "travel_time_cost": np.asarray(link_state.travel_time_cost, dtype=np.float32),
        "capacity_violation_flags": np.asarray(
            link_state.capacity_violation_flags,
            dtype=np.bool_,
        ),
        "turn_demand": np.asarray(node_state.turn_demand, dtype=np.float32),
        "turn_supply": np.asarray(node_state.turn_supply, dtype=np.float32),
        "turn_flow": np.asarray(node_state.turn_flow, dtype=np.float32),
        "signal_phase_timer": np.asarray(
            node_state.signal_phase_timer,
            dtype=np.int32,
        ),
    }


def fingerprint_flow_output(output: Mapping[str, np.ndarray]) -> str:
    digest = hashlib.sha256()
    for key in sorted(output):
        array = np.ascontiguousarray(output[key])
        digest.update(key.encode("utf-8"))
        digest.update(str(array.dtype).encode("utf-8"))
        digest.update(np.asarray(array.shape, dtype=np.int64).tobytes())
        digest.update(array.tobytes())
    return digest.hexdigest()


def max_abs_flow_output_diff(
    baseline: Mapping[str, np.ndarray],
    probe: Mapping[str, np.ndarray],
) -> float:
    if set(baseline) != set(probe):
        return float("inf")
    max_diff = 0.0
    for key, baseline_value in baseline.items():
        probe_value = probe[key]
        baseline_array = np.asarray(baseline_value)
        probe_array = np.asarray(probe_value)
        if baseline_array.shape != probe_array.shape:
            return float("inf")
        if baseline_array.dtype.kind in {"b", "i", "u"}:
            if not np.array_equal(baseline_array, probe_array):
                return float("inf")
            continue
        if not np.all(np.isfinite(baseline_array)) or not np.all(
            np.isfinite(probe_array)
        ):
            return float("inf")
        diff = np.max(
            np.abs(
                np.asarray(baseline_array, dtype=np.float32)
                - np.asarray(probe_array, dtype=np.float32)
            ),
            initial=0.0,
        )
        if not np.isfinite(diff):
            return float("inf")
        max_diff = max(max_diff, float(diff))
    return max_diff
