"""Multi-seed diagnostic audit for morphology-gated zone and POI placement."""

from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
from typing import Any, Iterable

from metroflow.city.generator_v2 import GeneratorV2
from metroflow.city.landuse_accessibility import (
    audit_landuse_accessibility,
    compare_landuse_placements,
)
from metroflow.city.morphology_reference import MORPHOLOGY_ARCHETYPES
from metroflow.city.zones import ZoningPlacementResult, generate_zones_and_pois
from metroflow.sim.config import CityGenerationConfig, SimulationConfig
from metroflow.sim.state import (
    SimulationDynamicRefs,
    SimulationState,
    SimulationStaticRefs,
)

from .static_map import build_static_city_map_artifact, write_static_city_map_html

__all__ = ["write_morphology_landuse_accessibility_audit"]


def write_morphology_landuse_accessibility_audit(
    output_dir: str | Path,
    *,
    seeds: Iterable[int] = (17, 29, 41),
    style_ids: Iterable[str] = MORPHOLOGY_ARCHETYPES,
    topology_mode: str = "sidecar_local_fabric_planar",
    population_target: int = 20_000,
) -> dict[str, Path]:
    """Write metrics and one static legacy/morphology map pair per style."""

    resolved_seeds = tuple(int(seed) for seed in seeds)
    resolved_styles = tuple(str(style_id) for style_id in style_ids)
    if len(resolved_seeds) < 3:
        raise ValueError("morphology land-use audit requires at least three seeds")
    if len(set(resolved_seeds)) != len(resolved_seeds):
        raise ValueError("morphology land-use audit seeds must be unique")
    if not resolved_styles:
        raise ValueError("morphology land-use audit style_ids must not be empty")
    if len(set(resolved_styles)) != len(resolved_styles):
        raise ValueError("morphology land-use audit style_ids must be unique")
    unknown_styles = tuple(
        style_id
        for style_id in resolved_styles
        if style_id not in MORPHOLOGY_ARCHETYPES
    )
    if unknown_styles:
        raise ValueError(
            "morphology land-use audit requires registered safe style ids: "
            f"{unknown_styles}"
        )
    if int(population_target) < 1:
        raise ValueError("population_target must be >= 1")

    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise ValueError("morphology land-use audit output_dir must be empty")
    target.mkdir(parents=True, exist_ok=True)
    generator = GeneratorV2()
    style_entries: list[dict[str, Any]] = []
    map_entries: list[dict[str, Any]] = []
    paths: dict[str, Path] = {}

    for style_index, style_id in enumerate(resolved_styles):
        runs: list[dict[str, Any]] = []
        for seed_index, seed in enumerate(resolved_seeds):
            topology = generator.generate_preview_topology(
                {
                    "scenario_id": "synthetic_smoke",
                    "seed": seed,
                    "preview_mode": str(topology_mode),
                    "style_id": style_id,
                }
            )
            legacy = _generate_zoning(
                topology=topology,
                seed=seed,
                population_target=int(population_target),
                topology_mode=topology_mode,
                style_id=style_id,
                coupling_mode="legacy",
            )
            morphology = _generate_zoning(
                topology=topology,
                seed=seed,
                population_target=int(population_target),
                topology_mode=topology_mode,
                style_id=style_id,
                coupling_mode="morphology_gated",
            )
            legacy_audit = _audit(topology, legacy)
            morphology_audit = _audit(topology, morphology)
            comparison = compare_landuse_placements(
                legacy=legacy,
                morphology=morphology,
                legacy_audit=legacy_audit,
                morphology_audit=morphology_audit,
            )
            runs.append(
                {
                    "seed": seed,
                    "geometry_fingerprint": topology.road_geometry.fingerprint,
                    "legacy": legacy_audit.as_dict(),
                    "morphology": morphology_audit.as_dict(),
                    "comparison": comparison.as_dict(),
                }
            )
            if seed_index == 0:
                map_entry = _write_map_pair(
                    target=target,
                    topology=topology,
                    legacy=legacy,
                    morphology=morphology,
                    seed=seed,
                    style_id=style_id,
                    population_target=int(population_target),
                )
                map_entries.append(map_entry)
                for mode in ("legacy", "morphology"):
                    path = target / map_entry[f"{mode}_html"]
                    paths[f"{style_id}_{mode}_map"] = path
                    if style_index == 0:
                        paths[f"{mode}_map"] = path
        style_entries.append({"style_id": style_id, "runs": runs})

    payload = {
        "artifact_format_version": "morphology_landuse_accessibility_v1",
        "evidence_status": "diagnostic_not_validation",
        "topology_mode": str(topology_mode),
        "population_target": int(population_target),
        "seeds": list(resolved_seeds),
        "styles": style_entries,
        "decision_boundary": {
            "demand_policy_authorized": False,
            "pr46_authorized": False,
            "route_legality_changed": False,
            "runtime_backend_changed": False,
            "falsifier": (
                "any POI access validity or directed zone-pair reachability loss"
            ),
        },
    }
    json_path = target / "morphology-landuse-accessibility.json"
    markdown_path = target / "morphology-landuse-accessibility.md"
    index_path = target / "index.html"
    manifest_path = target / "manifest.json"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")
    index_path.write_text(
        _render_index(payload=payload, map_entries=map_entries),
        encoding="utf-8",
    )
    manifest = {
        "artifact_format_version": "morphology_landuse_accessibility_bundle_v1",
        "evidence_status": "diagnostic_not_validation",
        "data_json": json_path.name,
        "review_markdown": markdown_path.name,
        "index_html": index_path.name,
        "map_entries": map_entries,
        "seeds": list(resolved_seeds),
        "style_ids": list(resolved_styles),
        "demand_policy_changed": False,
        "pr46_authorized": False,
        "runtime_backend_changed": False,
        "html_retention": "reproducible_local_output_not_required_in_version_control",
        "artifact_files": sorted(
            {
                json_path.name,
                markdown_path.name,
                index_path.name,
                *(
                    filename
                    for entry in map_entries
                    for filename in (entry["legacy_html"], entry["morphology_html"])
                ),
            }
        ),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    paths.update(
        {
            "json": json_path,
            "markdown": markdown_path,
            "index": index_path,
            "manifest": manifest_path,
        }
    )
    return paths


def _generate_zoning(
    *,
    topology: Any,
    seed: int,
    population_target: int,
    topology_mode: str,
    style_id: str,
    coupling_mode: str,
) -> ZoningPlacementResult:
    return generate_zones_and_pois(
        topology,
        config=CityGenerationConfig(
            topology_mode=str(topology_mode),
            morphology_style_id=str(style_id),
            zone_poi_coupling_mode=str(coupling_mode),
        ),
        seed=int(seed),
        population_target=int(population_target),
        validate=True,
    )


def _audit(topology: Any, zoning: ZoningPlacementResult):
    return audit_landuse_accessibility(
        nodes=topology.nodes,
        links=topology.links,
        zones=zoning.zones,
        pois=zoning.pois,
        node_zone_by_id=zoning.node_zone_by_id,
        zone_node_ids=zoning.zone_node_ids,
        coupling_mode=str(zoning.metadata["zone_poi_coupling_resolved_mode"]),
        zoning_fingerprint=str(zoning.metadata["zoning_placement_fingerprint"]),
    )


def _write_map_pair(
    *,
    target: Path,
    topology: Any,
    legacy: ZoningPlacementResult,
    morphology: ZoningPlacementResult,
    seed: int,
    style_id: str,
    population_target: int,
) -> dict[str, Any]:
    output: dict[str, Any] = {"style_id": str(style_id), "seed": int(seed)}
    for label, zoning in (("legacy", legacy), ("morphology", morphology)):
        state = _diagnostic_state(
            topology=topology,
            zoning=zoning,
            seed=seed,
            population_target=population_target,
        )
        artifact = build_static_city_map_artifact(state)
        filename = f"{style_id}-{label}.html"
        write_static_city_map_html(artifact, target / filename)
        output[f"{label}_html"] = filename
    return output


def _diagnostic_state(
    *,
    topology: Any,
    zoning: ZoningPlacementResult,
    seed: int,
    population_target: int,
) -> SimulationState:
    geometry_fingerprint = str(topology.road_geometry.fingerprint)
    zoning_metadata = {
        key: zoning.metadata[key]
        for key in (
            "zoning_placement_fingerprint",
            "zoning_policy",
            "poi_placement_policy",
            "zone_poi_coupling_requested_mode",
            "zone_poi_coupling_resolved_mode",
            "zone_poi_coupling_fallback_reason",
            "zone_poi_coupling_gate_version",
            "zone_poi_coupling_gate_digest",
            "zone_poi_coupling_anchor_digest",
        )
    }
    return SimulationState(
        config=SimulationConfig(
            population_target=int(population_target),
            active_agent_capacity=1,
        ),
        static=SimulationStaticRefs(
            scenario_id=f"synthetic-{int(seed)}",
            city_topology=topology,
            zones=zoning.zones,
            pois=zoning.pois,
            routing_static={
                "node_zone_by_id": dict(zoning.node_zone_by_id),
                "zone_node_ids": dict(zoning.zone_node_ids),
            },
            ui_network_geometry_version=(
                f"landuse-audit-{int(seed)}-{geometry_fingerprint}"
            ),
            metadata={
                "scenario_seed": int(seed),
                "road_geometry_fingerprint": geometry_fingerprint,
                **zoning_metadata,
            },
        ),
        dynamic=SimulationDynamicRefs(),
        metadata={"scenario_seed": int(seed), **zoning_metadata},
    )


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Morphology Land-Use Accessibility Audit",
        "",
        "Diagnostic only. This is not empirical validation and does not authorize PR46 or a demand-policy change.",
        "",
        "| Style | Seed | Legacy/Morph POI valid | Legacy/Morph zone coverage | Legacy/Morph reachability | Aggregate preserved | Zones changed | POIs changed |",
        "|---|---:|---:|---:|---:|:---:|---:|---:|",
    ]
    for style in payload["styles"]:
        for run in style["runs"]:
            morphology = run["morphology"]
            legacy = run["legacy"]
            comparison = run["comparison"]
            lines.append(
                f"| {style['style_id']} | {run['seed']} | "
                f"{float(legacy['poi_access_valid_share']):.3f}/"
                f"{float(morphology['poi_access_valid_share']):.3f} | "
                f"{float(legacy['zone_access_coverage_share']):.3f}/"
                f"{float(morphology['zone_access_coverage_share']):.3f} | "
                f"{float(legacy['directed_zone_pair_reachability_share']):.3f}/"
                f"{float(morphology['directed_zone_pair_reachability_share']):.3f} | "
                f"{'yes' if comparison['aggregate_contract_preserved'] else 'no'} | "
                f"{float(comparison['zone_center_changed_share']):.3f} | "
                f"{float(comparison['poi_access_node_changed_share']):.3f} |"
            )
    lines.extend(
        [
            "",
            "## Compact CCoT",
            "",
            "Question: Does morphology-aware placement preserve network accessibility?",
            "Evidence: Multi-seed POI access validity and directed representative-zone reachability.",
            "Inference: Structural placement is acceptable only when it retains legacy accessibility.",
            "Counterevidence checked: Weak connectivity and visual separation alone are insufficient.",
            "Decision: Keep this audit diagnostic; it does not authorize PR46 and no demand or route authority is changed.",
            "Falsifier: Any run loses POI validity or directed zone-pair reachability.",
            "Next action: Any PR46 admission requires separate decision-changing demand-defect evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_index(
    *,
    payload: dict[str, Any],
    map_entries: list[dict[str, Any]],
) -> str:
    sections = []
    for entry in map_entries:
        style = escape(entry["style_id"])
        sections.append(
            f"<section><h2>{style}</h2><div class=\"maps\">"
            f"<div><h3>Legacy</h3><iframe src=\"{escape(entry['legacy_html'])}\" "
            f"title=\"{style} legacy\"></iframe></div>"
            f"<div><h3>Morphology gated</h3><iframe src=\"{escape(entry['morphology_html'])}\" "
            f"title=\"{style} morphology gated\"></iframe></div>"
            "</div></section>"
        )
    embedded = escape(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Metroflow land-use accessibility audit</title><style>
body{{margin:0;background:#f4f6f8;color:#17202a;font:14px system-ui,sans-serif}}header{{padding:20px 24px;background:#fff;border-bottom:1px solid #ccd3dc}}main{{padding:16px 24px}}section{{border-top:1px solid #ccd3dc;padding:12px 0 24px}}.maps{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}iframe{{width:100%;height:720px;border:1px solid #ccd3dc;background:#fff}}.note{{color:#5b6674}}@media(max-width:900px){{.maps{{grid-template-columns:1fr}}}}
</style></head><body><header><h1>Morphology land-use accessibility audit</h1>
<p class="note">Diagnostic only. Not empirical validation and does not authorize PR46 or demand-policy changes.</p></header>
<main data-landuse-accessibility="{embedded}">{''.join(sections)}</main></body></html>"""


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--seeds", default="17,29,41")
    parser.add_argument("--population-target", type=int, default=20_000)
    args = parser.parse_args()
    seeds = tuple(int(value.strip()) for value in args.seeds.split(",") if value.strip())
    paths = write_morphology_landuse_accessibility_audit(
        args.output_dir,
        seeds=seeds,
        population_target=args.population_target,
    )
    print(json.dumps({key: str(value) for key, value in paths.items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
