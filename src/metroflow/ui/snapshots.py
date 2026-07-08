"""UI snapshot source builders (pre-packet intermediate representation)."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

from metroflow.flow.state import LinkState
from metroflow.sim.invariants import InvariantReport
from metroflow.sim.state import SimulationState

__all__ = ["build_ui_snapshot_source"]


def build_ui_snapshot_source(
    *,
    state: SimulationState,
    invariant_report: InvariantReport,
    max_link_samples: int = 64,
) -> dict[str, Any]:
    """Build a `UISnapshotSource` from current simulation state.

    This is a pre-packet intermediate object used by later UI packetization tasks.
    The shape matches the data-model/contract while keeping simulation internals
    decoupled from transport schema.
    """

    metrics_state = state.dynamic.metrics_state if isinstance(state.dynamic.metrics_state, Mapping) else {}
    routing_static = state.static.routing_static if isinstance(state.static.routing_static, Mapping) else {}
    road_csr = routing_static.get("road_csr")

    return {
        "network_geometry_version": state.static.ui_network_geometry_version,
        "sampled_link_congestion": _sampled_link_congestion(
            road_csr=road_csr,
            flow_link_state=state.dynamic.flow_link_state,
            max_link_samples=max_link_samples,
        ),
        "active_events": _active_events_overlay(state.dynamic.event_state),
        "clock_state": {
            "day_type": state.day_type.value,
            "time_band": state.time_band.value,
            "sim_tick": int(state.tick_index),
        },
        "summary_metrics": _summary_metrics(
            state=state,
            invariant_report=invariant_report,
            metrics_state=metrics_state,
        ),
    }


def _sampled_link_congestion(
    *,
    road_csr: Any,
    flow_link_state: Any,
    max_link_samples: int,
) -> tuple[dict[str, Any], ...]:
    if road_csr is None or not isinstance(flow_link_state, LinkState):
        return ()
    links = getattr(road_csr, "links", None)
    if links is None:
        return ()
    try:
        links_len = len(links)
    except Exception:
        return ()

    link_count = int(flow_link_state.link_count)
    if link_count <= 0:
        return ()
    if links_len != link_count:
        return ()
    sample_n = max(1, min(int(max_link_samples), link_count))
    if sample_n <= 0:
        return ()

    if sample_n == 1:
        sample_indices = (0,)
    elif sample_n == link_count:
        sample_indices = tuple(range(link_count))
    else:
        # Integer downsample points without invoking float-heavy JAX kernels.
        sample_indices = tuple((i * (link_count - 1)) // (sample_n - 1) for i in range(sample_n))
    sample_idx = np.asarray(sample_indices, dtype=np.int32)

    queue_src = flow_link_state.queue_vehicles
    cap_src = flow_link_state.effective_capacity_vehicles
    cost_src = flow_link_state.travel_time_cost
    free_cost_src = flow_link_state.metadata.get("free_flow_travel_time_cost", flow_link_state.travel_time_cost)
    flags_src = flow_link_state.capacity_violation_flags
    if (
        _shape0(queue_src) != link_count
        or _shape0(cap_src) != link_count
        or _shape0(cost_src) != link_count
        or _shape0(flags_src) != link_count
    ):
        return ()

    queue = np.asarray(queue_src[sample_idx], dtype=np.float32)
    cap = np.asarray(cap_src[sample_idx], dtype=np.float32)
    cost = np.asarray(cost_src[sample_idx], dtype=np.float32)
    if _shape0(free_cost_src) == link_count:
        free_cost = np.asarray(free_cost_src[sample_idx], dtype=np.float32)
    else:
        free_cost = np.asarray(cost_src[sample_idx], dtype=np.float32)
    flags = np.asarray(flags_src[sample_idx], dtype=np.bool_)

    congestion_ratio = queue / np.maximum(cap, 1e-6)
    slowdown_ratio = cost / np.maximum(free_cost, 1e-6)

    out: list[dict[str, Any]] = []
    for pos, idx in enumerate(sample_indices):
        try:
            link = links[idx]
        except Exception:
            return ()
        out.append(
            {
                "link_id": int(link.link_id),
                "road_class": str(link.road_class.value if hasattr(link.road_class, "value") else link.road_class),
                "queue_vehicles": float(queue[pos]),
                "effective_capacity": float(cap[pos]),
                "congestion_ratio": float(congestion_ratio[pos]),
                "travel_time_cost": float(cost[pos]),
                "slowdown_ratio": float(slowdown_ratio[pos]),
                "capacity_flag": bool(flags[pos]),
            }
        )
    return tuple(out)


def _active_events_overlay(event_state: Any) -> tuple[Any, ...]:
    if event_state is None:
        return ()
    if isinstance(event_state, Mapping):
        for key in ("active_events", "events", "active"):
            value = event_state.get(key)
            if value is not None:
                try:
                    return tuple(value)
                except TypeError:
                    return ()
    try:
        value = getattr(event_state, "active_events")
    except Exception:
        return ()
    try:
        return tuple(value)
    except TypeError:
        return ()


def _summary_metrics(
    *,
    state: SimulationState,
    invariant_report: InvariantReport,
    metrics_state: Mapping[str, Any],
) -> dict[str, Any]:
    active_pool = state.dynamic.active_agent_pool
    active_agents = int(getattr(active_pool, "alive_count", 0) or 0)
    demand_state = state.dynamic.demand_state if isinstance(state.dynamic.demand_state, Mapping) else {}
    queued = int(demand_state.get("queued_trip_requests", metrics_state.get("queued_trip_requests", 0)))
    pending = int(demand_state.get("pending_trip_requests", metrics_state.get("pending_trip_requests", queued)))
    completed_total = int(metrics_state.get("completed_trips_total", 0))
    failed_total = int(metrics_state.get("failed_trips_total", 0))
    capacity_violation_count = int(metrics_state.get("capacity_violation_count", 0))

    return {
        "active_agents": active_agents,
        "queued_trip_requests": queued,
        "pending_trip_requests": pending,
        "completed_trips_total": completed_total,
        "failed_trips_total": failed_total,
        "capacity_violation_count": capacity_violation_count,
        "negative_queue_detected": invariant_report.counters.negative_queue_violations > 0,
        "invariant_total_violations": int(invariant_report.counters.total_violations),
    }


def _shape0(array_like: Any) -> int | None:
    try:
        shape = getattr(array_like, "shape")
        if shape is None:
            return None
        if len(shape) < 1:
            return None
        return int(shape[0])
    except Exception:
        return None
