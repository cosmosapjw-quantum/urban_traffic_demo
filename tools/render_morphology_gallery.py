"""Tool to render SVG and PNG sample maps for all 6 morphology styles.

Uses exclusively ``build_scalable_city_map`` from ``scalable_city.py`` and direct
self-contained SVG generation without intermediate HTML wrapper boilerplate.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from metroflow.city.scale import CityScaleSpec
from metroflow.city.scalable_city import build_scalable_city_map
from metroflow.ui.static_map import (
    build_static_city_map_artifact,
    render_static_city_map_svg,
)
from metroflow.sim.state import SimulationState, SimulationStaticRefs

_DEFAULT_OUT = Path(__file__).resolve().parent.parent / "artifacts" / "sample_city_maps"
_GALLERY_SCALE_SPEC = CityScaleSpec(target_population=100_000, urbanized_area_km2=25.0)

MORPHOLOGY_GALLERY_SET: tuple[tuple[str, int, str], ...] = (
    ("grid_core", 17, "Grid Core (Standard Uniform Lattice)"),
    ("ring_radial", 17, "Ring Radial (Concentric Rings & Radial Spines)"),
    ("river_constrained", 17, "River Constrained (Bifurcated Corridor & Bridges)"),
    ("polycentric_tod", 17, "Polycentric TOD (Multi-Hub Centers)"),
    ("superblock_mixed", 17, "Superblock Mixed (Hierarchical Arterial Perimeter)"),
    ("organic", 17, "Organic Fabric (Irregular Local Network)"),
)


@dataclass(frozen=True)
class _GalleryConfig:
    """Config protocol-compatible object for build_scalable_city_map."""

    topology_mode: str = "scalable_synthetic_v2"
    morphology_style_id: str = "grid_core"
    zone_poi_coupling_mode: str = "block_based_v1"
    scale_spec: CityScaleSpec | None = _GALLERY_SCALE_SPEC


def render_all_sample_maps(out_dir: Path, generate_png: bool = True) -> None:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_entries: list[dict[str, str]] = []

    # Clean up legacy/unnecessary HTML files if present
    for html_file in out_dir.glob("map_*.html"):
        html_file.unlink(missing_ok=True)

    for style_id, seed, label in MORPHOLOGY_GALLERY_SET:
        print(f"Generating {style_id} (seed {seed})...")
        cfg = _GalleryConfig(morphology_style_id=style_id)

        # Provenance gate: assert we are calling the scalable pipeline
        assert cfg.topology_mode == "scalable_synthetic_v2"

        city = build_scalable_city_map(
            cfg,
            scenario_id=f"{style_id}_s{seed}",
            seed=seed,
        )
        static_refs = SimulationStaticRefs(
            scenario_id=f"{style_id}_s{seed}",
            city_topology=city.topology,
            zones=city.zoning.zones,
            pois=city.zoning.pois,
            metadata={"label": label},
        )
        sim_state = SimulationState(static=static_refs)
        artifact = build_static_city_map_artifact(sim_state)
        svg = render_static_city_map_svg(artifact)
        svg_sha256 = hashlib.sha256(svg.encode("utf-8")).hexdigest()

        svg_path = out_dir / f"map_{style_id}.svg"
        svg_path.write_text(svg, encoding="utf-8")

        entry = {
            "style_id": style_id,
            "seed": str(seed),
            "topology_mode": "scalable_synthetic_v2",
            "target_population": str(_GALLERY_SCALE_SPEC.target_population),
            "urbanized_area_km2": str(_GALLERY_SCALE_SPEC.urbanized_area_km2),
            "network_schema_version": city.network.schema_version,
            "network_fingerprint": city.network.fingerprint,
            "blocks_schema_version": city.blocks.schema_version,
            "blocks_fingerprint": city.blocks.fingerprint,
            "compiled_schema_version": city.compiled.schema_version,
            "compiled_fingerprint": city.compiled.fingerprint,
            "static_authority_schema_version": city.static_authority.schema_version,
            "static_authority_fingerprint": city.static_authority.fingerprint,
            "zoning_placement_fingerprint": city.zoning.metadata.get(
                "zoning_placement_fingerprint", ""
            ),
            "city_map_fingerprint": city.fingerprint,
            "svg_sha256": svg_sha256,
            "node_count": str(len(city.topology.nodes)),
            "link_count": str(len(city.topology.links)),
        }
        manifest_entries.append(entry)

        png_path = out_dir / f"map_{style_id}.png"
        if generate_png:
            png_path.unlink(missing_ok=True)
            subprocess.run(
                [
                    "google-chrome",
                    "--headless",
                    "--disable-gpu",
                    f"--screenshot={str(png_path)}",
                    "--window-size=1400,1050",
                    svg_path.as_uri(),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if not png_path.is_file() or png_path.stat().st_size == 0:
                png_path.unlink(missing_ok=True)
                raise RuntimeError(
                    f"Chrome did not produce a fresh non-empty PNG: {png_path}"
                )
            entry["png_sha256"] = hashlib.sha256(png_path.read_bytes()).hexdigest()
            print(f"  -> Saved {svg_path.name} and {png_path.name}")
        else:
            entry["png_provenance"] = "not_rendered_svg_only"
            print(f"  -> Saved {svg_path.name}")

    # Write provenance manifest
    manifest_path = out_dir / "gallery_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_entries, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote gallery manifest: {manifest_path}")


def check_gallery_artifacts(out_dir: Path) -> bool:
    out_dir = out_dir.resolve()
    manifest_path = out_dir / "gallery_manifest.json"
    if not manifest_path.exists():
        print(f"Manifest not found: {manifest_path}", file=sys.stderr)
        return False

    entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry_by_style = {e["style_id"]: e for e in entries}

    for style_id, seed, description in MORPHOLOGY_GALLERY_SET:
        if style_id not in entry_by_style:
            print(f"Missing manifest entry for {style_id}", file=sys.stderr)
            return False
        committed_entry = entry_by_style[style_id]
        svg_path = out_dir / f"map_{style_id}.svg"
        if not svg_path.exists():
            print(f"Missing SVG artifact: {svg_path}", file=sys.stderr)
            return False

        # Re-derive from source code
        config = _GalleryConfig(morphology_style_id=style_id)
        city_map = build_scalable_city_map(config, scenario_id=f"{style_id}_s{seed}", seed=seed)
        static_refs = SimulationStaticRefs(
            scenario_id=f"{style_id}_s{seed}",
            city_topology=city_map.topology,
            zones=city_map.zoning.zones,
            pois=city_map.zoning.pois,
            metadata={"label": description},
        )
        sim_state = SimulationState(static=static_refs)
        artifact = build_static_city_map_artifact(sim_state)
        rederived_svg = render_static_city_map_svg(artifact)
        rederived_sha = hashlib.sha256(rederived_svg.encode("utf-8")).hexdigest()

        committed_svg = svg_path.read_text(encoding="utf-8")
        committed_sha = hashlib.sha256(committed_svg.encode("utf-8")).hexdigest()

        if committed_sha != committed_entry.get("svg_sha256"):
            print(
                f"Committed SVG digest mismatch for {style_id}: {committed_sha} != {committed_entry.get('svg_sha256')}",
                file=sys.stderr,
            )
            return False

        if rederived_sha != committed_sha:
            print(
                f"Source drift detected for {style_id}: rederived SVG digest {rederived_sha} != committed digest {committed_sha}",
                file=sys.stderr,
            )
            return False

        if rederived_svg != committed_svg:
            print(
                f"Source drift detected for {style_id}: rederived SVG content does not match committed SVG bytes exactly",
                file=sys.stderr,
            )
            return False

        if city_map.fingerprint != committed_entry.get("city_map_fingerprint"):
            print(
                f"City map fingerprint drift for {style_id}: {city_map.fingerprint} != {committed_entry.get('city_map_fingerprint')}",
                file=sys.stderr,
            )
            return False

        expected_png_sha = committed_entry.get("png_sha256")
        if expected_png_sha is not None:
            png_path = out_dir / f"map_{style_id}.png"
            if not png_path.exists():
                print(f"Missing PNG artifact: {png_path}", file=sys.stderr)
                return False
            actual_png_sha = hashlib.sha256(png_path.read_bytes()).hexdigest()
            if actual_png_sha != expected_png_sha:
                print(
                    f"Committed PNG digest mismatch for {style_id}: "
                    f"{actual_png_sha} != {expected_png_sha}",
                    file=sys.stderr,
                )
                return False

    print("Gallery check passed: all 6 morphology maps re-derived and verified byte-identical.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Render morphology sample maps")
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT, help="Output directory")
    parser.add_argument("--svg-only", action="store_true", help="Skip PNG screenshot generation")
    parser.add_argument("--check", action="store_true", help="Check existing gallery artifacts against manifest")
    args = parser.parse_args()

    if args.check:
        return 0 if check_gallery_artifacts(args.out) else 1

    render_all_sample_maps(args.out, generate_png=not args.svg_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
