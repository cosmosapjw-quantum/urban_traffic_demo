"""Compile deterministic static turn authority for generated road networks.

The table is exhaustive over every declared incoming/outgoing pair at each
compiled node interface.  An immediate return to the node that the incoming
link came from is retained as an explicit ``U_TURN_FORBIDDEN`` row.  This makes
the absence of a permitted movement fail closed: consumers never need to treat
a missing turn table as permission to traverse arbitrary adjacent links.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from numbers import Real
from types import MappingProxyType
from typing import Mapping, Protocol, Sequence

from metroflow.map.node_compiler import NodeInterfaceCatalog
from metroflow.map.road_geometry import RoadGeometryCatalog

from .graph import RoadClass, TurnMovement, TurnType

__all__ = [
    "TurnAuthorityCatalog",
    "compile_turn_authority",
]

TurnPair = tuple[int, int]


class _LinkLike(Protocol):
    link_id: int
    src_node_id: int
    dst_node_id: int
    road_class: RoadClass | str


@dataclass(frozen=True, slots=True)
class TurnAuthorityCatalog:
    """Canonical turn rows plus an unambiguous pair-to-row index."""

    movements: tuple[TurnMovement, ...]
    _movement_by_pair: Mapping[TurnPair, TurnMovement] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _index_by_pair: Mapping[TurnPair, int] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        raw_movements = tuple(self.movements)
        if any(not isinstance(movement, TurnMovement) for movement in raw_movements):
            raise TypeError("movements must contain TurnMovement instances")
        movements = tuple(
            sorted(
                raw_movements,
                key=lambda movement: (
                    int(movement.from_link_id),
                    int(movement.to_link_id),
                ),
            )
        )
        movement_by_pair = {
            (movement.from_link_id, movement.to_link_id): movement
            for movement in movements
        }
        if len(movement_by_pair) != len(movements):
            raise ValueError("turn authority must contain unique link pairs")
        object.__setattr__(self, "movements", movements)
        object.__setattr__(
            self,
            "_movement_by_pair",
            MappingProxyType(movement_by_pair),
        )
        object.__setattr__(
            self,
            "_index_by_pair",
            MappingProxyType(
                {
                    pair: index
                    for index, pair in enumerate(movement_by_pair)
                }
            ),
        )

    @property
    def pair_to_index(self) -> Mapping[TurnPair, int]:
        """Read-only mapping from ``(from_link_id, to_link_id)`` to row index."""

        return self._index_by_pair

    @property
    def fingerprint(self) -> str:
        """Stable fingerprint of ordered turn authority and control metadata."""

        return _sha256_json(
            [
                {
                    "from_link_id": movement.from_link_id,
                    "to_link_id": movement.to_link_id,
                    "turn_type": movement.turn_type.value,
                    "base_priority": movement.base_priority,
                    "signal_phase_id": movement.signal_phase_id,
                }
                for movement in self.movements
            ]
        )

    def movement_for_pair(
        self,
        from_link_id: int,
        to_link_id: int,
    ) -> TurnMovement:
        pair = (int(from_link_id), int(to_link_id))
        try:
            return self._movement_by_pair[pair]
        except KeyError as exc:
            raise KeyError(f"no turn authority for link pair {pair}") from exc

    def index_for_pair(self, from_link_id: int, to_link_id: int) -> int:
        pair = (int(from_link_id), int(to_link_id))
        try:
            return self._index_by_pair[pair]
        except KeyError as exc:
            raise KeyError(f"no turn authority for link pair {pair}") from exc


def compile_turn_authority(
    *,
    links: Sequence[_LinkLike],
    road_geometry: RoadGeometryCatalog,
    node_interfaces: NodeInterfaceCatalog,
    through_angle_tolerance_deg: float = 30.0,
) -> TurnAuthorityCatalog:
    """Compile one deterministic authority row for every adjacent link pair.

    Classification uses the final centerline tangent into and out of the
    junction.  A deflection within ``through_angle_tolerance_deg`` is
    ``THROUGH``; positive/counter-clockwise deflection is ``LEFT`` and negative
    deflection is ``RIGHT``.  Transitions into and out of ``RoadClass.RAMP``
    take precedence as ``RAMP_ON`` and ``RAMP_OFF`` respectively.
    """

    tolerance = _validated_tolerance(through_angle_tolerance_deg)
    link_by_id = {int(link.link_id): link for link in links}
    if len(link_by_id) != len(links):
        raise ValueError("links must have unique link_id values")
    if not isinstance(node_interfaces, NodeInterfaceCatalog):
        raise TypeError("node_interfaces must be a NodeInterfaceCatalog")
    if not isinstance(road_geometry, RoadGeometryCatalog):
        raise TypeError("road_geometry must be a RoadGeometryCatalog")

    _validate_interface_alignment(
        link_by_id=link_by_id,
        node_interfaces=node_interfaces,
    )
    for link_id in sorted(link_by_id):
        road_geometry.assignment_for_link(link_id)

    movements: list[TurnMovement] = []
    for interface in node_interfaces.interfaces:
        for from_link_id in interface.incoming_link_ids:
            from_link = link_by_id[from_link_id]
            for to_link_id in interface.outgoing_link_ids:
                to_link = link_by_id[to_link_id]
                movements.append(
                    TurnMovement(
                        from_link_id=from_link_id,
                        to_link_id=to_link_id,
                        turn_type=_classify_turn(
                            from_link=from_link,
                            to_link=to_link,
                            incoming_points=road_geometry.points_for_link(from_link_id),
                            outgoing_points=road_geometry.points_for_link(to_link_id),
                            through_angle_tolerance_deg=tolerance,
                        ),
                    )
                )
    return TurnAuthorityCatalog(tuple(movements))


def _validate_interface_alignment(
    *,
    link_by_id: Mapping[int, _LinkLike],
    node_interfaces: NodeInterfaceCatalog,
) -> None:
    incoming_declarations: dict[int, list[int]] = {
        link_id: [] for link_id in link_by_id
    }
    outgoing_declarations: dict[int, list[int]] = {
        link_id: [] for link_id in link_by_id
    }
    for interface in node_interfaces.interfaces:
        for link_id in interface.incoming_link_ids:
            if link_id not in link_by_id:
                raise ValueError(
                    f"node interface {interface.node_id} references unknown incoming "
                    f"link {link_id}"
                )
            incoming_declarations[link_id].append(interface.node_id)
        for link_id in interface.outgoing_link_ids:
            if link_id not in link_by_id:
                raise ValueError(
                    f"node interface {interface.node_id} references unknown outgoing "
                    f"link {link_id}"
                )
            outgoing_declarations[link_id].append(interface.node_id)

    for link_id, link in sorted(link_by_id.items()):
        expected_incoming = [int(link.dst_node_id)]
        expected_outgoing = [int(link.src_node_id)]
        if incoming_declarations[link_id] != expected_incoming:
            raise ValueError(
                f"incoming interface declarations for link {link_id} are stale or "
                f"incomplete: expected {expected_incoming}, got "
                f"{incoming_declarations[link_id]}"
            )
        if outgoing_declarations[link_id] != expected_outgoing:
            raise ValueError(
                f"outgoing interface declarations for link {link_id} are stale or "
                f"incomplete: expected {expected_outgoing}, got "
                f"{outgoing_declarations[link_id]}"
            )


def _classify_turn(
    *,
    from_link: _LinkLike,
    to_link: _LinkLike,
    incoming_points: tuple[tuple[float, float], ...],
    outgoing_points: tuple[tuple[float, float], ...],
    through_angle_tolerance_deg: float,
) -> TurnType:
    if int(from_link.dst_node_id) != int(to_link.src_node_id):
        raise ValueError(
            "turn authority requires adjacent incoming/outgoing links: "
            f"{int(from_link.link_id)} -> {int(to_link.link_id)}"
        )
    if int(from_link.src_node_id) == int(to_link.dst_node_id):
        return TurnType.U_TURN_FORBIDDEN

    from_class = RoadClass(from_link.road_class)
    to_class = RoadClass(to_link.road_class)
    if from_class is not RoadClass.RAMP and to_class is RoadClass.RAMP:
        return TurnType.RAMP_ON
    if from_class is RoadClass.RAMP and to_class is not RoadClass.RAMP:
        return TurnType.RAMP_OFF

    signed_deflection = _signed_deflection_degrees(
        incoming_points,
        outgoing_points,
    )
    if abs(signed_deflection) <= through_angle_tolerance_deg:
        return TurnType.THROUGH
    if signed_deflection > 0.0:
        return TurnType.LEFT
    return TurnType.RIGHT


def _signed_deflection_degrees(
    incoming_points: tuple[tuple[float, float], ...],
    outgoing_points: tuple[tuple[float, float], ...],
) -> float:
    incoming_x = incoming_points[-1][0] - incoming_points[-2][0]
    incoming_y = incoming_points[-1][1] - incoming_points[-2][1]
    outgoing_x = outgoing_points[1][0] - outgoing_points[0][0]
    outgoing_y = outgoing_points[1][1] - outgoing_points[0][1]
    incoming_norm = math.hypot(incoming_x, incoming_y)
    outgoing_norm = math.hypot(outgoing_x, outgoing_y)
    if incoming_norm <= 0.0 or outgoing_norm <= 0.0:
        raise ValueError("centerline tangent vectors must have positive length")
    cross = incoming_x * outgoing_y - incoming_y * outgoing_x
    dot = incoming_x * outgoing_x + incoming_y * outgoing_y
    return math.degrees(math.atan2(cross, dot))


def _validated_tolerance(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("through_angle_tolerance_deg must be a real number")
    tolerance = float(value)
    if not math.isfinite(tolerance) or tolerance < 0.0 or tolerance >= 90.0:
        raise ValueError("through_angle_tolerance_deg must be in [0, 90)")
    return tolerance


def _sha256_json(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()
