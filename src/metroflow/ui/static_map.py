"""Static generated-city map review artifact rendering."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from html import escape
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from metroflow.city.connectivity import analyze_weak_connectivity
from metroflow.flow.state import LinkState
from metroflow.map.lane_grammar import RoadUnitKind
from metroflow.map.road_geometry import (
    RoadGeometryCatalog,
    build_endpoint_geometry_catalog,
)
from metroflow.map.section_compiler import RoadSectionCatalog, compile_road_sections
from metroflow.sim.state import SimulationState

__all__ = [
    "StaticCityMapArtifact",
    "build_static_city_map_artifact",
    "render_static_city_map_html",
    "write_static_city_map_html",
]


@dataclass(slots=True)
class StaticCityMapArtifact:
    """JSON-safe static city map payload plus HTML renderer."""

    scenario_id: str
    geometry_version: str
    bounds: dict[str, float]
    nodes: tuple[dict[str, Any], ...]
    links: tuple[dict[str, Any], ...]
    zones: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    pois: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    bridges: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    label: str = "SMOKE REVIEW ARTIFACT"
    roads: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    visible_layers: tuple[str, ...] = ("roads", "zones", "pois")

    def __post_init__(self) -> None:
        self.scenario_id = str(self.scenario_id)
        self.geometry_version = str(self.geometry_version)
        self.bounds = {str(key): float(value) for key, value in dict(self.bounds).items()}
        self.nodes = tuple(dict(item) for item in self.nodes)
        self.links = tuple(dict(item) for item in self.links)
        roads = tuple(dict(item) for item in self.roads)
        self.roads = roads or _legacy_roads_from_links(
            links=self.links,
            bounds=self.bounds,
        )
        self.zones = tuple(dict(item) for item in self.zones)
        self.pois = tuple(dict(item) for item in self.pois)
        self.bridges = tuple(dict(item) for item in self.bridges)
        self.metadata = dict(self.metadata)
        self.visible_layers = _normalize_visible_layers(self.visible_layers)
        self.label = str(self.label)

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def link_count(self) -> int:
        return len(self.links)

    @property
    def road_count(self) -> int:
        return len(self.roads)

    @property
    def zone_count(self) -> int:
        return len(self.zones)

    @property
    def poi_count(self) -> int:
        return len(self.pois)

    def to_dict(self) -> dict[str, Any]:
        """Serialize this artifact to a stable JSON-safe dictionary."""

        road_class_counts = Counter(str(link.get("road_class", "")) for link in self.links)
        physical_road_class_counts = Counter(
            str(road.get("road_class", "")) for road in self.roads
        )
        zone_type_counts = Counter(str(zone.get("zone_type", "")) for zone in self.zones)
        poi_type_counts = Counter(str(poi.get("poi_type", "")) for poi in self.pois)
        return {
            "scenario_id": self.scenario_id,
            "geometry_version": self.geometry_version,
            "label": self.label,
            "node_count": self.node_count,
            "link_count": self.link_count,
            "road_count": self.road_count,
            "zone_count": self.zone_count,
            "poi_count": self.poi_count,
            "bounds": dict(self.bounds),
            "road_class_counts": dict(sorted(road_class_counts.items())),
            "physical_road_class_counts": dict(
                sorted(physical_road_class_counts.items())
            ),
            "zone_type_counts": dict(sorted(zone_type_counts.items())),
            "poi_type_counts": dict(sorted(poi_type_counts.items())),
            "nodes": tuple(dict(item) for item in self.nodes),
            "links": tuple(dict(item) for item in self.links),
            "roads": tuple(dict(item) for item in self.roads),
            "zones": tuple(dict(item) for item in self.zones),
            "pois": tuple(dict(item) for item in self.pois),
            "bridges": tuple(dict(item) for item in self.bridges),
            "metadata": dict(self.metadata),
            "visible_layers": self.visible_layers,
        }

    def to_json(self) -> str:
        """Serialize the artifact as stable compact JSON."""

        return json.dumps(self.to_dict(), separators=(",", ":"), sort_keys=True)

    def to_html(self) -> str:
        """Render a standalone static HTML/SVG review surface."""

        return render_static_city_map_html(self)


def build_static_city_map_artifact(
    state: SimulationState,
    *,
    focus_largest_component: bool = False,
    visible_layers: tuple[str, ...] = ("roads", "zones", "pois"),
) -> StaticCityMapArtifact:
    """Build a static map artifact from a generated `SimulationState`."""

    city = state.static.city_topology
    if city is None:
        raise ValueError("state.static.city_topology is required for static city map rendering")
    nodes_raw = tuple(getattr(city, "nodes", ()) or ())
    links_raw = tuple(getattr(city, "links", ()) or ())
    if not nodes_raw or not links_raw:
        raise ValueError("city_topology must contain non-empty nodes and links")
    resolved_layers = _normalize_visible_layers(visible_layers)

    component_report = analyze_weak_connectivity(nodes=nodes_raw, links=links_raw)
    bounds_nodes = _bounds_nodes(
        nodes_raw,
        component_report=component_report,
        focus_largest_component=focus_largest_component,
    )
    node_xy = {
        int(node.node_id): (float(node.x), float(node.y))
        for node in nodes_raw
    }
    for link in links_raw:
        _node_xy_for_link(link, node_xy)
    road_geometry = _resolve_road_geometry(
        city=city,
        nodes=nodes_raw,
        links=links_raw,
    )
    focused_geometry_ids = _focused_geometry_ids(
        links=links_raw,
        road_geometry=road_geometry,
        component_report=component_report,
        focus_largest_component=focus_largest_component,
    )
    bounds = _geometry_bounds(
        bounds_nodes,
        road_geometry=road_geometry,
        geometry_ids=focused_geometry_ids,
    )
    repair_link_ids = {
        int(link_id)
        for link_id in tuple((getattr(city, "metadata", {}) or {}).get("connectivity_repair_link_ids", ()))
    }
    bridge_by_link_id = _bridge_metadata_by_link_id(city)
    flow_link_state = state.dynamic.flow_link_state
    link_state = flow_link_state if isinstance(flow_link_state, LinkState) else None
    nodes = tuple(
        _node_payload(
            node,
            bounds=bounds,
            component_id=component_report.node_component_id_by_node_id.get(int(node.node_id), -1),
        )
        for node in nodes_raw
    )
    links = tuple(
        _link_payload(
            link,
            idx=idx,
            node_xy=node_xy,
            bounds=bounds,
            link_state=link_state,
            component_id=component_report.node_component_id_by_node_id.get(
                int(link.src_node_id),
                -1,
            ),
            connectivity_repair=int(link.link_id) in repair_link_ids,
            bridge_metadata=bridge_by_link_id.get(int(link.link_id)),
        )
        for idx, link in enumerate(links_raw)
    )
    road_sections = _resolve_road_sections(
        city=city,
        links=links_raw,
        road_geometry=road_geometry,
    )
    roads = _physical_road_payloads(
        links_raw=links_raw,
        link_payloads=links,
        road_geometry=road_geometry,
        road_sections=road_sections,
        bounds=bounds,
    )
    zones = tuple(_zone_payload(zone, bounds=bounds) for zone in tuple(state.static.zones or ()))
    pois = tuple(_poi_payload(poi, node_xy=node_xy, bounds=bounds) for poi in tuple(state.static.pois or ()))
    bridges = tuple(_bridge_payload(crossing) for crossing in tuple(getattr(city, "bridge_crossings", ()) or ()))

    return StaticCityMapArtifact(
        scenario_id=str(state.static.scenario_id or "unknown"),
        geometry_version=str(state.static.ui_network_geometry_version or "unknown"),
        bounds=dict(bounds),
        nodes=nodes,
        links=links,
        roads=roads,
        zones=zones,
        pois=pois,
        bridges=bridges,
        metadata=_artifact_metadata(
            state=state,
            city=city,
            component_report=component_report,
            map_focus="largest_component" if focus_largest_component else "full_extent",
            road_geometry=road_geometry,
            road_sections=road_sections,
        ),
        visible_layers=resolved_layers,
    )


def render_static_city_map_html(artifact: StaticCityMapArtifact) -> str:
    """Render a static, dependency-free city map HTML artifact."""

    payload_json = escape(artifact.to_json())
    svg = _render_map_svg(artifact)
    road_rows = _render_count_rows(
        artifact.to_dict()["physical_road_class_counts"]
    )
    zone_rows = _render_count_rows(artifact.to_dict()["zone_type_counts"])
    visible_layers = ",".join(artifact.visible_layers)
    layer_controls = "".join(
        _render_layer_control(layer, layer in artifact.visible_layers)
        for layer in ("roads", "zones", "pois")
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Metroflow Static City Map</title>
  <style>
    :root {{ color-scheme: light; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    body {{ margin: 0; background: #f4f6f8; color: #17202a; }}
    main {{ max-width: 1220px; margin: 0 auto; padding: 24px; }}
    h1 {{ margin: 0 0 6px; font-size: 25px; letter-spacing: 0; }}
    h2 {{ margin: 24px 0 8px; font-size: 16px; letter-spacing: 0; }}
    .meta {{ color: #5b6674; margin-bottom: 16px; }}
    .map-frame {{ border: 1px solid #ccd3dc; background: #ffffff; border-radius: 8px; overflow: auto; }}
    .metric-row {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; margin: 14px 0; }}
    .metric {{ background: #ffffff; border: 1px solid #d5dbe3; border-radius: 8px; padding: 11px; }}
    .metric strong {{ display: block; margin-top: 3px; font-size: 21px; }}
    .layer-controls {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 10px; }}
    .layer-controls button {{ border: 1px solid #aeb8c4; background: #ffffff; color: #263442; padding: 6px 10px; border-radius: 6px; cursor: pointer; }}
    .layer-controls button[aria-pressed="true"] {{ background: #263442; color: #ffffff; border-color: #263442; }}
    table {{ border-collapse: collapse; width: 100%; background: #ffffff; border: 1px solid #d5dbe3; }}
    td, th {{ border-bottom: 1px solid #e4e8ed; padding: 8px 10px; text-align: left; font-size: 13px; }}
    th {{ background: #ecf0f4; font-weight: 650; }}
    .road-shoulder {{ fill: none; stroke: #727b84; stroke-linecap: round; stroke-linejoin: round; opacity: 0.58; }}
    .road-ribbon {{ fill: none; stroke-linecap: round; stroke-linejoin: round; }}
    .road-ribbon.local {{ stroke: #b7bec6; }}
    .road-ribbon.collector {{ stroke: #5f9b84; }}
    .road-ribbon.arterial {{ stroke: #d99b49; }}
    .road-ribbon.expressway {{ stroke: #4778b5; }}
    .road-ribbon.ramp {{ stroke: #8671b1; }}
    .road-ribbon.bridge {{ stroke: #3b8791; }}
    .road-ribbon.unknown {{ stroke: #838b94; }}
    .road-median {{ fill: none; stroke: #f5f5f2; stroke-linecap: round; stroke-linejoin: round; opacity: 0.9; }}
    .road-repair {{ fill: none; stroke: #b85f4c; stroke-width: 1.8; stroke-dasharray: 7 4; opacity: 0.96; }}
    .zone-layer circle {{ fill-opacity: 0.12; stroke-width: 1.1; }}
    .poi-layer circle {{ stroke: #ffffff; stroke-width: 0.8; opacity: 0.72; }}
    .bridge-label text {{ font-size: 10px; fill: #1f4f59; paint-order: stroke; stroke: #ffffff; stroke-width: 3px; }}
    .legend text {{ font-size: 11px; fill: #354050; }}
    .note {{ color: #5b6674; font-size: 13px; line-height: 1.45; }}
  </style>
</head>
<body>
<main class="metroflow-static-city-map" data-static-city-map="{payload_json}" data-visible-layers="{escape(visible_layers)}">
  <h1>Metroflow Static City Map</h1>
  <div class="meta">{escape(artifact.label)} &middot; scenario <code>{escape(artifact.scenario_id)}</code> &middot; geometry <code>{escape(artifact.geometry_version)}</code></div>
  <section class="metric-row">
    <div class="metric">nodes<strong>{artifact.node_count}</strong></div>
    <div class="metric">physical roads<strong>{artifact.road_count}</strong></div>
    <div class="metric">links<strong>{artifact.link_count}</strong></div>
    <div class="metric">zones<strong>{artifact.zone_count}</strong></div>
    <div class="metric">POIs<strong>{artifact.poi_count}</strong></div>
  </section>
  <div class="layer-controls" role="group" aria-label="map layers">{layer_controls}</div>
  <section class="map-frame">{svg}</section>
  <h2>Physical Road Class Counts</h2>
  <table><thead><tr><th>road class</th><th>count</th></tr></thead><tbody>{road_rows}</tbody></table>
  <h2>Zone Type Counts</h2>
  <table><thead><tr><th>zone type</th><th>count</th></tr></thead><tbody>{zone_rows}</tbody></table>
  <p class="note">This static map is a smoke review artifact for generated-city structure and runtime overlay inspection. It is not a validation claim.</p>
</main>
<script>
  document.querySelectorAll("[data-layer-toggle]").forEach((button) => {{
    button.addEventListener("click", () => {{
      const layer = button.dataset.layerToggle;
      const group = document.querySelector(`.${{layer.slice(0, -1)}}-layer`);
      if (!group) return;
      const next = button.getAttribute("aria-pressed") !== "true";
      button.setAttribute("aria-pressed", String(next));
      group.hidden = !next;
    }});
  }});
</script>
</body>
</html>
"""


