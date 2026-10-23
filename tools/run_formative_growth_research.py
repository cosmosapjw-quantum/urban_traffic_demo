#!/usr/bin/env python3
"""Generate and render the pure-Python formative-growth research map."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from metroflow.city.formative_growth import FormationConfig, generate_formative_city


def _svg_path(points: list[tuple[float, float]], *, close: bool = False) -> str:
    if not points:
        return ""
    commands = [f"M {points[0][0]:.3f} {points[0][1]:.3f}"]
    commands.extend(f"L {x:.3f} {y:.3f}" for x, y in points[1:])
    if close:
        commands.append("Z")
    return " ".join(commands)


def write_svg(city, path: Path, *, age_mode: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width_px = 1200
    height_px = int(round(width_px * city.height_m / city.width_m))
    sx = width_px / city.width_m
    sy = height_px / city.height_m

    def screen(x: float, y: float) -> tuple[float, float]:
        return x * sx, height_px - y * sy

    land = {
        "residential": "#d8dcc8",
        "mixed": "#d7c9b1",
        "commercial": "#d0b0a5",
        "industrial": "#c8c1bd",
        "park": "#b8d0b0",
    }
    road = {"local": "#596168", "secondary": "#39454e", "primary": "#17232b"}
    road_width = {"local": 0.75, "secondary": 1.65, "primary": 3.0}
    epoch_palette = ["#3d315b", "#5d4b8a", "#7567a5", "#4f7a9d", "#4d9b87", "#78a85a", "#c2a34f", "#d17a45"]

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_px}" height="{height_px}" viewBox="0 0 {width_px} {height_px}">',
        '<rect width="100%" height="100%" fill="#f4f1e8"/>',
    ]
    if not age_mode:
        for block in city.blocks:
            points = [screen(city.nodes[i].x_m, city.nodes[i].y_m) for i in block.node_ids]
            lines.append(
                f'<path d="{_svg_path(points, close=True)}" fill="{land.get(block.land_use, "#ddd")}" '
                'fill-opacity="0.90" stroke="#d0cabd" stroke-width="0.35"/>'
            )
    for edge in sorted(city.edges, key=lambda e: ({"local": 0, "secondary": 1, "primary": 2}[e.hierarchy], e.edge_id)):
        a = screen(city.nodes[edge.u].x_m, city.nodes[edge.u].y_m)
        b = screen(city.nodes[edge.v].x_m, city.nodes[edge.v].y_m)
        colour = epoch_palette[min(edge.birth_epoch, len(epoch_palette) - 1)] if age_mode else road[edge.hierarchy]
        width = (1.25 if age_mode else road_width[edge.hierarchy])
        lines.append(
            f'<line x1="{a[0]:.3f}" y1="{a[1]:.3f}" x2="{b[0]:.3f}" y2="{b[1]:.3f}" '
            f'stroke="{colour}" stroke-width="{width:.3f}" stroke-linecap="round"/>'
        )
    for centre in city.centres:
        x, y = screen(centre.x_m, centre.y_m)
        r = 5.5 if centre.centre_id == 0 else 4.0
        lines.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{r}" fill="#9f2f28" stroke="#fff" stroke-width="1.2"/>')
    lines.append(
        f'<text x="22" y="31" font-family="sans-serif" font-size="18" fill="#17232b">'
        f'{"Formation age" if age_mode else "Formative urban growth"} · seed {city.config.seed}</text>'
    )
    lines.append('</svg>')
    path.write_text("\n".join(lines), encoding="utf-8")


def write_png(city, path: Path, *, age_mode: bool = False) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon

    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 9), dpi=150)
    ax.set_facecolor("#f4f1e8")
    land = {
        "residential": "#d8dcc8",
        "mixed": "#d7c9b1",
        "commercial": "#d0b0a5",
        "industrial": "#c8c1bd",
        "park": "#b8d0b0",
    }
    road = {"local": "#596168", "secondary": "#39454e", "primary": "#17232b"}
    road_width = {"local": 0.45, "secondary": 1.0, "primary": 2.2}
    epoch_palette = ["#3d315b", "#5d4b8a", "#7567a5", "#4f7a9d", "#4d9b87", "#78a85a", "#c2a34f", "#d17a45"]
    if not age_mode:
        for block in city.blocks:
            pts = [(city.nodes[i].x_m, city.nodes[i].y_m) for i in block.node_ids]
            ax.add_patch(Polygon(pts, closed=True, facecolor=land.get(block.land_use, "#ddd"), edgecolor="#d0cabd", linewidth=0.25, alpha=0.9))
    for edge in sorted(city.edges, key=lambda e: ({"local": 0, "secondary": 1, "primary": 2}[e.hierarchy], e.edge_id)):
        a = city.nodes[edge.u]
        b = city.nodes[edge.v]
        colour = epoch_palette[min(edge.birth_epoch, len(epoch_palette) - 1)] if age_mode else road[edge.hierarchy]
        width = 0.8 if age_mode else road_width[edge.hierarchy]
        ax.plot([a.x_m, b.x_m], [a.y_m, b.y_m], color=colour, linewidth=width, solid_capstyle="round")
    ax.scatter([c.x_m for c in city.centres], [c.y_m for c in city.centres], s=[70 if c.centre_id == 0 else 45 for c in city.centres], c="#9f2f28", edgecolors="white", linewidths=0.8, zorder=5)
    ax.set_xlim(0, city.width_m)
    ax.set_ylim(0, city.height_m)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(("Formation age" if age_mode else "Formative urban growth") + f" · seed {city.config.seed}")
    fig.tight_layout(pad=0.5)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261023)
    parser.add_argument("--node-count", type=int, default=320)
    parser.add_argument("--area-km2", type=float, default=25.0)
    args = parser.parse_args()

    city = generate_formative_city(
        FormationConfig(seed=args.seed, node_count=args.node_count, urbanized_area_km2=args.area_km2)
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    payload_path = args.output_dir / "formative_city.json"
    payload_path.write_text(json.dumps(city.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    write_svg(city, args.output_dir / "formative_city.svg")
    write_svg(city, args.output_dir / "formative_city_age.svg", age_mode=True)
    try:
        write_png(city, args.output_dir / "formative_city.png")
        write_png(city, args.output_dir / "formative_city_age.png", age_mode=True)
    except ImportError:
        pass
    print(json.dumps({"fingerprint": city.fingerprint, "metrics": dict(city.metrics), "audit": dict(city.audit)}, indent=2, sort_keys=True))
    return 0 if city.audit["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
