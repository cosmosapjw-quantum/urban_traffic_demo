"""Compile deterministic static node-interface metadata from road geometry."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from numbers import Integral, Real
from types import MappingProxyType
from typing import Mapping, Protocol, Sequence

from metroflow.map.road_geometry import RoadGeometryCatalog

__all__ = [
    "NodeRuleSet",
    "CompiledNodeInterface",
    "NodeInterfaceCatalog",
    "compile_node_interfaces",
]


@dataclass(frozen=True, slots=True)
class NodeRuleSet:
    through_continuity: bool = True
    turn_pocket_separation: bool = True
    signal_eligible: bool = True

    def __post_init__(self) -> None:
        for field_name in (
            "through_continuity",
            "turn_pocket_separation",
            "signal_eligible",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise ValueError(f"{field_name} must be a bool")


@dataclass(frozen=True, slots=True)
class CompiledNodeInterface:
    node_id: int
    incoming_link_ids: tuple[int, ...]
    outgoing_link_ids: tuple[int, ...]
    through_link_pairs: tuple[tuple[int, int], ...]
    turn_pocket_incoming_link_ids: tuple[int, ...]
    non_through_movement_count: int
    signal_eligible: bool

    def __post_init__(self) -> None:
        node_id = _strict_nonnegative_int(self.node_id, "node_id")
        incoming = _canonical_id_tuple(self.incoming_link_ids, "incoming_link_ids")
        outgoing = _canonical_id_tuple(self.outgoing_link_ids, "outgoing_link_ids")
        through_pairs = _canonical_link_pairs(self.through_link_pairs)
        pockets = _canonical_id_tuple(
            self.turn_pocket_incoming_link_ids,
            "turn_pocket_incoming_link_ids",
        )
        non_through = _strict_nonnegative_int(
            self.non_through_movement_count,
            "non_through_movement_count",
        )
        if not isinstance(self.signal_eligible, bool):
            raise ValueError("signal_eligible must be a bool")
        unknown_pairs = [
            pair
            for pair in through_pairs
            if pair[0] not in incoming or pair[1] not in outgoing
        ]
        if unknown_pairs:
            raise ValueError(
                "through_link_pairs must reference declared incoming/outgoing links"
            )
        if any(link_id not in incoming for link_id in pockets):
            raise ValueError(
                "turn_pocket_incoming_link_ids must reference incoming links"
            )
        object.__setattr__(self, "node_id", node_id)
        object.__setattr__(self, "incoming_link_ids", incoming)
        object.__setattr__(self, "outgoing_link_ids", outgoing)
        object.__setattr__(self, "through_link_pairs", through_pairs)
        object.__setattr__(self, "turn_pocket_incoming_link_ids", pockets)
        object.__setattr__(self, "non_through_movement_count", non_through)

    def _canonical_payload(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "incoming_link_ids": self.incoming_link_ids,
            "outgoing_link_ids": self.outgoing_link_ids,
            "through_link_pairs": self.through_link_pairs,
            "turn_pocket_incoming_link_ids": self.turn_pocket_incoming_link_ids,
            "non_through_movement_count": self.non_through_movement_count,
            "signal_eligible": self.signal_eligible,
        }


@dataclass(frozen=True, slots=True)
class NodeInterfaceCatalog:
    interfaces: tuple[CompiledNodeInterface, ...]
    _interface_by_node_id: Mapping[int, CompiledNodeInterface] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if any(not isinstance(item, CompiledNodeInterface) for item in self.interfaces):
            raise TypeError(
                "interfaces must contain CompiledNodeInterface instances"
            )
        interfaces = tuple(sorted(self.interfaces, key=lambda item: item.node_id))
        interface_by_node_id = {item.node_id: item for item in interfaces}
        if len(interface_by_node_id) != len(interfaces):
            raise ValueError("duplicate compiled node_id values")
        object.__setattr__(self, "interfaces", interfaces)
        object.__setattr__(
            self,
            "_interface_by_node_id",
            MappingProxyType(interface_by_node_id),
        )

    @property
    def fingerprint(self) -> str:
        return _sha256_json(
            [item._canonical_payload() for item in self.interfaces]
        )

    def interface_for_node(self, node_id: int) -> CompiledNodeInterface:
        try:
            return self._interface_by_node_id[int(node_id)]
        except KeyError as exc:
            raise KeyError(f"no compiled interface for node_id {int(node_id)}") from exc


class _NodeLike(Protocol):
    node_id: int


class _LinkLike(Protocol):
    link_id: int
    src_node_id: int
    dst_node_id: int
    lanes: int


def compile_node_interfaces(
    *,
    nodes: Sequence[_NodeLike],
    links: Sequence[_LinkLike],
    road_geometry: RoadGeometryCatalog,
    rule_set: NodeRuleSet | None = None,
    through_angle_tolerance_deg: float = 30.0,
) -> NodeInterfaceCatalog:
    """Compile static node continuity and control eligibility metadata."""

    rules = rule_set if rule_set is not None else NodeRuleSet()
    if not isinstance(rules, NodeRuleSet):
        raise TypeError("rule_set must be a NodeRuleSet")
    tolerance = _strict_real(
        through_angle_tolerance_deg,
        "through_angle_tolerance_deg",
    )
    if not math.isfinite(tolerance) or tolerance < 0.0 or tolerance >= 90.0:
        raise ValueError("through_angle_tolerance_deg must be in [0, 90)")
    node_ids = {
        _strict_nonnegative_int(node.node_id, "node_id") for node in nodes
    }
    if len(node_ids) != len(nodes):
        raise ValueError("nodes must have unique node_id values")
    link_by_id = {
        _strict_nonnegative_int(link.link_id, "link_id"): link for link in links
    }
    if len(link_by_id) != len(links):
        raise ValueError("links must have unique link_id values")
    incoming: dict[int, list[int]] = {node_id: [] for node_id in node_ids}
    outgoing: dict[int, list[int]] = {node_id: [] for node_id in node_ids}
    for link in links:
        link_id = _strict_nonnegative_int(link.link_id, "link_id")
        src = _strict_nonnegative_int(link.src_node_id, "src_node_id")
        dst = _strict_nonnegative_int(link.dst_node_id, "dst_node_id")
        if src not in node_ids or dst not in node_ids:
            raise ValueError(f"link {link_id} references a missing node")
        road_geometry.assignment_for_link(link_id)
        outgoing[src].append(link_id)
        incoming[dst].append(link_id)

    interfaces: list[CompiledNodeInterface] = []
    for node_id in sorted(node_ids):
        incoming_ids = tuple(sorted(incoming[node_id]))
        outgoing_ids = tuple(sorted(outgoing[node_id]))
        legal_pairs = tuple(
            (incoming_id, outgoing_id)
            for incoming_id in incoming_ids
            for outgoing_id in outgoing_ids
            if int(link_by_id[incoming_id].src_node_id)
            != int(link_by_id[outgoing_id].dst_node_id)
        )
        geometric_through_pairs = tuple(
            pair
            for pair in legal_pairs
            if _deflection_degrees(
                road_geometry.points_for_link(pair[0]),
                road_geometry.points_for_link(pair[1]),
            )
            <= tolerance
        )
        through_pairs = (
            geometric_through_pairs
            if rules.through_continuity
            else ()
        )
        turn_pockets = (
            tuple(
                incoming_id
                for incoming_id in incoming_ids
                if _strict_nonnegative_int(
                    link_by_id[incoming_id].lanes,
                    "lanes",
                )
                >= 2
                and sum(pair[0] == incoming_id for pair in legal_pairs) > 1
            )
            if rules.turn_pocket_separation
            else ()
        )
        non_through_movement_count = max(
            0,
            len(legal_pairs) - len(geometric_through_pairs),
        )
        neighbor_count = len(
            {
                int(link_by_id[link_id].src_node_id) for link_id in incoming_ids
            }
            | {int(link_by_id[link_id].dst_node_id) for link_id in outgoing_ids}
        )
        interfaces.append(
            CompiledNodeInterface(
                node_id=node_id,
                incoming_link_ids=incoming_ids,
                outgoing_link_ids=outgoing_ids,
                through_link_pairs=through_pairs,
                turn_pocket_incoming_link_ids=turn_pockets,
                non_through_movement_count=non_through_movement_count,
                signal_eligible=bool(
                    rules.signal_eligible
                    and neighbor_count >= 3
                    and len(incoming_ids) >= 2
                    and len(outgoing_ids) >= 2
                ),
            )
        )
    return NodeInterfaceCatalog(tuple(interfaces))


def _deflection_degrees(
    incoming_points: tuple[tuple[float, float], ...],
    outgoing_points: tuple[tuple[float, float], ...],
) -> float:
    incoming_vector = (
        incoming_points[-1][0] - incoming_points[-2][0],
        incoming_points[-1][1] - incoming_points[-2][1],
    )
    outgoing_vector = (
        outgoing_points[1][0] - outgoing_points[0][0],
        outgoing_points[1][1] - outgoing_points[0][1],
    )
    incoming_norm = math.hypot(*incoming_vector)
    outgoing_norm = math.hypot(*outgoing_vector)
    if incoming_norm <= 0.0 or outgoing_norm <= 0.0:
        raise ValueError("centerline tangent vectors must have positive length")
    cosine = (
        incoming_vector[0] * outgoing_vector[0]
        + incoming_vector[1] * outgoing_vector[1]
    ) / (incoming_norm * outgoing_norm)
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _sha256_json(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _strict_nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{field_name} must be an integer")
    converted = int(value)
    if converted < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return converted


def _strict_real(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field_name} must be a real number")
    return float(value)


def _canonical_id_tuple(values: object, field_name: str) -> tuple[int, ...]:
    try:
        resolved = tuple(
            _strict_nonnegative_int(value, field_name) for value in values  # type: ignore[union-attr]
        )
    except TypeError as exc:
        raise ValueError(f"{field_name} must be an iterable of integers") from exc
    if len(set(resolved)) != len(resolved):
        raise ValueError(f"{field_name} must contain unique values")
    return tuple(sorted(resolved))


def _canonical_link_pairs(values: object) -> tuple[tuple[int, int], ...]:
    try:
        raw_pairs = tuple(values)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ValueError("through_link_pairs must be an iterable of pairs") from exc
    pairs: list[tuple[int, int]] = []
    for raw_pair in raw_pairs:
        try:
            pair = tuple(raw_pair)
        except TypeError as exc:
            raise ValueError("through_link_pairs must contain pairs") from exc
        if len(pair) != 2:
            raise ValueError("through_link_pairs must contain pairs")
        pairs.append(
            (
                _strict_nonnegative_int(pair[0], "through incoming link_id"),
                _strict_nonnegative_int(pair[1], "through outgoing link_id"),
            )
        )
    if len(set(pairs)) != len(pairs):
        raise ValueError("through_link_pairs must contain unique pairs")
    return tuple(sorted(pairs))