def write_static_city_map_html(
    artifact: StaticCityMapArtifact,
    output_path: str | Path,
) -> Path:
    """Write a static city map HTML artifact."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(artifact.to_html(), encoding="utf-8")
    return path


def _geometry_bounds(
    nodes: tuple[Any, ...],
    *,
    road_geometry: RoadGeometryCatalog,
    geometry_ids: frozenset[int] | None = None,
) -> dict[str, float]:
    geometry_points = tuple(
        point
        for centerline in road_geometry.centerlines
        if geometry_ids is None or centerline.geometry_id in geometry_ids
        for point in centerline.points_m
    )
    xs = np.asarray(
        [float(node.x) for node in nodes]
        + [float(point[0]) for point in geometry_points],
        dtype=np.float64,
    )
    ys = np.asarray(
        [float(node.y) for node in nodes]
        + [float(point[1]) for point in geometry_points],
        dtype=np.float64,
    )
    min_x = float(np.min(xs))
    max_x = float(np.max(xs))
    min_y = float(np.min(ys))
    max_y = float(np.max(ys))
    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)
    pad_x = width * 0.04
    pad_y = height * 0.04
    padded_min_x = min_x - pad_x
    padded_max_x = max_x + pad_x
    padded_min_y = min_y - pad_y
    padded_max_y = max_y + pad_y
    padded_width = padded_max_x - padded_min_x
    padded_height = padded_max_y - padded_min_y
    scale = min(1000.0 / padded_width, 680.0 / padded_height)
    rendered_width = padded_width * scale
    rendered_height = padded_height * scale
    return {
        "min_x": padded_min_x,
        "max_x": padded_max_x,
        "min_y": padded_min_y,
        "max_y": padded_max_y,
        "width": padded_width,
        "height": padded_height,
        "scale_px_per_m": scale,
        "offset_x_px": 40.0 + ((1000.0 - rendered_width) * 0.5),
        "offset_y_px": 40.0 + ((680.0 - rendered_height) * 0.5),
    }


def _focused_geometry_ids(
    *,
    links: tuple[Any, ...],
    road_geometry: RoadGeometryCatalog,
    component_report: Any,
    focus_largest_component: bool,
) -> frozenset[int] | None:
    if not focus_largest_component or not component_report.component_node_ids:
        return None
    largest_node_ids = set(component_report.component_node_ids[0])
    largest_link_ids = {
        int(link.link_id)
        for link in links
        if int(link.src_node_id) in largest_node_ids
        and int(link.dst_node_id) in largest_node_ids
    }
    return frozenset(
        assignment.geometry_id
        for assignment in road_geometry.assignments
        if assignment.link_id in largest_link_ids
    )


def _bounds_nodes(
    nodes: tuple[Any, ...],
    *,
    component_report: Any,
    focus_largest_component: bool,
) -> tuple[Any, ...]:
    if not focus_largest_component or not component_report.component_node_ids:
        return nodes
    largest_ids = set(component_report.component_node_ids[0])
    return tuple(node for node in nodes if int(node.node_id) in largest_ids) or nodes


def _node_payload(
    node: Any,
    *,
    bounds: Mapping[str, float],
    component_id: int,
) -> dict[str, Any]:
    return {
        "node_id": int(node.node_id),
        "x": float(node.x),
        "y": float(node.y),
        "sx": _scale_x(float(node.x), bounds),
        "sy": _scale_y(float(node.y), bounds),
        "kind": str(getattr(getattr(node, "kind", ""), "value", getattr(node, "kind", ""))),
        "component_id": int(component_id),
    }


def _link_payload(
    link: Any,
    *,
    idx: int,
    node_xy: Mapping[int, tuple[float, float]],
    bounds: Mapping[str, float],
    link_state: LinkState | None,
    component_id: int,
    connectivity_repair: bool,
    bridge_metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    src_xy, dst_xy = _node_xy_for_link(link, node_xy)
    queue = _array_value(link_state.queue_vehicles, idx, 0.0) if link_state is not None else 0.0
    cap = (
        _array_value(link_state.effective_capacity_vehicles, idx, float(link.capacity_veh_per_tick))
        if link_state is not None
        else float(link.capacity_veh_per_tick)
    )
    cost = _array_value(link_state.travel_time_cost, idx, 0.0) if link_state is not None else 0.0
    congestion = float(queue / max(cap, 1e-6))
    return {
        "link_id": int(link.link_id),
        "src_node_id": int(link.src_node_id),
        "dst_node_id": int(link.dst_node_id),
        "road_class": _road_class_value(link),
        "component_id": int(component_id),
        "lanes": int(getattr(link, "lanes", 1)),
        "capacity_veh_per_tick": float(getattr(link, "capacity_veh_per_tick", 0.0)),
        "queue_vehicles": float(queue),
        "effective_capacity": float(cap),
        "travel_time_cost": float(cost),
        "congestion_ratio": congestion,
        "connectivity_repair": bool(connectivity_repair),
        "bridge": bool(getattr(link, "bridge_group_id", None) is not None),
        "bridge_group_id": (
            None
            if getattr(link, "bridge_group_id", None) is None
            else int(getattr(link, "bridge_group_id"))
        ),
        "bridge_name": "" if bridge_metadata is None else str(bridge_metadata.get("name", "")),
        "polyline": (
            (_scale_x(src_xy[0], bounds), _scale_y(src_xy[1], bounds)),
            (_scale_x(dst_xy[0], bounds), _scale_y(dst_xy[1], bounds)),
        ),
    }


def _legacy_roads_from_links(
    *,
    links: tuple[dict[str, Any], ...],
    bounds: Mapping[str, float],
) -> tuple[dict[str, Any], ...]:
    """Preserve direct artifact construction while marking approximate geometry."""

    groups: dict[tuple[object, ...], list[dict[str, Any]]] = {}
    for link in links:
        link_id = int(link.get("link_id", -1))
        src = link.get("src_node_id")
        dst = link.get("dst_node_id")
        if src is None or dst is None:
            key: tuple[object, ...] = ("link", link_id)
        else:
            key = (
                "endpoints",
                min(int(src), int(dst)),
                max(int(src), int(dst)),
                str(link.get("road_class", "unknown")),
            )
        groups.setdefault(key, []).append(link)

    scale = float(
        bounds.get(
            "scale_px_per_m",
            min(
                1000.0 / max(float(bounds.get("width", 1.0)), 1.0),
                680.0 / max(float(bounds.get("height", 1.0)), 1.0),
            ),
        )
    )
    roads: list[dict[str, Any]] = []
    for geometry_id, key in enumerate(sorted(groups, key=repr)):
        group = tuple(sorted(groups[key], key=lambda item: int(item.get("link_id", -1))))
        first = group[0]
        points = tuple(first.get("polyline", ()))
        if len(points) < 2:
            raise ValueError(
                "StaticCityMapArtifact links require polylines when roads are omitted"
            )
        lane_count = sum(max(1, int(link.get("lanes", 1))) for link in group)
        section_width_m = lane_count * 3.5
        road_class = str(first.get("road_class", "unknown"))
        roads.append(
            {
                "geometry_id": geometry_id,
                "source": "legacy_link_fallback",
                "source_ref": "",
                "layer": 0,
                "corridor_id": None,
                "link_ids": tuple(int(link.get("link_id", -1)) for link in group),
                "directional_link_count": len(group),
                "road_class": road_class,
                "section_profile_id": "legacy_approximation",
                "section_width_m": section_width_m,
                "render_width_px": max(0.75, section_width_m * scale),
                "has_median": False,
                "has_shoulder": False,
                "ramp": road_class == "ramp",
                "component_id": int(first.get("component_id", -1)),
                "connectivity_repair": any(
                    bool(link.get("connectivity_repair", False)) for link in group
                ),
                "bridge": any(bool(link.get("bridge", False)) for link in group),
                "bridge_group_id": first.get("bridge_group_id"),
                "bridge_name": str(first.get("bridge_name", "")),
                "congestion_ratio": max(
                    float(link.get("congestion_ratio", 0.0)) for link in group
                ),
                "polyline": points,
            }
        )
    return tuple(roads)


def _resolve_road_geometry(
    *,
    city: Any,
    nodes: tuple[Any, ...],
    links: tuple[Any, ...],
) -> RoadGeometryCatalog:
    geometry = getattr(city, "road_geometry", None)
    if geometry is None:
        return build_endpoint_geometry_catalog(nodes=nodes, links=links)
    if not isinstance(geometry, RoadGeometryCatalog):
        raise TypeError("city_topology.road_geometry must be a RoadGeometryCatalog")
    return geometry


def _resolve_road_sections(
    *,
    city: Any,
    links: tuple[Any, ...],
    road_geometry: RoadGeometryCatalog,
) -> RoadSectionCatalog:
    sections = getattr(city, "road_sections", None)
    if sections is None:
        return compile_road_sections(links=links, road_geometry=road_geometry)
    if not isinstance(sections, RoadSectionCatalog):
        raise TypeError("city_topology.road_sections must be a RoadSectionCatalog")
    return sections


def _physical_road_payloads(
    *,
    links_raw: tuple[Any, ...],
    link_payloads: tuple[dict[str, Any], ...],
    road_geometry: RoadGeometryCatalog,
    road_sections: RoadSectionCatalog,
    bounds: Mapping[str, float],
) -> tuple[dict[str, Any], ...]:
    link_by_id = {int(link.link_id): link for link in links_raw}
    payload_by_link_id = {
        int(payload["link_id"]): payload for payload in link_payloads
    }
    assignment_ids = {item.link_id for item in road_geometry.assignments}
    if assignment_ids != set(link_by_id):
        raise ValueError("road geometry assignments must exactly cover topology links")

    link_ids_by_geometry: dict[int, list[int]] = {}
    for assignment in road_geometry.assignments:
        link_ids_by_geometry.setdefault(assignment.geometry_id, []).append(
            assignment.link_id
        )

    pixels_per_meter = float(
        bounds.get(
            "scale_px_per_m",
            min(
                1000.0 / float(bounds["width"]),
                680.0 / float(bounds["height"]),
            ),
        )
    )
    roads: list[dict[str, Any]] = []
    for centerline in road_geometry.centerlines:
        link_ids = tuple(sorted(link_ids_by_geometry.get(centerline.geometry_id, ())))
        if not link_ids:
            raise ValueError(
                f"physical centerline {centerline.geometry_id} has no link assignments"
            )
        link_classes = {_road_class_value(link_by_id[link_id]) for link_id in link_ids}
        if len(link_classes) != 1:
            raise ValueError(
                f"physical centerline {centerline.geometry_id} has mixed road classes"
            )
        section_assignments = tuple(
            road_sections.assignment_for_link(link_id) for link_id in link_ids
        )
        profile_ids = {assignment.profile_id for assignment in section_assignments}
        section_widths = {
            round(float(assignment.total_width_m), 9)
            for assignment in section_assignments
        }
        if len(profile_ids) != 1 or len(section_widths) != 1:
            raise ValueError(
                f"physical centerline {centerline.geometry_id} has inconsistent sections"
            )
        profile_id = next(iter(profile_ids))
        profile = road_sections.profile(profile_id)
        section_width_m = next(iter(section_widths))
        unit_kinds = {unit.kind for unit in profile.start.units}
        directed_payloads = tuple(payload_by_link_id[link_id] for link_id in link_ids)
        road_class = next(iter(link_classes))
        bridge_group_ids = {
            payload["bridge_group_id"]
            for payload in directed_payloads
            if payload["bridge_group_id"] is not None
        }
        if len(bridge_group_ids) > 1:
            raise ValueError(
                f"physical centerline {centerline.geometry_id} has mixed bridge groups"
            )
        bridge_group_id = (
            next(iter(bridge_group_ids)) if bridge_group_ids else None
        )
        roads.append(
            {
                "geometry_id": int(centerline.geometry_id),
                "source": centerline.source.value,
                "source_ref": centerline.source_ref,
                "layer": int(centerline.layer),
                "corridor_id": centerline.corridor_id,
                "link_ids": link_ids,
                "directional_link_count": len(link_ids),
                "road_class": road_class,
                "section_profile_id": profile_id,
                "section_width_m": section_width_m,
                "render_width_px": max(0.75, section_width_m * pixels_per_meter),
                "has_median": RoadUnitKind.MEDIAN in unit_kinds,
                "has_shoulder": RoadUnitKind.SHOULDER in unit_kinds,
                "ramp": road_class == "ramp",
                "component_id": int(directed_payloads[0]["component_id"]),
                "connectivity_repair": any(
                    bool(payload["connectivity_repair"])
                    for payload in directed_payloads
                ),
                "bridge": bool(bridge_group_ids),
                "bridge_group_id": bridge_group_id,
                "bridge_name": next(
                    (
                        str(payload["bridge_name"])
                        for payload in directed_payloads
                        if payload["bridge_name"]
                    ),
                    "",
                ),
                "congestion_ratio": max(
                    float(payload["congestion_ratio"])
                    for payload in directed_payloads
                ),
                "polyline": tuple(
                    (
                        _scale_x(point[0], bounds),
                        _scale_y(point[1], bounds),
                    )
                    for point in centerline.points_m
                ),
            }
        )
    return tuple(roads)


def _zone_payload(zone: Any, *, bounds: Mapping[str, float]) -> dict[str, Any]:
    return {
        "zone_id": int(zone.zone_id),
        "zone_type": str(getattr(zone.zone_type, "value", zone.zone_type)),
        "centroid": (
            _scale_x(float(zone.centroid_x), bounds),
            _scale_y(float(zone.centroid_y), bounds),
        ),
        "population_capacity": int(getattr(zone, "population_capacity", 0)),
        "job_capacity": int(getattr(zone, "job_capacity", 0)),
        "leisure_capacity": int(getattr(zone, "leisure_capacity", 0)),
    }


def _poi_payload(
    poi: Any,
    *,
    node_xy: Mapping[int, tuple[float, float]],
    bounds: Mapping[str, float],
) -> dict[str, Any]:
    x, y = node_xy.get(int(poi.node_id), (0.0, 0.0))
    return {
        "poi_id": int(poi.poi_id),
        "zone_id": int(poi.zone_id),
        "poi_type": str(getattr(poi.poi_type, "value", poi.poi_type)),
        "node_id": int(poi.node_id),
        "capacity_hint": int(getattr(poi, "capacity_hint", 0)),
        "point": (_scale_x(x, bounds), _scale_y(y, bounds)),
    }


def _bridge_payload(crossing: Any) -> dict[str, Any]:
    return {
        "bridge_group_id": int(crossing.bridge_group_id),
        "link_ids": tuple(int(link_id) for link_id in tuple(crossing.link_ids)),
        "barrier_id": int(crossing.barrier_id),
        "name": str(crossing.crossing_name),
    }


def _bridge_metadata_by_link_id(city: Any) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for crossing in tuple(getattr(city, "bridge_crossings", ()) or ()):
        item = _bridge_payload(crossing)
        for link_id in tuple(item["link_ids"]):
            out[int(link_id)] = item
    return out


def _node_xy_for_link(
    link: Any,
    node_xy: Mapping[int, tuple[float, float]],
) -> tuple[tuple[float, float], tuple[float, float]]:
    src_node_id = int(link.src_node_id)
    dst_node_id = int(link.dst_node_id)
    missing_ids = tuple(
        node_id for node_id in (src_node_id, dst_node_id) if node_id not in node_xy
    )
    if missing_ids:
        raise ValueError(
            f"city_topology link {int(link.link_id)} references missing node id(s): "
            f"{missing_ids}"
        )
    return node_xy[src_node_id], node_xy[dst_node_id]


def _artifact_metadata(
    *,
    state: SimulationState,
    city: Any,
    component_report: Any,
    map_focus: str,
    road_geometry: RoadGeometryCatalog,
    road_sections: RoadSectionCatalog,
) -> dict[str, Any]:
    raw = dict(getattr(city, "metadata", {}) or {})
    _require_matching_fingerprint(
        raw,
        key="road_geometry_fingerprint",
        actual=road_geometry.fingerprint,
    )
    _require_matching_fingerprint(
        raw,
        key="road_section_fingerprint",
        actual=road_sections.fingerprint,
    )
    keep_keys = (
        "engine",
        "active_call_path",
        "style_id",
        "morphology_center_pattern",
        "morphology_street_pattern",
        "morphology_evidence_status",
        "morphology_reference_cities",
        "street_network_morphometrics",
        "street_network_morphometrics_status",
        "morphology_quality_metrics",
        "morphology_quality_status",
        "morphology_quality_gate",
        "continuous_fabric_strategy",
        "continuous_fabric_segment_count",
        "seed",
        "ring_road_count",
        "bridge_count",
        "hierarchy_legibility_score",
        "road_hierarchy_module_alignment_ok",
        "road_geometry_fingerprint",
        "road_section_fingerprint",
        "road_section_profile_count",
        "node_interface_fingerprint",
        "node_interface_count",
        "physical_centerline_count",
        "outer_frame_link_share",
        "edge_link_share",
        "non_orthogonal_link_count",
        "weak_component_count_before_repair",
        "weak_component_sizes_before_repair",
        "connectivity_repair_link_count",
        "connectivity_repair_link_ids",
        "weak_component_count_after_repair",
        "weak_component_sizes_after_repair",
    )
    return {
        "scenario_seed": state.metadata.get("scenario_seed"),
        "map_focus": str(map_focus),
        "edge_backend": state.config.edge_backend,
        "flow_backend": state.config.flow_backend,
        "routing_backend": state.config.routing_backend,
        "agent_backend": state.config.agent_backend,
        "weak_component_count_rendered": component_report.component_count,
        "weak_component_sizes_rendered": component_report.component_sizes,
        **{key: raw[key] for key in keep_keys if key in raw},
        "road_geometry_fingerprint": road_geometry.fingerprint,
        "road_section_fingerprint": road_sections.fingerprint,
    }


def _require_matching_fingerprint(
    metadata: Mapping[str, Any],
    *,
    key: str,
    actual: str,
) -> None:
    recorded = metadata.get(key)
    if recorded is not None and str(recorded) != str(actual):
        raise ValueError(
            f"city topology {key} does not match the catalog being rendered"
        )


def _render_map_svg(artifact: StaticCityMapArtifact) -> str:
    width = 1080
    height = 760
    road_paths = (
        "\n".join(_render_road_ribbon(road) for road in artifact.roads)
        if "roads" in artifact.visible_layers
        else ""
    )
    zone_marks = (
        "\n".join(_render_zone_circle(zone) for zone in artifact.zones)
        if "zones" in artifact.visible_layers
        else ""
    )
    poi_marks = (
        "\n".join(_render_poi_circle(poi) for poi in artifact.pois)
        if "pois" in artifact.visible_layers
        else ""
    )
    bridge_labels = _render_bridge_labels(artifact)
    legend = _render_svg_legend()
    return f"""<svg role="img" aria-label="static generated city map" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff" />
  <g class="zone-layer">{zone_marks}</g>
  <g class="road-layer">{road_paths}</g>
  <g class="poi-layer">{poi_marks}</g>
  <g class="bridge-label">{bridge_labels}</g>
  {legend}
