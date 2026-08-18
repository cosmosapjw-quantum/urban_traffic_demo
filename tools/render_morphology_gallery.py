"""Render the 6 urban morphology archetypes to static HTML/SVG and PNG map artifacts.

Uses the scalable_synthetic_v2 pipeline exclusively.  The previous version
incorrectly called the realistic_synthetic_v1 generator, producing
provenance-invalid gallery images.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from metroflow.city.scale import CityScaleSpec
from metroflow.city.scalable_city import build_scalable_city_map
from metroflow.sim.state import SimulationState, SimulationStaticRefs
from metroflow.ui.static_map import build_static_city_map_artifact, render_static_city_map_html

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_OUT = _REPO_ROOT / "artifacts" / "sample_city_maps"

# Default scale for gallery: 100k population, 25 km² urbanized area
_GALLERY_SCALE_SPEC = CityScaleSpec(100_000, 25.0)

MORPHOLOGY_GALLERY_SET = (
    ("grid_core", 17, "Grid Core (Dense Orthogonal Grid)"),
    ("ring_radial", 17, "Ring Radial (Concentric Arterials & Radial Spines)"),
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
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_entries: list[dict[str, str]] = []

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
        html = render_static_city_map_html(artifact)

        html_path = out_dir / f"map_{style_id}.html"
        html_path.write_text(html, encoding="utf-8")

        entry = {
            "style_id": style_id,
            "seed": str(seed),
            "topology_mode": "scalable_synthetic_v2",
            "network_fingerprint": city.network.fingerprint,
            "blocks_fingerprint": city.blocks.fingerprint,
            "compiled_fingerprint": city.compiled.fingerprint,
            "static_authority_fingerprint": city.static_authority.fingerprint,
            "node_count": str(len(city.topology.nodes)),
            "link_count": str(len(city.topology.links)),
        }
        manifest_entries.append(entry)

        if generate_png:
            png_path = out_dir / f"map_{style_id}.png"
            subprocess.run(
                [
                    "google-chrome",
                    "--headless",
                    "--disable-gpu",
                    f"--screenshot={str(png_path)}",
                    "--window-size=1400,1050",
                    f"file://{str(html_path)}",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"  -> Saved {html_path.name} and {png_path.name}")
        else:
            print(f"  -> Saved {html_path.name}")

    # Write provenance manifest
    manifest_path = out_dir / "gallery_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_entries, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote gallery manifest: {manifest_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render morphology sample maps")
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT, help="Output directory")
    parser.add_argument("--html-only", action="store_true", help="Skip PNG screenshot generation")
    args = parser.parse_args()

    render_all_sample_maps(args.out, generate_png=not args.html_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
