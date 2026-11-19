"""Physical turning-pocket geometry compiler for opt-in KCMB route-FIFO.

This module constructs a different, spatially resolved *physical model*.
It does not infer lane geometry from route names, create empirical data or
migrate an old snapshot's unknown individual vehicle positions.

A single physical upstream lane ends at an explicit pocket-entry node.
Each pocket is a real finite-length link with its own lanes/capacity/storage,
so signal blocking in one pocket cannot automatically stop a different one.
Before entering a pocket, vehicles remain in the shared upstream FIFO lane.

See docs/research/KCMB_TURN_POCKET_THEORY_R1_R10_20261119_KO.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
import math

from .kcmb_network import KCMBLink, KCMBRoute, KCMBNetworkConfig


SCHEMA_VERSION = "kcmb_physical_turn_pocket_v1"


@dataclass(frozen=True, slots=True)
class PocketGroup:
    """Declared physical lane group, possibly shared by multiple turning routes.

    Lane counts and physical saturation capacity are *inputs* and never
    inferred from turn destinations or OSM names.
    """
    name: str
    routes: tuple[str, ...]
    lanes: int
    capacity_veh_per_s: float


@dataclass(frozen=True, slots=True)
class TurnPocketLayout:
    """A single shared upstream road and its finite dedicated pocket region."""
    approach: str
    pocket_length_m: float
    groups: tuple[PocketGroup, ...]


@dataclass(frozen=True, slots=True)
class PocketGeometryLedger:
    approach: str
    original_length_m: float
    shared_length_m: float
    pocket_length_m: float
    upstream_lanes: int
    pocket_region_lanes: int
    original_lane_metres: float
    compiled_lane_metres: float
    added_lane_metres: float
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class CompiledPocketNetwork:
    config: KCMBNetworkConfig
    geometry: PocketGeometryLedger
    pocket_link_by_group: tuple[tuple[str, str], ...]


def compile_turn_pockets(config: KCMBNetworkConfig,
                         layout: TurnPocketLayout) -> CompiledPocketNetwork:
    """Construct a new topology, returning an independent immutable config.

    The old KCMBNetworkConfig and source bytes are not mutated. All route
    identities and kinetic laws are preserved, but geometry and time-discrete
    minimum travel time may legitimately differ.
    """
    if not isinstance(config, KCMBNetworkConfig) or not isinstance(layout, TurnPocketLayout):
        raise ValueError("explicit original KCMB config and pocket layout required")
    if config.lane_policy!="shared_head":
        raise ValueError("physical pocket expansion requires shared_head FIFO upstream")
    names={l.name for l in config.links}
    if not isinstance(layout.approach,str) or layout.approach not in names:
        raise ValueError("unknown approach link for pocket geometry")
    links={l.name:l for l in config.links}
    approach=links[layout.approach]
    if approach.lanes != 1:
        # This research solver uses a *single ordered head queue* on upstream
        # approach, so treating two independent upstream lanes as that queue
        # could overblock physically possible overtaking.
        raise ValueError("strict shared upstream FIFO requires one-lane approach")
    if (isinstance(layout.pocket_length_m,bool) or
        not isinstance(layout.pocket_length_m,(float,int)) or
        not math.isfinite(layout.pocket_length_m) or
        not 0 < layout.pocket_length_m < approach.length_m):
        raise ValueError("pocket length must be finite and inside approach road")

    if not isinstance(layout.groups,tuple) or not layout.groups:
        raise ValueError("nonempty immutable physical pocket groups required")

    consumed={r.name for r in config.routes if approach.name in r.path}
    if not consumed:
        raise ValueError("approach not used by any immutable route")
    all_route_names={r.name for r in config.routes}
    groups_seen=set()
    route_to_group={}
    group_links=[]
    virtual_node=f"{approach.name}::kcmb_pocket_entry"
    original_nodes={node for link in config.links for node in (link.tail,link.head)}
    if virtual_node in original_nodes:
        raise ValueError("pocket-entry physical node name collision")

    pocket_lanes=0
    pocket_len=float(layout.pocket_length_m)
    shared_len=approach.length_m-pocket_len
    new_link_names=set(names)
    for g in layout.groups:
        if not isinstance(g,PocketGroup):
            raise ValueError("PocketGroup required for physical lane partition")
        if not isinstance(g.name,str) or not g.name or g.name in groups_seen:
            raise ValueError("unique nonempty pocket group name required")
        groups_seen.add(g.name)
        if (not isinstance(g.routes,tuple) or not g.routes or
            any(not isinstance(x,str) or not x for x in g.routes) or
            len(set(g.routes))!=len(g.routes)):
            raise ValueError("unique, nonempty route assignments required")
        if isinstance(g.lanes,bool) or not isinstance(g.lanes,int) or g.lanes<=0:
            raise ValueError("pocket group lanes must be positive integer")
        if (isinstance(g.capacity_veh_per_s,bool) or
            not isinstance(g.capacity_veh_per_s,(float,int)) or
            not math.isfinite(g.capacity_veh_per_s) or g.capacity_veh_per_s<=0):
            raise ValueError("pocket group capacity must be finite and positive")
        pocket_lanes+=g.lanes
        for route in g.routes:
            if route not in consumed or route not in all_route_names or route in route_to_group:
                raise ValueError("unknown, duplicated or unassigned approach route")
            route_to_group[route]=g.name
        link_id=f"{approach.name}::kcmb_pocket::{g.name}"
        if link_id in new_link_names:
            raise ValueError("pocket link name collision")
        new_link_names.add(link_id)
        group_links.append((g.name, KCMBLink(
            link_id,virtual_node,approach.head,pocket_len,
            g.lanes,float(g.capacity_veh_per_s),
            approach.backward_wave_mps,approach.priority,
        )))
    if consumed!=set(route_to_group):
        missing=sorted(consumed-set(route_to_group))
        raise ValueError(f"missing pocket route assignments: {missing}")

    shared=KCMBLink(approach.name,approach.tail,virtual_node,
                    shared_len,approach.lanes,approach.capacity_veh_per_s,
                    approach.backward_wave_mps,approach.priority)
    expanded_links=tuple(shared if l.name==approach.name else l
                          for l in config.links) + tuple(link for _,link in group_links)

    lookup={name:link.name for name,link in group_links}
    expanded_routes=[]
    for r in config.routes:
        if r.name not in route_to_group:
            expanded_routes.append(r)
            continue
        path=[]
        for name in r.path:
            path.append(name)
            if name==approach.name:
                path.append(lookup[route_to_group[r.name]])
        expanded_routes.append(KCMBRoute(r.name,r.vehicle,tuple(path)))

    # KCMBNetworkConfig performs downstream continuity and CFL checks; do not
    # silently shrink dt, invent additional cohorts, or change class laws.
    upgraded=KCMBNetworkConfig(expanded_links,tuple(expanded_routes),
                               config.dt_s,config.lane_policy)
    original_lm=approach.lanes*approach.length_m
    expanded_lm=approach.lanes*shared_len+pocket_lanes*pocket_len
    geom=PocketGeometryLedger(
        approach.name,approach.length_m,shared_len,pocket_len,
        approach.lanes,pocket_lanes,original_lm,expanded_lm,
        expanded_lm-original_lm,
    )
    return CompiledPocketNetwork(
        upgraded,geom,tuple((name,link.name) for name,link in group_links))
