"""Active-agent packed pool primitives."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

__all__ = [
    "ActiveAgentSlot",
    "ActiveAgentPool",
    "create_active_agent_pool",
    "allocate_active_agent_slot",
    "release_active_agent_slot",
    "read_active_agent_slot",
    "validate_active_agent_pool",
]

Array = np.ndarray


@dataclass(slots=True)
class ActiveAgentSlot:
    """Logical slot payload matching the ActiveAgentSlot data-model fields."""

    slot_id: int = -1
    alive: bool = False
    citizen_id: int = -1
    trip_id: int = -1
    current_link_id: int = -1
    progress_01: float = 0.0
    remaining_route_ptr: int = 0
    dest_node_id: int = -1
    behavior_profile_id: int = -1
    reroute_cooldown_ticks: int = 0
    plugin_memory: dict[int, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.slot_id = int(self.slot_id)
        self.alive = bool(self.alive)
        self.citizen_id = int(self.citizen_id)
        self.trip_id = int(self.trip_id)
        self.current_link_id = int(self.current_link_id)
        self.progress_01 = float(self.progress_01)
        self.remaining_route_ptr = int(self.remaining_route_ptr)
        self.dest_node_id = int(self.dest_node_id)
        self.behavior_profile_id = int(self.behavior_profile_id)
        self.reroute_cooldown_ticks = int(self.reroute_cooldown_ticks)
        if not 0.0 <= self.progress_01 <= 1.0:
            raise ValueError("progress_01 must be in [0, 1]")
        if self.reroute_cooldown_ticks < 0:
            raise ValueError("reroute_cooldown_ticks must be >= 0")
        if not isinstance(self.plugin_memory, dict):
            self.plugin_memory = dict(self.plugin_memory)

    @classmethod
    def spawn(
        cls,
        *,
        citizen_id: int,
        trip_id: int,
        current_link_id: int,
        dest_node_id: int,
        behavior_profile_id: int,
        progress_01: float = 0.0,
        remaining_route_ptr: int = 0,
        reroute_cooldown_ticks: int = 0,
    ) -> "ActiveAgentSlot":
        """Convenience constructor for an alive slot payload before allocation."""

        return cls(
            alive=True,
            citizen_id=citizen_id,
            trip_id=trip_id,
            current_link_id=current_link_id,
            progress_01=progress_01,
            remaining_route_ptr=remaining_route_ptr,
            dest_node_id=dest_node_id,
            behavior_profile_id=behavior_profile_id,
            reroute_cooldown_ticks=reroute_cooldown_ticks,
        )


@dataclass(slots=True)
class ActiveAgentPool:
    """Packed active-agent state plus free-slot stack bookkeeping."""

    capacity: int
    free_slot_stack: Array
    free_slot_count: int
    alive_mask: Array
    alive_count: int
    citizen_id: Array
    trip_id: Array
    current_link_id: Array
    progress_01: Array
    remaining_route_ptr: Array
    dest_node_id: Array
    behavior_profile_id: Array
    reroute_cooldown_ticks: Array
    plugin_memory: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.capacity = int(self.capacity)
        self.free_slot_count = int(self.free_slot_count)
        self.alive_count = int(self.alive_count)

        self.free_slot_stack = np.asarray(self.free_slot_stack, dtype=np.int32)
        self.alive_mask = np.asarray(self.alive_mask, dtype=np.bool_)
        self.citizen_id = np.asarray(self.citizen_id, dtype=np.int32)
        self.trip_id = np.asarray(self.trip_id, dtype=np.int32)
        self.current_link_id = np.asarray(self.current_link_id, dtype=np.int32)
        self.progress_01 = np.asarray(self.progress_01, dtype=np.float32)
        self.remaining_route_ptr = np.asarray(self.remaining_route_ptr, dtype=np.int32)
        self.dest_node_id = np.asarray(self.dest_node_id, dtype=np.int32)
        self.behavior_profile_id = np.asarray(self.behavior_profile_id, dtype=np.int32)
        self.reroute_cooldown_ticks = np.asarray(self.reroute_cooldown_ticks, dtype=np.int32)

        if self.capacity <= 0:
            raise ValueError("capacity must be > 0")
        _validate_pool_array_shapes(self)
        if not (0 <= self.free_slot_count <= self.capacity):
            raise ValueError("free_slot_count out of range")
        if not (0 <= self.alive_count <= self.capacity):
            raise ValueError("alive_count out of range")
        if self.free_slot_count + self.alive_count != self.capacity:
            raise ValueError("free_slot_count + alive_count must equal capacity")
        if not isinstance(self.plugin_memory, dict):
            self.plugin_memory = dict(self.plugin_memory)

    @property
    def available_slots(self) -> int:
        return self.free_slot_count

    @classmethod
    def from_internal_arrays(
        cls,
        *,
        capacity: int,
        free_slot_stack: Any,
        free_slot_count: int,
        alive_mask: Any,
        alive_count: int,
        citizen_id: Any,
        trip_id: Any,
        current_link_id: Any,
        progress_01: Any,
        remaining_route_ptr: Any,
        dest_node_id: Any,
        behavior_profile_id: Any,
        reroute_cooldown_ticks: Any,
        plugin_memory: dict[str, Any] | None = None,
    ) -> "ActiveAgentPool":
        """Build ActiveAgentPool without JAX coercion for trusted hotpath internals."""

        cap = int(capacity)
        free_count = int(free_slot_count)
        alive = int(alive_count)
        if cap <= 0:
            raise ValueError("capacity must be > 0")
        if not (0 <= free_count <= cap):
            raise ValueError("free_slot_count out of range")
        if not (0 <= alive <= cap):
            raise ValueError("alive_count out of range")
        if free_count + alive != cap:
            raise ValueError("free_slot_count + alive_count must equal capacity")

        free_stack = np.asarray(free_slot_stack, dtype=np.int32)
        alive_mask_np = np.asarray(alive_mask, dtype=np.bool_)
        citizen = np.asarray(citizen_id, dtype=np.int32)
        trip = np.asarray(trip_id, dtype=np.int32)
        current_link = np.asarray(current_link_id, dtype=np.int32)
        progress = np.asarray(progress_01, dtype=np.float32)
        route_ptr = np.asarray(remaining_route_ptr, dtype=np.int32)
        dest = np.asarray(dest_node_id, dtype=np.int32)
        behavior = np.asarray(behavior_profile_id, dtype=np.int32)
        cooldown = np.asarray(reroute_cooldown_ticks, dtype=np.int32)
        _validate_pool_array_shapes_numpy(
            capacity=cap,
            free_slot_stack=free_stack,
            alive_mask=alive_mask_np,
            citizen_id=citizen,
            trip_id=trip,
            current_link_id=current_link,
            progress_01=progress,
            remaining_route_ptr=route_ptr,
            dest_node_id=dest,
            behavior_profile_id=behavior,
            reroute_cooldown_ticks=cooldown,
        )

        out_obj = object.__new__(cls)
        out_obj.capacity = cap
        out_obj.free_slot_stack = free_stack
        out_obj.free_slot_count = free_count
        out_obj.alive_mask = alive_mask_np
        out_obj.alive_count = alive
        out_obj.citizen_id = citizen
        out_obj.trip_id = trip
        out_obj.current_link_id = current_link
        out_obj.progress_01 = progress
        out_obj.remaining_route_ptr = route_ptr
        out_obj.dest_node_id = dest
        out_obj.behavior_profile_id = behavior
        out_obj.reroute_cooldown_ticks = cooldown
        out_obj.plugin_memory = dict(plugin_memory or {})
        return out_obj


def create_active_agent_pool(capacity: int) -> ActiveAgentPool:
    """Create an empty active-agent packed pool with all slots free."""

    capacity = int(capacity)
    if capacity <= 0:
        raise ValueError("capacity must be > 0")

    free_slot_stack = np.arange(capacity - 1, -1, -1, dtype=np.int32)
    zeros_i = np.zeros((capacity,), dtype=np.int32)
    return ActiveAgentPool.from_internal_arrays(
        capacity=capacity,
        free_slot_stack=free_slot_stack,
        free_slot_count=capacity,
        alive_mask=np.zeros((capacity,), dtype=np.bool_),
        alive_count=0,
        citizen_id=zeros_i - 1,
        trip_id=zeros_i - 1,
        current_link_id=zeros_i - 1,
        progress_01=np.zeros((capacity,), dtype=np.float32),
        remaining_route_ptr=zeros_i,
        dest_node_id=zeros_i - 1,
        behavior_profile_id=zeros_i - 1,
        reroute_cooldown_ticks=zeros_i,
    )


def allocate_active_agent_slot(
    pool: ActiveAgentPool,
    slot_payload: ActiveAgentSlot,
) -> tuple[ActiveAgentPool, int]:
    """Allocate one free slot and write packed slot fields.

    Returns the updated pool and the allocated `slot_id`. The free-slot stack is
    treated as LIFO so recently released slots are reused first.
    """

    if pool.free_slot_count <= 0:
        raise RuntimeError("active-agent pool is full")
    if not slot_payload.alive:
        raise ValueError("slot_payload.alive must be True for allocation")

    top_index = pool.free_slot_count - 1
    slot_id = int(pool.free_slot_stack[top_index])
    _validate_slot_index(slot_id, pool.capacity)

    next_pool = replace(
        pool,
        free_slot_count=pool.free_slot_count - 1,
        alive_count=pool.alive_count + 1,
        alive_mask=_array_set_1d(pool.alive_mask, slot_id, True),
        citizen_id=_array_set_1d(pool.citizen_id, slot_id, slot_payload.citizen_id),
        trip_id=_array_set_1d(pool.trip_id, slot_id, slot_payload.trip_id),
        current_link_id=_array_set_1d(
            pool.current_link_id,
            slot_id,
            slot_payload.current_link_id
        ),
        progress_01=_array_set_1d(pool.progress_01, slot_id, slot_payload.progress_01),
        remaining_route_ptr=_array_set_1d(
            pool.remaining_route_ptr,
            slot_id,
            slot_payload.remaining_route_ptr
        ),
        dest_node_id=_array_set_1d(pool.dest_node_id, slot_id, slot_payload.dest_node_id),
        behavior_profile_id=_array_set_1d(
            pool.behavior_profile_id,
            slot_id,
            slot_payload.behavior_profile_id
        ),
        reroute_cooldown_ticks=_array_set_1d(
            pool.reroute_cooldown_ticks,
            slot_id,
            slot_payload.reroute_cooldown_ticks
        ),
    )
    return next_pool, slot_id


def release_active_agent_slot(pool: ActiveAgentPool, slot_id: int) -> ActiveAgentPool:
    """Release an alive slot back to the free-slot stack (LIFO reuse)."""

    slot_id = int(slot_id)
    _validate_slot_index(slot_id, pool.capacity)
    if not bool(pool.alive_mask[slot_id]):
        raise ValueError(f"slot {slot_id} is not alive")
    if pool.free_slot_count >= pool.capacity:
        raise RuntimeError("free_slot_stack overflow")

    next_free_stack = _array_set_1d(pool.free_slot_stack, pool.free_slot_count, slot_id)
    return replace(
        pool,
        free_slot_stack=next_free_stack,
        free_slot_count=pool.free_slot_count + 1,
        alive_count=pool.alive_count - 1,
        alive_mask=_array_set_1d(pool.alive_mask, slot_id, False),
        citizen_id=_array_set_1d(pool.citizen_id, slot_id, -1),
        trip_id=_array_set_1d(pool.trip_id, slot_id, -1),
        current_link_id=_array_set_1d(pool.current_link_id, slot_id, -1),
        progress_01=_array_set_1d(pool.progress_01, slot_id, 0.0),
        remaining_route_ptr=_array_set_1d(pool.remaining_route_ptr, slot_id, 0),
        dest_node_id=_array_set_1d(pool.dest_node_id, slot_id, -1),
        behavior_profile_id=_array_set_1d(pool.behavior_profile_id, slot_id, -1),
        reroute_cooldown_ticks=_array_set_1d(pool.reroute_cooldown_ticks, slot_id, 0),
    )


def read_active_agent_slot(pool: ActiveAgentPool, slot_id: int) -> ActiveAgentSlot:
    """Read one logical slot view from packed arrays."""

    slot_id = int(slot_id)
    _validate_slot_index(slot_id, pool.capacity)
    raw_plugin_memory = pool.plugin_memory.get(slot_id, {})
    slot_plugin_memory = (
        dict(raw_plugin_memory) if isinstance(raw_plugin_memory, dict) else {}
    )

    return ActiveAgentSlot(
        slot_id=slot_id,
        alive=bool(pool.alive_mask[slot_id]),
        citizen_id=int(pool.citizen_id[slot_id]),
        trip_id=int(pool.trip_id[slot_id]),
        current_link_id=int(pool.current_link_id[slot_id]),
        progress_01=float(pool.progress_01[slot_id]),
        remaining_route_ptr=int(pool.remaining_route_ptr[slot_id]),
        dest_node_id=int(pool.dest_node_id[slot_id]),
        behavior_profile_id=int(pool.behavior_profile_id[slot_id]),
        reroute_cooldown_ticks=int(pool.reroute_cooldown_ticks[slot_id]),
        plugin_memory=slot_plugin_memory,
    )


def validate_active_agent_pool(pool: ActiveAgentPool) -> tuple[str, ...]:
    """Return consistency violations for the packed pool (empty tuple == valid)."""

    issues: list[str] = []

    alive_count_from_mask = int(np.sum(pool.alive_mask).item())
    if pool.alive_count != alive_count_from_mask:
        issues.append("alive_count != sum(alive_mask)")

    if pool.free_slot_count + pool.alive_count != pool.capacity:
        issues.append("free_slot_count + alive_count != capacity")

    free_ids = [
        int(x)
        for x in np.asarray(pool.free_slot_stack[: pool.free_slot_count]).tolist()
    ]
    if len(set(free_ids)) != len(free_ids):
        issues.append("duplicate slot ids in free_slot_stack")

    if any(slot_id < 0 or slot_id >= pool.capacity for slot_id in free_ids):
        issues.append("free_slot_stack contains out-of-range slot ids")

    alive_ids = {
        int(i)
        for i, is_alive in enumerate(np.asarray(pool.alive_mask).tolist())
        if bool(is_alive)
    }
    if alive_ids.intersection(free_ids):
        issues.append("slot ids appear in both alive set and free_slot_stack")

    progress = np.asarray(pool.progress_01)
    if bool(np.any(progress < 0.0)) or bool(np.any(progress > 1.0)):
        issues.append("progress_01 contains values outside [0, 1]")

    cooldown = np.asarray(pool.reroute_cooldown_ticks)
    if bool(np.any(cooldown < 0)):
        issues.append("reroute_cooldown_ticks contains negative values")

    return tuple(issues)


def _validate_pool_array_shapes(pool: ActiveAgentPool) -> None:
    expected = (pool.capacity,)
    arrays = (
        ("free_slot_stack", pool.free_slot_stack),
        ("alive_mask", pool.alive_mask),
        ("citizen_id", pool.citizen_id),
        ("trip_id", pool.trip_id),
        ("current_link_id", pool.current_link_id),
        ("progress_01", pool.progress_01),
        ("remaining_route_ptr", pool.remaining_route_ptr),
        ("dest_node_id", pool.dest_node_id),
        ("behavior_profile_id", pool.behavior_profile_id),
        ("reroute_cooldown_ticks", pool.reroute_cooldown_ticks),
    )
    for name, array in arrays:
        if tuple(array.shape) != expected:
            raise ValueError(f"{name} must have shape {expected}, got {tuple(array.shape)}")


def _array_set_1d(array: Any, index: int, value: Any) -> Any:
    out = np.asarray(array).copy()
    out[int(index)] = value
    return out


def _validate_pool_array_shapes_numpy(
    *,
    capacity: int,
    free_slot_stack: np.ndarray,
    alive_mask: np.ndarray,
    citizen_id: np.ndarray,
    trip_id: np.ndarray,
    current_link_id: np.ndarray,
    progress_01: np.ndarray,
    remaining_route_ptr: np.ndarray,
    dest_node_id: np.ndarray,
    behavior_profile_id: np.ndarray,
    reroute_cooldown_ticks: np.ndarray,
) -> None:
    expected = (int(capacity),)
    arrays = (
        ("free_slot_stack", free_slot_stack),
        ("alive_mask", alive_mask),
        ("citizen_id", citizen_id),
        ("trip_id", trip_id),
        ("current_link_id", current_link_id),
        ("progress_01", progress_01),
        ("remaining_route_ptr", remaining_route_ptr),
        ("dest_node_id", dest_node_id),
        ("behavior_profile_id", behavior_profile_id),
        ("reroute_cooldown_ticks", reroute_cooldown_ticks),
    )
    for name, array in arrays:
        if tuple(np.asarray(array).shape) != expected:
            raise ValueError(f"{name} must have shape {expected}, got {tuple(np.asarray(array).shape)}")


def _validate_slot_index(slot_id: int, capacity: int) -> None:
    if slot_id < 0 or slot_id >= capacity:
        raise IndexError(f"slot_id {slot_id} out of range for capacity {capacity}")
