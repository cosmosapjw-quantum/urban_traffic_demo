"""Render the 6 urban morphology archetypes to static HTML/SVG and PNG map artifacts."""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path

from metroflow.city.realistic_city import generate_city_map
from metroflow.sim.state import SimulationState, SimulationStaticRefs
from metroflow.ui.static_map import build_static_city_map_artifact, render_static_city_map_html

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_OUT = _REPO_ROOT / "artifacts" / "sample_city_maps"

MORPHOLOGY_GALLERY_SET = (
    ("grid_core", 17, "Gridiron Core (Dense Orthogonal Manhattan Grid)"),
    ("ring_radial", 17, "Ring Radial (Concentric Arterials & Radial Spines)"),
    ("river_constrained", 17, "River Constrained (Bifurcated Corridor & Bridges)"),
    ("polycentric_tod", 17, "Polycentric TOD (Multi-Hub Transit Centers)"),
    ("superblock_mixed", 17, "Superblock Mixed (Hierarchical Arterial Perimeter)"),
    ("organic", 17, "Organic Fabric (Curvilinear Historical Network)"),
)


@dataclass(frozen=True)
class Config:
    topology_mode: str = "realistic_synthetic_v1"
    morphology_style_id: str = "grid_core"
    zone_poi_coupling_mode: str = "block_based_v1"


def render_all_sample_maps(out_dir: Path, generate_png: bool = True) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    for style_id, seed, label in MORPHOLOGY_GALLERY_SET:
        print(f"Generating {style_id} (seed {seed})...")
        cfg = Config(morphology_style_id=style_id)
        city = generate_city_map(cfg, scenario_id=f"{style_id}_s{seed}", seed=seed)
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Render morphology sample maps")
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT, help="Output directory")
    parser.add_argument("--html-only", action="store_true", help="Skip PNG screenshot generation")
    args = parser.parse_args()

    render_all_sample_maps(args.out, generate_png=not args.html_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
