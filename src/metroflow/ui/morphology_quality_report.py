"""Write the multi-seed generated-city morphology quality report."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any, Iterable

from metroflow.city.generator_v2 import GeneratorV2
from metroflow.city.morphology_reference import MORPHOLOGY_ARCHETYPES

__all__ = ["write_morphology_quality_envelope"]


def write_morphology_quality_envelope(
    output_dir: str | Path,
    *,
    seeds: Iterable[int] = (17, 29, 41),
    style_ids: Iterable[str] | None = None,
    scenario_id: str = "synthetic_smoke",
    topology_mode: str = "sidecar_local_fabric_planar",
) -> dict[str, Path]:
    """Write deterministic multi-seed JSON and Markdown diagnostic artifacts."""

    resolved_seeds = tuple(int(seed) for seed in seeds)
    resolved_styles = tuple(
        str(style_id)
        for style_id in (
            MORPHOLOGY_ARCHETYPES if style_ids is None else tuple(style_ids)
        )
    )
    if len(resolved_seeds) < 3:
        raise ValueError("morphology quality envelope requires at least three seeds")
    if len(set(resolved_seeds)) != len(resolved_seeds):
        raise ValueError("morphology quality envelope seeds must be unique")
    if not resolved_styles:
        raise ValueError("morphology quality envelope style_ids must not be empty")

    generator = GeneratorV2()
    style_entries: list[dict[str, Any]] = []
    for style_id in resolved_styles:
        runs: list[dict[str, Any]] = []
        for seed in resolved_seeds:
            topology = generator.generate_preview_topology(
                {
                    "scenario_id": str(scenario_id),
                    "seed": seed,
                    "preview_mode": str(topology_mode),
                    "style_id": style_id,
                }
            )
            metrics = dict(topology.metadata["morphology_quality_metrics"])
            runs.append(
                {
                    "seed": seed,
                    "geometry_fingerprint": topology.road_geometry.fingerprint,
                    "metrics": metrics,
                }
            )
        numeric_keys = tuple(
            key
            for key, value in runs[0]["metrics"].items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        )
        aggregate = {
            key: _aggregate_values(
                tuple(float(run["metrics"][key]) for run in runs)
            )
            for key in numeric_keys
        }
        style_entries.append(
            {
                "style_id": style_id,
                "runs": runs,
                "aggregate": aggregate,
            }
        )

    payload = {
        "artifact_format_version": "city_morphology_quality_v2",
        "evidence_status": "diagnostic_not_city_replication",
        "scenario_id": str(scenario_id),
        "topology_mode": str(topology_mode),
        "seeds": list(resolved_seeds),
        "styles": style_entries,
        "metric_definitions": {
            "block_continuity": "one minus physical road length share on graph bridges",
            "street_density_km_per_km2": "physical centerline km per node convex-hull km2",
            "district_quadrant_presence_share": "mean occupied quadrant share inside district envelopes",
            "connector_to_local_length_ratio": "non-local physical length divided by local physical length",
            "global_street_cell_presence_share": "all physical centerlines present on a 24 by 24 convex-hull raster",
            "global_local_street_cell_presence_share": "local-class centerlines present on a 24 by 24 convex-hull raster",
            "global_local_junction_proximity_share": "12 by 12 hull-cell centers within 0.5 cell diagonals of a local degree-3 junction",
        },
    }
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "morphology-quality.json"
    markdown_path = target / "morphology-quality.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_render_quality_markdown(payload), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def _aggregate_values(values: tuple[float, ...]) -> dict[str, float]:
    return {
        "min": float(min(values)),
        "median": float(statistics.median(values)),
        "max": float(max(values)),
    }


def _render_quality_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# City Morphology Quality Envelope",
        "",
        "Diagnostic structural envelope only. It is not city-replication or runtime-validation evidence.",
        "",
        "| Style | Density km/km2 | Local cells | Junction proximity | Block continuity | Four-way |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for entry in payload["styles"]:
        aggregate = entry["aggregate"]

        def median(key: str) -> float:
            return float(aggregate[key]["median"])

        lines.append(
            f"| {entry['style_id']} | {median('street_density_km_per_km2'):.3f} | "
            f"{median('global_local_street_cell_presence_share'):.3f} | "
            f"{median('global_local_junction_proximity_share'):.3f} | "
            f"{median('block_continuity'):.3f} | "
            f"{median('degree_four_share'):.3f} |"
        )
    lines.extend(
        [
            "",
            "## Compact CCoT",
            "",
            "Question: Do generated styles distribute local streets beyond precinct islands?",
            "Evidence: Three-seed 24 by 24 local-street cell presence plus the v1 structural metrics.",
            "Inference: Style grammar changes are admitted only when local presence improves without v1 regressions.",
            "Counterevidence checked: Static maps and named-city references are diagnostic only.",
            "Decision: Gate v2 requires project-owned minimum local cell presence without empirical fitting.",
            "Falsifier: Infill improves raster presence but degrades topology, OD, or visual continuity.",
            "Next action: Visually audit the regenerated atlas before land-use coupling.",
            "",
        ]
    )
    return "\n".join(lines)


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--seeds", default="17,29,41")
    parser.add_argument("--scenario-id", default="synthetic_smoke")
    parser.add_argument(
        "--topology-mode",
        default="sidecar_local_fabric_planar",
        choices=("sidecar_local_fabric", "sidecar_local_fabric_planar"),
    )
    args = parser.parse_args()
    seeds = tuple(int(value.strip()) for value in args.seeds.split(",") if value.strip())
    paths = write_morphology_quality_envelope(
        args.output_dir,
        seeds=seeds,
        scenario_id=args.scenario_id,
        topology_mode=args.topology_mode,
    )
    print(json.dumps({key: str(value) for key, value in paths.items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
