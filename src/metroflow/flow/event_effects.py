"""Apply active traffic-event effects to flow link state (US2/T049)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import numpy as np

from metroflow.flow.events import TrafficEvent, TrafficEventStatus
from metroflow.flow.state import LinkState, validate_link_state

__all__ = [
    "LinkEventEffectsResult",
    "apply_active_event_effects_to_link_state",
    "compute_incident_capacity_multiplier_from_events",
]

_BRIDGE_GROUP_LINK_IDS_CACHE: dict[tuple[int, int, int], dict[int, tuple[int, ...]]] = {}
_BRIDGE_GROUP_LINK_IDS_CACHE_MAX = 32


@dataclass(slots=True)
class LinkEventEffectsResult:
    """Result of applying active event effects to a `LinkState`."""

    link_state: LinkState
    applied_event_ids: tuple[int, ...]
    ignored_event_ids: tuple[int, ...]
    affected_link_ids: tuple[int, ...]


@dataclass(slots=True)
class _LinkEventEffectPlan:
    """Host-side event-effect planning output prior to array application."""

    update_indices: tuple[int, ...]
    update_multipliers: tuple[float, ...]
    applied_event_ids: tuple[int, ...]
    ignored_event_ids: tuple[int, ...]
    affected_link_ids: tuple[int, ...]


def apply_active_event_effects_to_link_state(
    *,
    road_csr: Any,
    link_state: LinkState,
    active_events: Iterable[TrafficEvent | Mapping[str, Any]],
    validate: bool = False,
) -> LinkEventEffectsResult:
    """Apply active event effects to `link_state.incident_capacity_multiplier`.

    T049 minimal behavior:
    - Supports target scopes: `link_ids`, `bridge_group_id`
    - Supports effect models: `closure`, `capacity_reduction`
    - Ignores non-active / unsupported / unresolved events safely
    - Combines multiple effects by taking the minimum multiplier per link
    """

    multiplier, applied, ignored, affected = compute_incident_capacity_multiplier_from_events(
        road_csr=road_csr,
        active_events=active_events,
        link_count=link_state.link_count,
    )
    effective_capacity = np.asarray(link_state.capacity_veh_per_tick, dtype=np.float32) * np.asarray(
        multiplier,
        dtype=np.float32,
    )
    next_flags = np.asarray(link_state.outflow_vehicles, dtype=np.float32) > (
        effective_capacity + np.float32(1e-6)
    )
    next_link_state = LinkState.from_internal_arrays(
        queue_vehicles=link_state.queue_vehicles,
        inflow_vehicles=link_state.inflow_vehicles,
        outflow_vehicles=link_state.outflow_vehicles,
        travel_time_cost=link_state.travel_time_cost,
        capacity_veh_per_tick=link_state.capacity_veh_per_tick,
        incident_capacity_multiplier=multiplier,
        capacity_violation_flags=next_flags,
        metadata=link_state.metadata,
    )
    if validate:
        issues = validate_link_state(next_link_state)
        if issues:
            raise ValueError(f"Invalid LinkState after event effects: {', '.join(issues)}")
    return LinkEventEffectsResult(
        link_state=next_link_state,
        applied_event_ids=applied,
        ignored_event_ids=ignored,
        affected_link_ids=affected,
    )


def compute_incident_capacity_multiplier_from_events(
    *,
    road_csr: Any,
    active_events: Iterable[TrafficEvent | Mapping[str, Any]],
    link_count: int | None = None,
) -> tuple[np.ndarray, tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    """Compute per-link incident capacity multipliers from active events."""

    links = tuple(getattr(road_csr, "links", ()) or ())
    link_id_to_index = dict(getattr(road_csr, "link_id_to_index", {}) or {})
    if link_count is None:
        link_count = int(getattr(road_csr, "link_count", len(links)))
    link_count = int(link_count)
    if link_count < 0:
        raise ValueError("link_count must be >= 0")
    _validate_link_axis_compatibility(
        links=links,
        link_id_to_index=link_id_to_index,
        road_csr_link_count=int(getattr(road_csr, "link_count", link_count)),
        expected_link_count=link_count,
    )

    base = np.ones((link_count,), dtype=np.float32)
    if link_count == 0:
        return base, (), (), ()

    bridge_group_to_link_ids = _bridge_group_link_ids_cached(road_csr, links)
    link_is_blockable: dict[int, bool] = {
        int(getattr(link, "link_id", -1)): bool(getattr(link, "is_blockable", True))
        for link in links
    }

    plan = _plan_event_effect_applications(
        active_events=active_events,
        bridge_group_to_link_ids=bridge_group_to_link_ids,
        link_id_to_index=link_id_to_index,
        link_is_blockable=link_is_blockable,
        link_count=link_count,
    )
    multiplier = _apply_event_multiplier_updates_core(
        base_multiplier=base,
        update_indices=plan.update_indices,
        update_multipliers=plan.update_multipliers,
    )
    return (multiplier, plan.applied_event_ids, plan.ignored_event_ids, plan.affected_link_ids)


def _coerce_event(event: TrafficEvent | Mapping[str, Any]) -> TrafficEvent:
    if isinstance(event, TrafficEvent):
        return event
    return TrafficEvent(**dict(event))


def _plan_event_effect_applications(
    *,
    active_events: Iterable[TrafficEvent | Mapping[str, Any]],
    bridge_group_to_link_ids: Mapping[int, tuple[int, ...]],
    link_id_to_index: Mapping[int, int],
    link_is_blockable: Mapping[int, bool],
    link_count: int,
) -> _LinkEventEffectPlan:
    """Host-side planning of event target link updates and bookkeeping."""

    applied_event_ids: list[int] = []
    ignored_event_ids: list[int] = []
    affected_link_ids: set[int] = set()
    per_index_min_multiplier: dict[int, float] = {}

    for raw_event in tuple(active_events):
        event = _coerce_event(raw_event)
        if event.status is not TrafficEventStatus.ACTIVE:
            ignored_event_ids.append(int(event.event_id))
            continue
        target_link_ids = _resolve_target_link_ids(
            event=event,
            bridge_group_to_link_ids=bridge_group_to_link_ids,
        )
        if not target_link_ids:
            ignored_event_ids.append(int(event.event_id))
            continue
        per_event_multiplier = _event_capacity_multiplier(event)
        if per_event_multiplier is None:
            ignored_event_ids.append(int(event.event_id))
            continue

        resolved_any = False
        for link_id in target_link_ids:
            link_id_i = int(link_id)
            idx = link_id_to_index.get(link_id_i)
            if idx is None or idx < 0 or idx >= link_count:
                continue
            if event.effect_model == "closure" and not link_is_blockable.get(link_id_i, True):
                continue
            old = per_index_min_multiplier.get(int(idx), 1.0)
            per_index_min_multiplier[int(idx)] = min(float(old), float(per_event_multiplier))
            affected_link_ids.add(link_id_i)
            resolved_any = True
        if resolved_any:
            applied_event_ids.append(int(event.event_id))
        else:
            ignored_event_ids.append(int(event.event_id))

    if per_index_min_multiplier:
        ordered = tuple(sorted(per_index_min_multiplier.items()))
        update_indices = tuple(int(idx) for idx, _ in ordered)
        update_multipliers = tuple(float(val) for _, val in ordered)
    else:
        update_indices = ()
        update_multipliers = ()

    return _LinkEventEffectPlan(
        update_indices=update_indices,
        update_multipliers=update_multipliers,
        applied_event_ids=tuple(applied_event_ids),
        ignored_event_ids=tuple(ignored_event_ids),
        affected_link_ids=tuple(sorted(affected_link_ids)),
    )


def _apply_event_multiplier_updates_core(
    *,
    base_multiplier: np.ndarray,
    update_indices: tuple[int, ...],
    update_multipliers: tuple[float, ...],
) -> np.ndarray:
    """Array core applying preplanned link multiplier updates."""

    if not update_indices:
        return base_multiplier
    out = np.asarray(base_multiplier, dtype=np.float32).copy()
    idx = np.asarray(update_indices, dtype=np.int32)
    vals = np.asarray(update_multipliers, dtype=np.float32)
    out[idx] = np.minimum(out[idx], vals)
    return out


def _bridge_group_link_ids(road_csr: Any, links: tuple[Any, ...]) -> dict[int, tuple[int, ...]]:
    out: dict[int, tuple[int, ...]] = {}
    bridge_crossings = tuple(getattr(road_csr, "bridge_crossings", ()) or ())
    for crossing in bridge_crossings:
        group_id = int(getattr(crossing, "bridge_group_id"))
        try:
            ids = tuple(int(v) for v in tuple(getattr(crossing, "link_ids", ())))
        except Exception:
            ids = ()
        if ids:
            out[group_id] = ids
    if out:
        return out
    # Fallback: derive from links when bridge_crossings are unavailable.
    tmp: dict[int, list[int]] = {}
    for link in links:
        group_id = getattr(link, "bridge_group_id", None)
        if group_id is None:
            continue
        tmp.setdefault(int(group_id), []).append(int(getattr(link, "link_id")))
    return {gid: tuple(ids) for gid, ids in tmp.items()}


def _bridge_group_link_ids_cached(road_csr: Any, links: tuple[Any, ...]) -> dict[int, tuple[int, ...]]:
    key = (
        id(road_csr),
        int(getattr(road_csr, "link_count", len(links))),
        len(tuple(getattr(road_csr, "bridge_crossings", ()) or ())),
    )
    cached = _BRIDGE_GROUP_LINK_IDS_CACHE.get(key)
    if cached is not None:
        return cached
    value = _bridge_group_link_ids(road_csr, links)
    if len(_BRIDGE_GROUP_LINK_IDS_CACHE) >= _BRIDGE_GROUP_LINK_IDS_CACHE_MAX:
        _BRIDGE_GROUP_LINK_IDS_CACHE.pop(next(iter(_BRIDGE_GROUP_LINK_IDS_CACHE)))
    _BRIDGE_GROUP_LINK_IDS_CACHE[key] = value
    return value


def _resolve_target_link_ids(
    *,
    event: TrafficEvent,
    bridge_group_to_link_ids: Mapping[int, tuple[int, ...]],
) -> tuple[int, ...]:
    target_scope = dict(event.target_scope)
    if "link_ids" in target_scope:
        try:
            return tuple(int(v) for v in tuple(target_scope.get("link_ids", ())))
        except Exception:
            return ()
    if "bridge_group_id" in target_scope:
        try:
            group_id = int(target_scope["bridge_group_id"])
        except Exception:
            return ()
        return tuple(bridge_group_to_link_ids.get(group_id, ()))
    return ()


def _event_capacity_multiplier(event: TrafficEvent) -> float | None:
    if event.effect_model == "closure":
        return 0.0
    if event.effect_model == "capacity_reduction":
        return max(0.0, min(1.0, 1.0 - float(event.severity)))
    return None


def _validate_link_axis_compatibility(
    *,
    links: tuple[Any, ...],
    link_id_to_index: Mapping[int, int],
    road_csr_link_count: int,
    expected_link_count: int,
) -> None:
    if expected_link_count < 0:
        raise ValueError("expected_link_count must be >= 0")
    if road_csr_link_count < 0:
        raise ValueError("road_csr.link_count must be >= 0")
    if road_csr_link_count != len(links):
        raise ValueError("road_csr.link_count does not match len(road_csr.links)")
    if expected_link_count != road_csr_link_count:
        raise ValueError("LinkState link axis does not match road_csr link axis")
    if len(link_id_to_index) != len(links):
        raise ValueError("road_csr.link_id_to_index size does not match road_csr.links")
    for idx in link_id_to_index.values():
        idx_i = int(idx)
        if idx_i < 0 or idx_i >= expected_link_count:
            raise ValueError("road_csr.link_id_to_index contains out-of-range index")
