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

    def __post_init__(self) -> None:
        self.scenario_id = str(self.scenario_id)
        self.geometry_version = str(self.geometry_version)
        self.bounds = {str(key): float(value) for key, value in dict(self.bounds).items()}
        self.nodes = tuple(dict(item) for item in self.nodes)
        self.links = tuple(dict(item) for item in self.links)
        self.zones = tuple(dict(item) for item in self.zones)
        self.pois = tuple(dict(item) for item in self.pois)
        self.bridges = tuple(dict(item) for item in self.bridges)
        self.metadata = dict(self.metadata)
        self.label = str(self.label)

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def link_count(self) -> int:
        return len(self.links)

    @property
    def zone_count(self) -> int:
        return len(self.zones)

    @property
    def poi_count(self) -> int:
        return len(self.pois)

    def to_dict(self) -> dict[str, Any]:
        """Serialize this artifact to a stable JSON-safe dictionary."""

        road_class_counts = Counter(str(link.get("road_class", "")) for link in self.links)
        zone_type_counts = Counter(str(zone.get("zone_type", "")) for zone in self.zones)
        poi_type_counts = Counter(str(poi.get("poi_type", "")) for poi in self.pois)
        return {
            "scenario_id": self.scenario_id,
            "geometry_version": self.geometry_version,
            "label": self.label,
            "node_count": self.node_count,
            "link_count": self.link_count,
            "zone_count": self.zone_count,
            "poi_count": self.poi_count,
            "bounds": dict(self.bounds),
            "road_class_counts": dict(sorted(road_class_counts.items())),
            "zone_type_counts": dict(sorted(zone_type_counts.items())),
            "poi_type_counts": dict(sorted(poi_type_counts.items())),
            "nodes": tuple(dict(item) for item in self.nodes),
            "links": tuple(dict(item) for item in self.links),
            "zones": tuple(dict(item) for item in self.zones),
            "pois": tuple(dict(item) for item in self.pois),
            "bridges": tuple(dict(item) for item in self.bridges),
            "metadata": dict(self.metadata),
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
) -> StaticCityMapArtifact:
    """Build a static map artifact from a generated `SimulationState`."""

    city = state.static.city_topology
    if city is None:
        raise ValueError("state.static.city_topology is required for static city map rendering")
    nodes_raw = tuple(getattr(city, "nodes", ()) or ())
    links_raw = tuple(getattr(city, "links", ()) or ())
    if not nodes_raw or not links_raw:
        raise ValueError("city_topology must contain non-empty nodes and links")

    component_report = analyze_weak_connectivity(nodes=nodes_raw, links=links_raw)
    bounds_nodes = _bounds_nodes(
        nodes_raw,
        component_report=component_report,
        focus_largest_component=focus_largest_component,
    )
    bounds = _geometry_bounds(bounds_nodes)
    node_xy = {
        int(node.node_id): (float(node.x), float(node.y))
        for node in nodes_raw
    }
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
    zones = tuple(_zone_payload(zone, bounds=bounds) for zone in tuple(state.static.zones or ()))
    pois = tuple(_poi_payload(poi, node_xy=node_xy, bounds=bounds) for poi in tuple(state.static.pois or ()))
    bridges = tuple(_bridge_payload(crossing) for crossing in tuple(getattr(city, "bridge_crossings", ()) or ()))

    return StaticCityMapArtifact(
        scenario_id=str(state.static.scenario_id or "unknown"),
        geometry_version=str(state.static.ui_network_geometry_version or "unknown"),
        bounds={
            "min_x": bounds["min_x"],
            "min_y": bounds["min_y"],
            "max_x": bounds["max_x"],
            "max_y": bounds["max_y"],
            "width": bounds["width"],
            "height": bounds["height"],
        },
        nodes=nodes,
        links=links,
        zones=zones,
        pois=pois,
        bridges=bridges,
        metadata=_artifact_metadata(
            state=state,
            city=city,
            component_report=component_report,
            map_focus="largest_component" if focus_largest_component else "full_extent",
        ),
    )


