"""Graph topology / CSR primitives and validation for synthetic city networks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Sequence

import numpy as np

__all__ = [
    "NodeKind",
    "RoadClass",
    "TurnType",
    "Node",
    "RoadLink",
    "TurnMovement",
    "BridgeCrossing",
    "TopologyValidationIssue",
    "TopologyValidationReport",
    "RoadNetworkCSR",
    "validate_road_network_topology",
    "build_road_network_csr",
]

Array = np.ndarray


class StrEnum(str, Enum):
    """Local string enum base."""


class NodeKind(StrEnum):
    INTERSECTION = "intersection"
    RAMP_MERGE = "ramp_merge"
    RAMP_SPLIT = "ramp_split"
    INTERCHANGE = "interchange"
    BRIDGE_ENDPOINT = "bridge_endpoint"


class RoadClass(StrEnum):
    LOCAL = "local"
    COLLECTOR = "collector"
    ARTERIAL = "arterial"
    EXPRESSWAY = "expressway"
    RAMP = "ramp"
    BRIDGE = "bridge"


class TurnType(StrEnum):
    LEFT = "left"
    THROUGH = "through"
    RIGHT = "right"
    RAMP_ON = "ramp_on"
    RAMP_OFF = "ramp_off"
    U_TURN_FORBIDDEN = "u_turn_forbidden"


@dataclass(slots=True)
class Node:
    node_id: int
    kind: NodeKind = NodeKind.INTERSECTION
    x: float = 0.0
    y: float = 0.0
    zone_id: int | None = None
    signal_group_id: int | None = None

    def __post_init__(self) -> None:
        self.node_id = int(self.node_id)
        self.kind = NodeKind(self.kind)
        self.x = float(self.x)
        self.y = float(self.y)
        self.zone_id = None if self.zone_id is None else int(self.zone_id)
        self.signal_group_id = (
            None if self.signal_group_id is None else int(self.signal_group_id)
        )


@dataclass(slots=True)
class RoadLink:
    link_id: int
    src_node_id: int
    dst_node_id: int
    road_class: RoadClass
    length_m: float
    free_flow_speed_mps: float
    capacity_veh_per_tick: float
    lanes: int = 1
    bridge_group_id: int | None = None
    is_blockable: bool = True

    def __post_init__(self) -> None:
        self.link_id = int(self.link_id)
        self.src_node_id = int(self.src_node_id)
        self.dst_node_id = int(self.dst_node_id)
        self.road_class = RoadClass(self.road_class)
        self.length_m = float(self.length_m)
        self.free_flow_speed_mps = float(self.free_flow_speed_mps)
        self.capacity_veh_per_tick = float(self.capacity_veh_per_tick)
        self.lanes = int(self.lanes)
        self.bridge_group_id = (
            None if self.bridge_group_id is None else int(self.bridge_group_id)
        )
        self.is_blockable = bool(self.is_blockable)

        if self.src_node_id == self.dst_node_id:
            raise ValueError("RoadLink src_node_id and dst_node_id must differ")
        if self.length_m <= 0:
            raise ValueError("RoadLink length_m must be > 0")
        if self.free_flow_speed_mps <= 0:
            raise ValueError("RoadLink free_flow_speed_mps must be > 0")
        if self.capacity_veh_per_tick < 0:
            raise ValueError("RoadLink capacity_veh_per_tick must be >= 0")
        if self.lanes < 1:
            raise ValueError("RoadLink lanes must be >= 1")
        if self.road_class == RoadClass.BRIDGE and self.bridge_group_id is None:
            raise ValueError("RoadLink bridge_group_id is required for bridge links")


@dataclass(slots=True)
class TurnMovement:
    from_link_id: int
    to_link_id: int
    turn_type: TurnType
    base_priority: float = 1.0
    signal_phase_id: int | None = None

    def __post_init__(self) -> None:
        self.from_link_id = int(self.from_link_id)
        self.to_link_id = int(self.to_link_id)
        self.turn_type = TurnType(self.turn_type)
        self.base_priority = float(self.base_priority)
        self.signal_phase_id = (
            None if self.signal_phase_id is None else int(self.signal_phase_id)
        )
        if self.base_priority < 0:
            raise ValueError("TurnMovement base_priority must be >= 0")


@dataclass(slots=True)
class BridgeCrossing:
    bridge_group_id: int
    link_ids: tuple[int, ...]
    barrier_id: int
    crossing_name: str
    bottleneck_rank_hint: int | None = None

    def __post_init__(self) -> None:
        self.bridge_group_id = int(self.bridge_group_id)
        self.link_ids = tuple(int(link_id) for link_id in self.link_ids)
        self.barrier_id = int(self.barrier_id)
        self.crossing_name = str(self.crossing_name)
        self.bottleneck_rank_hint = (
            None if self.bottleneck_rank_hint is None else int(self.bottleneck_rank_hint)
        )
        if not self.link_ids:
            raise ValueError("BridgeCrossing link_ids must not be empty")


@dataclass(slots=True)
class TopologyValidationIssue:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.code = str(self.code)
        self.message = str(self.message)
        if not isinstance(self.details, dict):
            self.details = dict(self.details)


@dataclass(slots=True)
class TopologyValidationReport:
    issues: tuple[TopologyValidationIssue, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.issues

    def summary(self) -> str:
        if self.ok:
            return "ok"
        return "; ".join(f"{issue.code}: {issue.message}" for issue in self.issues)


@dataclass(slots=True)
class RoadNetworkCSR:
    """Static road network topology with CSR adjacency and turn arrays."""

    nodes: tuple[Node, ...]
    links: tuple[RoadLink, ...]
    turns: tuple[TurnMovement, ...]
    bridge_crossings: tuple[BridgeCrossing, ...] = field(default_factory=tuple)

    node_id_to_index: dict[int, int] = field(default_factory=dict)
    link_id_to_index: dict[int, int] = field(default_factory=dict)

    node_ids: Array | None = None
    link_ids: Array | None = None
    link_src_node_index: Array | None = None
    link_dst_node_index: Array | None = None
    outgoing_indptr: Array | None = None
    outgoing_link_indices: Array | None = None
    incoming_indptr: Array | None = None
    incoming_link_indices: Array | None = None
    turn_from_link_index: Array | None = None
    turn_to_link_index: Array | None = None
    turn_base_priority: Array | None = None
    turn_is_forbidden: Array | None = None

    def __post_init__(self) -> None:
        self.nodes = tuple(self.nodes)
        self.links = tuple(self.links)
        self.turns = tuple(self.turns)
        self.bridge_crossings = tuple(self.bridge_crossings)
        self.node_id_to_index = (
            dict(self.node_id_to_index)
            if self.node_id_to_index
            else {node.node_id: idx for idx, node in enumerate(self.nodes)}
        )
        self.link_id_to_index = (
            dict(self.link_id_to_index)
            if self.link_id_to_index
            else {link.link_id: idx for idx, link in enumerate(self.links)}
        )

        self.node_ids = _as_array(self.node_ids, [node.node_id for node in self.nodes], np.int32)
        self.link_ids = _as_array(self.link_ids, [link.link_id for link in self.links], np.int32)
        self.link_src_node_index = _as_array(
            self.link_src_node_index,
            [self.node_id_to_index[link.src_node_id] for link in self.links],
            np.int32,
        )
        self.link_dst_node_index = _as_array(
            self.link_dst_node_index,
            [self.node_id_to_index[link.dst_node_id] for link in self.links],
            np.int32,
        )

        out_indptr, out_indices = _build_link_csr(
            node_count=len(self.nodes),
            node_indices=list(np.asarray(self.link_src_node_index).tolist()),
        )
        in_indptr, in_indices = _build_link_csr(
            node_count=len(self.nodes),
            node_indices=list(np.asarray(self.link_dst_node_index).tolist()),
        )
        self.outgoing_indptr = _as_array(self.outgoing_indptr, out_indptr, np.int32)
        self.outgoing_link_indices = _as_array(self.outgoing_link_indices, out_indices, np.int32)
        self.incoming_indptr = _as_array(self.incoming_indptr, in_indptr, np.int32)
        self.incoming_link_indices = _as_array(self.incoming_link_indices, in_indices, np.int32)

        self.turn_from_link_index = _as_array(
            self.turn_from_link_index,
            [self.link_id_to_index[t.from_link_id] for t in self.turns],
            np.int32,
        )
        self.turn_to_link_index = _as_array(
            self.turn_to_link_index,
            [self.link_id_to_index[t.to_link_id] for t in self.turns],
            np.int32,
        )
        self.turn_base_priority = _as_array(
            self.turn_base_priority,
            [t.base_priority for t in self.turns],
            np.float32,
        )
        self.turn_is_forbidden = _as_array(
            self.turn_is_forbidden,
            [t.turn_type == TurnType.U_TURN_FORBIDDEN for t in self.turns],
            np.bool_,
        )

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def link_count(self) -> int:
        return len(self.links)

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    def outgoing_links_for_node(self, node_id: int) -> tuple[RoadLink, ...]:
        node_index = self.node_id_to_index[int(node_id)]
        start = int(self.outgoing_indptr[node_index])
        end = int(self.outgoing_indptr[node_index + 1])
        indices = [int(x) for x in np.asarray(self.outgoing_link_indices[start:end]).tolist()]
        return tuple(self.links[i] for i in indices)


def validate_road_network_topology(
    nodes: Sequence[Node],
    links: Sequence[RoadLink],
    turns: Sequence[TurnMovement] = (),
    bridge_crossings: Sequence[BridgeCrossing] = (),
    *,
    require_weak_connectivity: bool = False,
) -> TopologyValidationReport:
    """Validate static topology entity references and graph consistency rules."""

    issues: list[TopologyValidationIssue] = []
    node_ids = [node.node_id for node in nodes]
    link_ids = [link.link_id for link in links]

    if len(set(node_ids)) != len(node_ids):
        issues.append(
            TopologyValidationIssue(
                code="duplicate_node_ids",
                message="Node ids must be unique",
            )
        )
    if len(set(link_ids)) != len(link_ids):
        issues.append(
            TopologyValidationIssue(
                code="duplicate_link_ids",
                message="Link ids must be unique",
            )
        )

    node_id_set = set(node_ids)
    link_by_id = {link.link_id: link for link in links}

    for link in links:
        if link.src_node_id not in node_id_set or link.dst_node_id not in node_id_set:
            issues.append(
                TopologyValidationIssue(
                    code="link_node_ref_missing",
                    message="RoadLink references missing node ids",
                    details={
                        "link_id": link.link_id,
                        "src_node_id": link.src_node_id,
                        "dst_node_id": link.dst_node_id,
                    },
                )
            )
        if link.road_class == RoadClass.BRIDGE and link.bridge_group_id is None:
            issues.append(
                TopologyValidationIssue(
                    code="bridge_group_missing",
                    message="Bridge link requires bridge_group_id",
                    details={"link_id": link.link_id},
                )
            )

    for turn in turns:
        from_link = link_by_id.get(turn.from_link_id)
        to_link = link_by_id.get(turn.to_link_id)
        if from_link is None or to_link is None:
            issues.append(
                TopologyValidationIssue(
                    code="turn_link_ref_missing",
                    message="TurnMovement references missing link ids",
                    details={
                        "from_link_id": turn.from_link_id,
                        "to_link_id": turn.to_link_id,
                    },
                )
            )
            continue
        if from_link.dst_node_id != to_link.src_node_id:
            issues.append(
                TopologyValidationIssue(
                    code="turn_links_not_adjacent",
                    message="TurnMovement links must share a junction node",
                    details={
                        "from_link_id": turn.from_link_id,
                        "to_link_id": turn.to_link_id,
                        "from_link_dst_node_id": from_link.dst_node_id,
                        "to_link_src_node_id": to_link.src_node_id,
                    },
                )
            )

    for crossing in bridge_crossings:
        missing = [link_id for link_id in crossing.link_ids if link_id not in link_by_id]
        if missing:
            issues.append(
                TopologyValidationIssue(
                    code="bridge_crossing_link_ref_missing",
                    message="BridgeCrossing references missing link ids",
                    details={
                        "bridge_group_id": crossing.bridge_group_id,
                        "missing_link_ids": tuple(missing),
                    },
                )
            )
            continue
        mismatched = [
            link_id
            for link_id in crossing.link_ids
            if link_by_id[link_id].bridge_group_id != crossing.bridge_group_id
        ]
        if mismatched:
            issues.append(
                TopologyValidationIssue(
                    code="bridge_crossing_group_mismatch",
                    message="BridgeCrossing link_ids must match bridge_group_id",
                    details={
                        "bridge_group_id": crossing.bridge_group_id,
                        "mismatched_link_ids": tuple(mismatched),
                    },
                )
            )

    if require_weak_connectivity and not issues:
        from metroflow.city.connectivity import analyze_weak_connectivity

        report = analyze_weak_connectivity(nodes=nodes, links=links)
        if report.component_count > 1:
            issues.append(
                TopologyValidationIssue(
                    code="weak_connectivity_missing",
                    message="Road network must be weakly connected",
                    details={
                        "component_count": report.component_count,
                        "component_sizes": report.component_sizes,
                    },
                )
            )

    return TopologyValidationReport(issues=tuple(issues))


def build_road_network_csr(
    nodes: Sequence[Node],
    links: Sequence[RoadLink],
    turns: Sequence[TurnMovement] = (),
    bridge_crossings: Sequence[BridgeCrossing] = (),
    *,
    validate: bool = True,
    require_weak_connectivity: bool = False,
) -> RoadNetworkCSR:
    """Build a CSR-backed static road network graph."""

    nodes_t = tuple(nodes)
    links_t = tuple(links)
    turns_t = tuple(turns)
    bridges_t = tuple(bridge_crossings)

    if validate:
        report = validate_road_network_topology(
            nodes_t,
            links_t,
            turns_t,
            bridges_t,
            require_weak_connectivity=require_weak_connectivity,
        )
        if not report.ok:
            raise ValueError(f"Invalid road network topology: {report.summary()}")

    return RoadNetworkCSR(
        nodes=nodes_t,
        links=links_t,
        turns=turns_t,
        bridge_crossings=bridges_t,
    )


def _build_link_csr(node_count: int, node_indices: list[int]) -> tuple[list[int], list[int]]:
    counts = [0] * node_count
    for node_index in node_indices:
        counts[int(node_index)] += 1

    indptr = [0] * (node_count + 1)
    for i in range(node_count):
        indptr[i + 1] = indptr[i] + counts[i]

    write_ptr = indptr[:-1].copy()
    indices = [0] * len(node_indices)
    for link_index, node_index in enumerate(node_indices):
        pos = write_ptr[node_index]
        indices[pos] = link_index
        write_ptr[node_index] += 1
    return indptr, indices


def _as_array(value: Array | None, fallback: Iterable[Any], dtype: Any) -> Array:
    if value is None:
        return np.asarray(list(fallback), dtype=dtype)
    return np.asarray(value, dtype=dtype)
