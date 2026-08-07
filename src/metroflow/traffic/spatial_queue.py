"""Physical link storage and deterministic active-agent progress helpers."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from metroflow.sim.active_agents import ActiveAgentPool

__all__ = ["advance_agent_link_progress", "compute_link_storage_capacity"]


def compute_link_storage_capacity(
    road_csr: Any,
    *,
    jam_spacing_m: float = 7.5,
) -> np.ndarray:
    """Return finite storage vehicles from physical lane length."""

    spacing = float(jam_spacing_m)
    if not math.isfinite(spacing) or not 2.0 <= spacing <= 20.0:
        raise ValueError("jam_spacing_m must be finite and in [2, 20]")
    links = tuple(getattr(road_csr, "links", ()) or ())
    if not links:
        raise ValueError("road_csr must contain links")
    storage = np.asarray(
        [
            max(
                1,
                int(
                    math.floor(
                        float(link.length_m) * int(link.lanes) / spacing
                    )
                ),
            )
            for link in links
        ],
        dtype=np.float32,
    )
    storage.flags.writeable = False
    return storage


def advance_agent_link_progress(
    pool: ActiveAgentPool,
    *,
    road_csr: Any,
    tick_seconds: float,
    skip_slot_ids: set[int] | None = None,
) -> tuple[ActiveAgentPool, dict[str, int]]:
    """Advance alive agents through their current physical link."""

    if not isinstance(pool, ActiveAgentPool):
        raise TypeError("pool must be an ActiveAgentPool")
    tick_seconds = float(tick_seconds)
    if not math.isfinite(tick_seconds) or tick_seconds <= 0.0:
        raise ValueError("tick_seconds must be finite and > 0")
    link_id_to_index = dict(getattr(road_csr, "link_id_to_index", {}) or {})
    links = tuple(getattr(road_csr, "links", ()) or ())
    if not links or not link_id_to_index:
        raise ValueError("road_csr must contain indexed links")
    skip_slots = {int(slot_id) for slot_id in (skip_slot_ids or set())}
    progress = np.asarray(pool.progress_01, dtype=np.float32).copy()
    progressed_count = 0
    for slot_id, alive in enumerate(
        np.asarray(pool.alive_mask, dtype=np.bool_).tolist()
    ):
        if not bool(alive) or slot_id in skip_slots:
            continue
        current_link_id = int(pool.current_link_id[slot_id])
        link_index = link_id_to_index.get(current_link_id)
        if link_index is None:
            raise RuntimeError(
                "active agent references missing physical link: "
                f"slot={slot_id} link={current_link_id}"
            )
        link = links[int(link_index)]
        increment = (
            float(link.free_flow_speed_mps) * tick_seconds / float(link.length_m)
        )
        previous_progress = float(progress[slot_id])
        next_progress = min(1.0, previous_progress + increment)
        progress[slot_id] = np.float32(next_progress)
        if next_progress > previous_progress + 1.0e-9:
            progressed_count += 1
    alive_mask = np.asarray(pool.alive_mask, dtype=np.bool_)
    alive_progress = progress[alive_mask]
    exit_queue_count = int(np.sum(alive_progress >= np.float32(1.0 - 1.0e-6)))
    return (
        ActiveAgentPool.from_internal_arrays(
            capacity=pool.capacity,
            free_slot_stack=pool.free_slot_stack,
            free_slot_count=pool.free_slot_count,
            alive_mask=pool.alive_mask,
            alive_count=pool.alive_count,
            citizen_id=pool.citizen_id,
            trip_id=pool.trip_id,
            current_link_id=pool.current_link_id,
            progress_01=progress,
            remaining_route_ptr=pool.remaining_route_ptr,
            dest_node_id=pool.dest_node_id,
            behavior_profile_id=pool.behavior_profile_id,
            reroute_cooldown_ticks=pool.reroute_cooldown_ticks,
            plugin_memory=pool.plugin_memory,
        ),
        {
            "active_agent_progressed_this_tick": progressed_count,
            "active_agent_exit_queue_count": exit_queue_count,
            "active_agent_in_transit_count": int(pool.alive_count)
            - exit_queue_count,
        },
    )