def render_static_city_map_html(artifact: StaticCityMapArtifact) -> str:
    """Render a static, dependency-free city map HTML artifact."""

    payload_json = escape(artifact.to_json())
    svg = _render_map_svg(artifact)
    road_rows = _render_count_rows(artifact.to_dict()["road_class_counts"])
    zone_rows = _render_count_rows(artifact.to_dict()["zone_type_counts"])
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
    .metric-row {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 14px 0; }}
    .metric {{ background: #ffffff; border: 1px solid #d5dbe3; border-radius: 8px; padding: 11px; }}
    .metric strong {{ display: block; margin-top: 3px; font-size: 21px; }}
    table {{ border-collapse: collapse; width: 100%; background: #ffffff; border: 1px solid #d5dbe3; }}
    td, th {{ border-bottom: 1px solid #e4e8ed; padding: 8px 10px; text-align: left; font-size: 13px; }}
    th {{ background: #ecf0f4; font-weight: 650; }}
    .road-class.local {{ stroke: #9fa8b3; stroke-width: 0.75; }}
    .road-class.collector {{ stroke: #4f8f7b; stroke-width: 1.2; }}
    .road-class.arterial {{ stroke: #d28b37; stroke-width: 1.8; }}
    .road-class.expressway {{ stroke: #315f9f; stroke-width: 2.8; }}
    .road-class.ramp {{ stroke: #7d67ad; stroke-width: 1.4; }}
    .road-class.bridge {{ stroke: #2f7783; stroke-width: 2.4; }}
    .road-class.unknown {{ stroke: #777f89; stroke-width: 1; }}
    .road-class.repair-link {{ stroke: #b85f4c; stroke-width: 2.2; stroke-dasharray: 7 4; opacity: 0.92; }}
    .zone-layer circle {{ fill-opacity: 0.12; stroke-width: 1.1; }}
    .poi-layer circle {{ stroke: #ffffff; stroke-width: 1.1; }}
    .bridge-label text {{ font-size: 10px; fill: #1f4f59; paint-order: stroke; stroke: #ffffff; stroke-width: 3px; }}
    .legend text {{ font-size: 11px; fill: #354050; }}
    .note {{ color: #5b6674; font-size: 13px; line-height: 1.45; }}
  </style>
</head>
<body>
<main class="metroflow-static-city-map" data-static-city-map="{payload_json}">
  <h1>Metroflow Static City Map</h1>
  <div class="meta">{escape(artifact.label)} &middot; scenario <code>{escape(artifact.scenario_id)}</code> &middot; geometry <code>{escape(artifact.geometry_version)}</code></div>
  <section class="metric-row">
    <div class="metric">nodes<strong>{artifact.node_count}</strong></div>
    <div class="metric">links<strong>{artifact.link_count}</strong></div>
    <div class="metric">zones<strong>{artifact.zone_count}</strong></div>
    <div class="metric">POIs<strong>{artifact.poi_count}</strong></div>
  </section>
  <section class="map-frame">{svg}</section>
  <h2>Road Class Counts</h2>
  <table><thead><tr><th>road class</th><th>count</th></tr></thead><tbody>{road_rows}</tbody></table>
  <h2>Zone Type Counts</h2>
  <table><thead><tr><th>zone type</th><th>count</th></tr></thead><tbody>{zone_rows}</tbody></table>
  <p class="note">This static map is a smoke review artifact for generated-city structure and runtime overlay inspection. It is not a validation claim.</p>
</main>
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


def _geometry_bounds(nodes: tuple[Any, ...]) -> dict[str, float]:
    xs = np.asarray([float(node.x) for node in nodes], dtype=np.float64)
    ys = np.asarray([float(node.y) for node in nodes], dtype=np.float64)
    min_x = float(np.min(xs))
    max_x = float(np.max(xs))
    min_y = float(np.min(ys))
    max_y = float(np.max(ys))
    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)
    pad_x = width * 0.04
    pad_y = height * 0.04
    return {
        "min_x": min_x - pad_x,
        "max_x": max_x + pad_x,
        "min_y": min_y - pad_y,
        "max_y": max_y + pad_y,
        "width": width + (2.0 * pad_x),
        "height": height + (2.0 * pad_y),
    }


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
) -> dict[str, Any]:
    raw = dict(getattr(city, "metadata", {}) or {})
    keep_keys = (
        "engine",
        "active_call_path",
        "style_id",
        "seed",
        "ring_road_count",
        "bridge_count",
        "hierarchy_legibility_score",
        "csur_module_alignment_ok",
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
        "weak_component_count_rendered": component_report.component_count,
        "weak_component_sizes_rendered": component_report.component_sizes,
        **{key: raw[key] for key in keep_keys if key in raw},
    }


def _render_map_svg(artifact: StaticCityMapArtifact) -> str:
    width = 1080
    height = 760
    link_lines = "\n".join(_render_link_line(link) for link in artifact.links)
    zone_marks = "\n".join(_render_zone_circle(zone) for zone in artifact.zones)
    poi_marks = "\n".join(_render_poi_circle(poi) for poi in artifact.pois)
    bridge_labels = _render_bridge_labels(artifact)
    legend = _render_svg_legend()
    return f"""<svg role="img" aria-label="static generated city map" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff" />
  <g class="zone-layer">{zone_marks}</g>
  <g class="road-layer">{link_lines}</g>
  <g class="poi-layer">{poi_marks}</g>
  <g class="bridge-label">{bridge_labels}</g>
  {legend}
</svg>"""


def _render_link_line(link: Mapping[str, Any]) -> str:
    (x1, y1), (x2, y2) = tuple(link["polyline"])
    road_class = _css_token(str(link.get("road_class", "unknown")))
    congestion = max(0.0, min(float(link.get("congestion_ratio", 0.0)), 2.0))
    opacity = 0.38 + min(congestion, 1.5) * 0.28
    if bool(link.get("bridge", False)):
        road_class = "bridge"
    classes = ["road-class", road_class, f'component-{int(link.get("component_id", -1))}']
    if bool(link.get("connectivity_repair", False)):
        classes.append("repair-link")
    return (
        f'<line class="{" ".join(classes)}" '
        f'x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
        f'opacity="{opacity:.3f}" data-link-id="{int(link.get("link_id", -1))}" '
        f'data-component-id="{int(link.get("component_id", -1))}" '
        f'data-connectivity-repair="{str(bool(link.get("connectivity_repair", False))).lower()}" '
        f'data-bridge-group-id="{_optional_int_attr(link.get("bridge_group_id"))}" '
        f'data-congestion="{congestion:.4f}" />'
    )


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
        f'<circle class="poi {token}" cx="{x:.2f}" cy="{y:.2f}" r="3.2" '
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
    for link in artifact.links:
        group_id = link.get("bridge_group_id")
        if group_id is None:
            continue
        (x1, y1), (x2, y2) = tuple(link["polyline"])
        labels.setdefault(
            int(group_id),
            (
                str(link.get("bridge_name", f"bridge_{int(group_id)}")),
                (float(x1) + float(x2)) / 2.0,
                (float(y1) + float(y2)) / 2.0,
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


def _scale_x(x: float, bounds: Mapping[str, float]) -> float:
    return 40.0 + (1000.0 * (float(x) - float(bounds["min_x"])) / float(bounds["width"]))


def _scale_y(y: float, bounds: Mapping[str, float]) -> float:
    # SVG y grows downward; city coordinates grow upward.
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
