"""Reviewer-facing static comparison bundle for synthetic morphology styles."""

from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path
from typing import Iterable

from metroflow.city.morphology_reference import MORPHOLOGY_ARCHETYPES
from metroflow.sim.config import CityGenerationConfig, SimulationConfig
from metroflow.sim.init import build_initial_simulation_state

from .static_map import build_static_city_map_artifact, write_static_city_map_html

__all__ = ["write_city_morphology_atlas"]


def write_city_morphology_atlas(
    output_dir: str | Path,
    *,
    seed: int = 17,
    topology_mode: str = "sidecar_local_fabric_planar",
    style_ids: Iterable[str] = MORPHOLOGY_ARCHETYPES,
) -> dict[str, Path]:
    """Write per-style static maps plus one comparison index and manifest."""

    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    styles = tuple(str(style_id) for style_id in style_ids)
    if not styles:
        raise ValueError("style_ids must not be empty")
    entries: list[dict[str, object]] = []
    paths: dict[str, Path] = {}

    for style_id in styles:
        bundle = build_initial_simulation_state(
            config=SimulationConfig(population_target=500, active_agent_capacity=16),
            city_config=CityGenerationConfig(
                topology_mode=topology_mode,
                morphology_style_id=style_id,
            ),
            scenario_seed=int(seed),
            eager_trip_generation=False,
        )
        artifact = build_static_city_map_artifact(bundle.state)
        html_path = write_static_city_map_html(
            artifact,
            target / f"{style_id}.html",
        )
        metadata = dict(bundle.city_topology.metadata)
        entry = {
            "style_id": style_id,
            "street_pattern": metadata.get("morphology_street_pattern"),
            "center_pattern": metadata.get("morphology_center_pattern"),
            "reference_cities": list(metadata.get("morphology_reference_cities", ())),
            "morphometrics": dict(metadata["street_network_morphometrics"]),
            "quality_metrics": dict(metadata["morphology_quality_metrics"]),
            "quality_gate": dict(metadata["morphology_quality_gate"]),
            "continuous_fabric_strategy": metadata.get("continuous_fabric_strategy"),
            "continuous_fabric_segment_count": int(
                metadata.get("continuous_fabric_segment_count", 0)
            ),
            "node_count": len(bundle.city_topology.nodes),
            "link_count": len(bundle.city_topology.links),
            "geometry_fingerprint": bundle.city_topology.road_geometry.fingerprint,
            "validation_status": metadata.get("city_map_validation_status", "diagnostic_only"),
            "html": html_path.name,
        }
        entries.append(entry)
        paths[f"{style_id}_html"] = html_path

    manifest = {
        "artifact_format_version": "city_morphology_atlas_v3",
        "evidence_status": "diagnostic_not_city_replication",
        "seed": int(seed),
        "topology_mode": str(topology_mode),
        "literature_source": "https://doi.org/10.1007/s41109-019-0189-1",
        "raw_osm_data_included": False,
        "html_retention": "reproducible_local_output_not_required_in_version_control",
        "styles": entries,
    }
    manifest_path = target / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    index_path = target / "index.html"
    index_path.write_text(_render_atlas_index(manifest), encoding="utf-8")
    paths["manifest"] = manifest_path
    paths["index"] = index_path
    return paths


def _render_atlas_index(manifest: dict[str, object]) -> str:
    panels: list[str] = []
    for raw_entry in manifest["styles"]:
        entry = dict(raw_entry)
        metrics = dict(entry["morphometrics"])
        quality = dict(entry["quality_metrics"])
        panels.append(
            "<section>"
            f"<h2>{escape(str(entry['style_id']))}</h2>"
            f"<p>{escape(str(entry['center_pattern']))} / "
            f"{escape(str(entry['street_pattern']))}</p>"
            f"<p>order {float(metrics['orientation_order']):.3f} &middot; "
            f"entropy {float(metrics['orientation_entropy']):.3f} &middot; "
            f"degree {float(metrics['mean_node_degree']):.3f}</p>"
            f"<p>density {float(quality['street_density_km_per_km2']):.2f} km/km&sup2; &middot; "
            f"continuity {float(quality['block_continuity']):.3f} &middot; "
            "local cell presence "
            f"{float(quality['global_local_street_cell_presence_share']):.3f}</p>"
            f"<iframe loading=\"lazy\" src=\"{escape(str(entry['html']))}\" "
            f"title=\"{escape(str(entry['style_id']))}\"></iframe>"
            "</section>"
        )
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Metroflow morphology atlas</title>
<style>
body{margin:0;background:#f4f5f7;color:#17202a;font:14px system-ui,sans-serif}header{padding:20px 24px;background:#fff;border-bottom:1px solid #ccd1d8}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(520px,1fr));gap:16px;padding:16px}section{background:#fff;border:1px solid #ccd1d8;border-radius:6px;overflow:hidden}h2,p{margin:10px 14px}iframe{display:block;width:100%;height:640px;border:0;border-top:1px solid #e1e4e8}.note{color:#5b6573}
</style></head><body>
<header><h1>Metroflow synthetic morphology atlas</h1><p class="note">Diagnostic comparison only. Reference metrics do not claim replication of named cities.</p></header>
<main>""" + "".join(panels) + "</main></body></html>"


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument(
        "--topology-mode",
        default="sidecar_local_fabric_planar",
        choices=("sidecar_local_fabric", "sidecar_local_fabric_planar"),
    )
    args = parser.parse_args()
    paths = write_city_morphology_atlas(
        args.output_dir,
        seed=args.seed,
        topology_mode=args.topology_mode,
    )
    print(json.dumps({key: str(value) for key, value in paths.items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