</svg>"""


def _render_road_ribbon(road: Mapping[str, Any]) -> str:
    points = tuple(road["polyline"])
    if len(points) < 2:
        raise ValueError("physical road polyline must contain at least two points")
    path_data = " ".join(
        ("M" if idx == 0 else "L") + f" {float(x):.2f} {float(y):.2f}"
        for idx, (x, y) in enumerate(points)
    )
    road_class = _css_token(str(road.get("road_class", "unknown")))
    congestion = max(0.0, min(float(road.get("congestion_ratio", 0.0)), 2.0))
    opacity = min(0.98, 0.68 + min(congestion, 1.5) * 0.18)
    if bool(road.get("bridge", False)):
        road_class = "bridge"
    classes = [
        "road-ribbon",
        "road-class",
        road_class,
        f'component-{int(road.get("component_id", -1))}',
    ]
    if bool(road.get("ramp", False)):
        classes.append("ramp-road")
    if bool(road.get("bridge", False)):
        classes.append("bridge-road")
    width = float(road["render_width_px"])
    common_data = (
        f'data-geometry-id="{int(road.get("geometry_id", -1))}" '
        f'data-link-ids="{escape(",".join(str(value) for value in road.get("link_ids", ())))}" '
        f'data-section-profile-id="{escape(str(road.get("section_profile_id", "")))}" '
        f'data-section-width-m="{float(road.get("section_width_m", 0.0)):.3f}" '
        f'data-component-id="{int(road.get("component_id", -1))}" '
        f'data-connectivity-repair="{str(bool(road.get("connectivity_repair", False))).lower()}" '
        f'data-bridge-group-id="{_optional_int_attr(road.get("bridge_group_id"))}" '
        f'data-congestion="{congestion:.4f}"'
    )
    paths: list[str] = []
    if bool(road.get("has_shoulder", False)):
        paths.append(
            f'<path class="road-shoulder" d="{path_data}" '
            f'stroke-width="{width + 1.4:.3f}" {common_data} />'
        )
    paths.append(
        f'<path class="{" ".join(classes)}" d="{path_data}" '
        f'stroke-width="{width:.3f}" opacity="{opacity:.3f}" {common_data} />'
    )
    if bool(road.get("has_median", False)):
        paths.append(
            f'<path class="road-median" d="{path_data}" '
            f'stroke-width="{max(0.55, width * 0.08):.3f}" {common_data} />'
        )
    if bool(road.get("connectivity_repair", False)):
        paths.append(f'<path class="road-repair" d="{path_data}" {common_data} />')
    return "\n".join(paths)


def _render_zone_circle(zone: Mapping[str, Any]) -> str:
    x, y = tuple(zone["centroid"])
    token = _css_token(str(zone.get("zone_type", "unknown")))
    fill = {
        "residential": "#4f8f7b",
        "cbd_commercial": "#315f9f",
        "industrial": "#9a6d43",
        "mixed_use": "#7d67ad",
    }.get(token, "#8c96a3")
    return (
        f'<circle class="zone {token}" cx="{x:.2f}" cy="{y:.2f}" r="18" '
        f'fill="{fill}" stroke="{fill}" data-zone-id="{int(zone.get("zone_id", -1))}" />'
    )


def _render_poi_circle(poi: Mapping[str, Any]) -> str:
    x, y = tuple(poi["point"])
    token = _css_token(str(poi.get("poi_type", "unknown")))
    fill = {
        "home": "#4f8f7b",
        "workplace": "#315f9f",
        "leisure": "#b85f4c",
    }.get(token, "#47515f")
    return (
        f'<circle class="poi {token}" cx="{x:.2f}" cy="{y:.2f}" r="2.2" '
        f'fill="{fill}" data-poi-id="{int(poi.get("poi_id", -1))}" />'
    )


def _render_svg_legend() -> str:
    entries = (
        ("expressway", "#315f9f"),
        ("arterial", "#d28b37"),
        ("collector", "#4f8f7b"),
        ("local", "#9fa8b3"),
        ("ramp", "#7d67ad"),
        ("bridge", "#2f7783"),
        ("repair-link", "#b85f4c"),
    )
    rows = []
    for idx, (label, color) in enumerate(entries):
        y = 28 + idx * 20
        rows.append(
            f'<line x1="18" y1="{y}" x2="48" y2="{y}" stroke="{color}" stroke-width="3" />'
            f'<text x="56" y="{y + 4}">{escape(label)}</text>'
        )
    return f'<g class="legend">{"".join(rows)}</g>'


def _render_bridge_labels(artifact: StaticCityMapArtifact) -> str:
    labels: dict[int, tuple[str, float, float]] = {}
    if "roads" not in artifact.visible_layers:
        return ""
    for road in artifact.roads:
        group_id = road.get("bridge_group_id")
        if group_id is None:
            continue
        points = tuple(road["polyline"])
        midpoint = points[len(points) // 2]
        labels.setdefault(
            int(group_id),
            (
                str(road.get("bridge_name", f"bridge_{int(group_id)}")),
                float(midpoint[0]),
                float(midpoint[1]),
            ),
        )
    return "\n".join(
        f'<text x="{x:.2f}" y="{y - 8.0:.2f}">{escape(name)}</text>'
        for _group_id, (name, x, y) in sorted(labels.items())
    )


def _render_count_rows(counts: Mapping[str, int]) -> str:
    if not counts:
        return '<tr><td>none</td><td>0</td></tr>'
    return "\n".join(
        f"<tr><td>{escape(str(key))}</td><td>{int(value)}</td></tr>"
        for key, value in sorted(dict(counts).items())
    )


def _render_layer_control(layer: str, selected: bool) -> str:
    label = {"roads": "Roads", "zones": "Zones", "pois": "POIs"}[layer]
    disabled = "" if selected else ' disabled aria-disabled="true"'
    return (
        f'<button type="button" data-layer-toggle="{layer}" '
        f'aria-pressed="{str(bool(selected)).lower()}"{disabled}>{label}</button>'
    )


def _normalize_visible_layers(values: object) -> tuple[str, ...]:
    if isinstance(values, str):
        raise ValueError("visible_layers must be an iterable of layer names")
    try:
        requested = tuple(str(value) for value in values)  # type: ignore[union-attr]
    except TypeError as exc:
        raise ValueError("visible_layers must be an iterable of layer names") from exc
    allowed = ("roads", "zones", "pois")
    unknown = tuple(sorted(set(requested) - set(allowed)))
    if unknown:
        raise ValueError(f"unknown static map layer name(s): {unknown}")
    if len(set(requested)) != len(requested):
        raise ValueError("visible_layers must not contain duplicates")
    return tuple(layer for layer in allowed if layer in requested)


def _scale_x(x: float, bounds: Mapping[str, float]) -> float:
    if "scale_px_per_m" in bounds:
        return float(bounds["offset_x_px"]) + (
            (float(x) - float(bounds["min_x"]))
            * float(bounds["scale_px_per_m"])
        )
    return 40.0 + (1000.0 * (float(x) - float(bounds["min_x"])) / float(bounds["width"]))


def _scale_y(y: float, bounds: Mapping[str, float]) -> float:
    # SVG y grows downward; city coordinates grow upward.
    if "scale_px_per_m" in bounds:
        return float(bounds["offset_y_px"]) + (
            (float(bounds["max_y"]) - float(y))
            * float(bounds["scale_px_per_m"])
        )
    return 720.0 - (680.0 * (float(y) - float(bounds["min_y"])) / float(bounds["height"]))


def _array_value(array: Any, idx: int, default: float) -> float:
    arr = np.asarray(array, dtype=np.float32)
    if arr.ndim != 1 or int(idx) < 0 or int(idx) >= int(arr.shape[0]):
        return float(default)
    return float(arr[int(idx)])


def _road_class_value(link: Any) -> str:
    return str(getattr(getattr(link, "road_class", "unknown"), "value", getattr(link, "road_class", "unknown")))


def _optional_int_attr(value: Any) -> str:
    return "" if value is None else str(int(value))


def _css_token(value: str) -> str:
    out = []
    for char in str(value).strip().lower():
        if char.isalnum():
            out.append(char)
        elif char in {"_", "-"}:
            out.append("_" if char == "_" else "-")
        else:
            out.append("-")
    token = "".join(out).strip("-_")
    return token or "unknown"
