"""Score every available generator arm on one calibrated instrument.

The PR62 audit generates its own maps with `topology_mode="realistic_synthetic_v1"`,
so it can only score the generator under test. This runner applies the same
pinned envelope to the incumbent default, both sidecar paths, the realistic
path, and any supplied offline OSM extract, so `fail` has a reference point.

Diagnostic evidence only. Not empirical traffic, demand, route-choice, land-use
or named-city validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from metroflow.city.morphology_control_table import (
    EMPIRICAL_MORPHOLOGY_METRICS,
    MorphologyControlTable,
    MorphologyScore,
    build_morphology_control_table,
    score_street_morphology,
)
from metroflow.city.morphology_reference import MORPHOLOGY_ARCHETYPES

CONTROL_TABLE_STYLES = tuple(MORPHOLOGY_ARCHETYPES)
CONTROL_TABLE_SEEDS = (17, 29, 41, 44, 53)
LEGACY_ARMS = ("standard", "sidecar_local_fabric", "sidecar_local_fabric_planar")
REALISTIC_ARM = "realistic_synthetic_v1"
GROWTH_ARM = "growth_fabric_v1"


def collect_scores(
    *,
    styles: tuple[str, ...] = CONTROL_TABLE_STYLES,
    seeds: tuple[int, ...] = CONTROL_TABLE_SEEDS,
    osm_paths: tuple[Path, ...] = (),
) -> tuple[tuple[MorphologyScore, ...], tuple[str, ...]]:
    """Score every arm that can produce a topology; report what was skipped."""

    from metroflow.city.generator_v2 import GeneratorV2
    from metroflow.city.plausibility_audit import _realistic_city_config
    from metroflow.city.realistic_city import generate_city_map

    scores: list[MorphologyScore] = []
    skipped: list[str] = []

    for arm in LEGACY_ARMS:
        for style_id in styles:
            for seed in seeds:
                case = f"{style_id}/{seed}"
                try:
                    topology = GeneratorV2().generate_preview_topology(
                        {
                            "scenario_id": "morphology_control_table",
                            "seed": seed,
                            "preview_mode": arm,
                            "style_id": style_id,
                        }
                    )
                except Exception as exc:  # noqa: BLE001 - recorded, never silenced
                    skipped.append(f"{arm}:{case}:{type(exc).__name__}:{exc}")
                    continue
                scores.append(score_street_morphology(topology, arm=arm, case=case))

    for style_id in styles:
        for seed in seeds:
            case = f"{style_id}/{seed}"
            try:
                generated = generate_city_map(
                    _realistic_city_config(style_id),
                    scenario_id="morphology_control_table",
                    seed=seed,
                )
            except Exception as exc:  # noqa: BLE001 - recorded, never silenced
                skipped.append(f"{REALISTIC_ARM}:{case}:{type(exc).__name__}:{exc}")
                continue
            scores.append(
                score_street_morphology(generated.topology, arm=REALISTIC_ARM, case=case)
            )

    for style_id in styles:
        for seed in seeds:
            case = f"{style_id}/{seed}"
            try:
                scores.append(
                    score_street_morphology(
                        _growth_topology(style_id=style_id, seed=seed), arm=GROWTH_ARM, case=case
                    )
                )
            except Exception as exc:  # noqa: BLE001 - recorded, never silenced
                skipped.append(f"{GROWTH_ARM}:{case}:{type(exc).__name__}:{exc}")

    for path in osm_paths:
        case = path.name
        try:
            scores.append(score_street_morphology(_osm_topology(path), arm="osm", case=case))
        except Exception as exc:  # noqa: BLE001 - recorded, never silenced
            skipped.append(f"osm:{case}:{type(exc).__name__}:{exc}")

    return tuple(scores), tuple(skipped)


def _growth_topology(*, style_id: str, seed: int):
    """Grow a network over the accepted terrain fields and compile it."""

    from metroflow.city.growth_fabric import compile_grown_network, grow_street_network
    from metroflow.city.terrain_field import build_terrain_field
    from metroflow.city.urban_form import build_urban_form_field

    terrain = build_terrain_field(width=6000, height=6000, seed=seed, style_id=style_id)
    urban_form = build_urban_form_field(terrain=terrain, style_id=style_id, seed=seed)
    network = grow_street_network(terrain=terrain, urban_form=urban_form, seed=seed)
    return compile_grown_network(network.streets)


def _osm_topology(path: Path):
    """Load an offline OSM extract as the positive control arm.

    Reads local bytes only; `osm_import` performs no network access.
    """

    from metroflow.city.generated_map import PreviewCityTopology
    from metroflow.map.osm_import import OSMImportConfig, import_osm_xml_file

    result = import_osm_xml_file(
        path,
        config=OSMImportConfig(lane_tagging_policy="osm_wiki"),
    )
    return PreviewCityTopology(
        nodes=result.nodes,
        links=result.links,
        road_geometry=result.road_geometry,
        road_sections=result.road_sections,
        metadata={
            "source": "osm",
            "source_name": path.name,
            "source_sha256": result.metadata["source_sha256"],
            "lane_interpretation_counts": result.metadata["lane_interpretation_counts"],
        },
    )


def render_markdown(table: MorphologyControlTable, skipped: tuple[str, ...]) -> str:
    header = ["arm", "cases", "all-7 pass"] + list(EMPIRICAL_MORPHOLOGY_METRICS)
    lines = [
        "# Morphology Control Table",
        "",
        f"Fingerprint: `{table.fingerprint}`",
        "",
        "One pinned envelope applied to every arm. Metrics are measured on the",
        "OSMnx-equivalent simplified graph, because the reference corpus reports",
        "values after degree-2 interstitial nodes are contracted.",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "|".join(["---"] * len(header)) + "|",
    ]
    for summary in table.summaries:
        cells = [summary.arm, str(summary.case_count), str(summary.passed_case_count)]
        cells += [
            f"{summary.metric_pass_counts[metric]}/{summary.case_count}"
            for metric in EMPIRICAL_MORPHOLOGY_METRICS
        ]
        lines.append("| " + " | ".join(cells) + " |")

    lines += ["", "## Instrument limits", ""]
    for envelope in table.envelopes:
        diagnostics = envelope.diagnostics()
        flags = [
            name
            for name, active in (
                ("lower_bound_inert", diagnostics["lower_bound_is_inert"]),
                ("upper_bound_inert", diagnostics["upper_bound_is_inert"]),
                ("VACUOUS", diagnostics["is_vacuous"]),
            )
            if active
        ]
        lines.append(
            f"- `{envelope.metric}` bounds `[{envelope.lower:.4f}, {envelope.upper:.4f}]`"
            + (f" - {', '.join(flags)}" if flags else "")
        )

    if skipped:
        lines += ["", "## Skipped cases", ""]
        lines += [f"- `{item}`" for item in skipped]

    lines += [
        "",
        "## Claim boundary",
        "",
        "Diagnostic street-morphology comparison against a pinned reference",
        "corpus. Not empirical traffic, demand, route-choice, land-use or",
        "named-city validation. Passing this table authorizes no runtime default",
        "change on its own.",
        "",
    ]
    return "\n".join(lines)


def write_artifacts(
    artifact_prefix: str | Path,
    *,
    table: MorphologyControlTable,
    skipped: tuple[str, ...],
) -> tuple[Path, ...]:
    prefix = Path(artifact_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(table.as_dict())
    payload["skipped_cases"] = list(skipped)

    json_path = prefix.with_suffix(".json")
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path = prefix.with_suffix(".md")
    markdown_path.write_text(render_markdown(table, skipped), encoding="utf-8")

    written = (json_path, markdown_path)
    manifest_path = prefix.with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(
            {
                "fingerprint": table.fingerprint,
                "schema_version": table.schema_version,
                "files": {
                    item.name: hashlib.sha256(item.read_bytes()).hexdigest()
                    for item in written
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return written + (manifest_path,)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-prefix", required=True)
    parser.add_argument("--seeds", default=",".join(str(item) for item in CONTROL_TABLE_SEEDS))
    parser.add_argument("--styles", default=",".join(CONTROL_TABLE_STYLES))
    parser.add_argument(
        "--osm-extract",
        action="append",
        default=[],
        help="Path to an offline OSM XML extract to score as the positive control.",
    )
    args = parser.parse_args(argv)

    scores, skipped = collect_scores(
        styles=tuple(item.strip() for item in args.styles.split(",") if item.strip()),
        seeds=tuple(int(item) for item in args.seeds.split(",") if item.strip()),
        osm_paths=tuple(Path(item) for item in args.osm_extract),
    )
    table = build_morphology_control_table(scores)
    for path in write_artifacts(args.artifact_prefix, table=table, skipped=skipped):
        print(path)
    print(render_markdown(table, skipped))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
