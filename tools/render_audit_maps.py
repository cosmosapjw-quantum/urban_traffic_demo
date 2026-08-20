"""Render the audited topologies as SVG, captioned with their audited numbers.

These are navigation aids for a reviewer. They are **not** evidence: the claim
ledger forbids presenting image artifacts as scientific validation, and nothing
here measures anything. Every number printed on a map is read back from the
committed control-table artifact, so a render can never disagree with the table
it illustrates -- and a case the table does not contain refuses to render rather
than appear with no provenance.

SVG rather than a screenshot, for three reasons: it needs no browser and no
plotting dependency, so CI and a reviewer can regenerate it from source; it is
text, so a diff shows which segments moved; and it is byte-deterministic, so a
rerun that changes nothing changes nothing.

The set spans arms deliberately. Showing only `growth_fabric_v1` would make the
gallery an argument; the runtime default and the rejected synthetic arm are
included so a reviewer can see what the envelope's failures look like.

Usage::

    .venv/bin/python tools/render_audit_maps.py --out artifacts/external_audit_2_maps
    .venv/bin/python tools/render_audit_maps.py --check   # bytes still reproduce
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONTROL_TABLE = (
    _REPO_ROOT
    / "artifacts"
    / "runtime_spine_review"
    / "morphology-control-table-v4-20260820.json"
)
_DEFAULT_OUT = _REPO_ROOT / "artifacts" / "external_audit_2_maps"

CANVAS_W = 1400.0
CANVAS_H = 1000.0
MARGIN = 28.0
CAPTION_H = 168.0

# Road classes drawn thicker, so a reviewer can see the hierarchy the generator
# claims to build rather than a uniform mat of lines.
_CLASS_STYLE: dict[str, tuple[float, str]] = {
    "expressway": (2.6, "#1b3a5c"),
    "arterial": (1.9, "#2f6690"),
    "collector": (1.2, "#4f9ac4"),
    "local": (0.6, "#9dc3d9"),
}
_FALLBACK_STYLE = (0.9, "#7a7a7a")


@dataclass(frozen=True)
class RenderCase:
    arm: str
    style_id: str
    seed: int
    note: str

    @property
    def case(self) -> str:
        # The OSM arm is keyed by fixture filename, not style/seed: there is no
        # seed to vary when the input is a city that already exists.
        if self.arm == "osm":
            return self.style_id
        return f"{self.style_id}/{self.seed}"

    @property
    def slug(self) -> str:
        if self.arm == "osm":
            return f"osm--{self.style_id.removesuffix('.osm')}"
        return f"{self.arm}--{self.style_id}--s{self.seed}"


# `growth_fabric_v1` is the arm under review, at every style on one seed plus two
# extra seeds on one style to show seed spread. `standard` is the runtime default
# and `realistic_synthetic_v1` the arm the envelope rejects outright; both are
# here so the gallery shows failure as well as success.
# Seeds are the control table's own (17, 29, 41, 44, 53) and the styles are the
# ones each arm was actually scored on -- `standard` was never run on grid_core,
# so asking for it would raise rather than render.
RENDER_SET: tuple[RenderCase, ...] = (
    RenderCase("growth_fabric_v1", "grid_core", 17, "arm under review"),
    RenderCase("growth_fabric_v1", "polycentric_tod", 17, "arm under review"),
    RenderCase("growth_fabric_v1", "ring_radial", 17, "arm under review"),
    RenderCase("growth_fabric_v1", "river_constrained", 17, "arm under review"),
    RenderCase("growth_fabric_v1", "organic", 17, "arm under review"),
    RenderCase("growth_fabric_v1", "superblock_mixed", 17, "arm under review"),
    RenderCase("growth_fabric_v1", "grid_core", 29, "seed spread"),
    RenderCase("growth_fabric_v1", "grid_core", 53, "seed spread"),
    RenderCase("standard", "polycentric_tod", 17, "runtime default"),
    RenderCase("standard", "ring_radial", 17, "runtime default"),
    RenderCase("realistic_synthetic_v1", "grid_core", 17, "rejected arm"),
    RenderCase("realistic_synthetic_v1", "polycentric_tod", 17, "rejected arm"),
    RenderCase("sidecar_local_fabric", "grid_core", 17, "partial arm"),
    # Cited by docs/harness/EXTERNAL_AUDIT_PROMPT.md as the counter-example: an
    # arm that passes all seven metrics and is plainly not a city. Rendered here
    # so that argument stays reproducible after the old PNG was removed.
    RenderCase(
        "sidecar_local_fabric", "superblock_mixed", 17, "metric counter-example"
    ),
    # The positive control. Real cities through the same renderer and the same
    # caption format is the only way a reviewer can judge the generated maps
    # against something that is not us.
    RenderCase("osm", "barcelona.osm", 0, "OSM control"),
    RenderCase("osm", "chicago.osm", 0, "OSM control"),
    RenderCase("osm", "charlotte.osm", 0, "OSM control"),
)


def load_scores(path: Path | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    """Index the committed control table by (arm, case).

    Read, never recomputed. A caption measured at render time could disagree
    with the table while looking just as authoritative.
    """

    payload = json.loads((path or _CONTROL_TABLE).read_text(encoding="utf-8"))
    return {(record["arm"], record["case"]): record for record in payload["scores"]}


def caption_for(
    scores: dict[tuple[str, str], dict[str, Any]], *, arm: str, case: str
) -> tuple[str, ...]:
    """Build the caption, or raise saying which case is missing.

    KeyError rather than a blank caption: a map with no provenance is the thing
    that lets a reader attach it to whichever claim they had in mind.
    """

    record = scores[(arm, case)]
    metrics = record["metrics"]
    verdict = "PASS 7/7" if record["passed"] else (
        "FAIL: " + ", ".join(record["failed_metrics"])
    )
    return (
        f"{arm}  |  {case}  |  {verdict}",
        (
            f"nodes {record['node_count']}   segments {record['physical_segment_count']}   "
            f"mean degree {metrics['mean_node_degree']:.4f}   "
            f"dead ends {metrics['dead_end_share']:.4f}"
        ),
        (
            f"circuity {metrics['circuity']:.4f}   "
            f"median segment {metrics['median_segment_length_m']:.1f} m   "
            f"four-way {metrics['four_way_share']:.4f}"
        ),
        (
            f"orientation entropy {metrics['orientation_entropy']:.4f}   "
            f"order {metrics['orientation_order']:.4f}"
        ),
        "measured values read from morphology-control-table-v4-20260820.json; "
        "this image measures nothing",
    )


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _style_for(link: Any) -> tuple[float, str]:
    road_class = getattr(link, "road_class", None)
    name = getattr(road_class, "value", road_class)
    return _CLASS_STYLE.get(str(name).lower(), _FALLBACK_STYLE)


def render_svg(
    *,
    nodes: Sequence[Any],
    links: Sequence[Any],
    title: str,
    caption_lines: Sequence[str],
) -> str:
    """Draw every link, fitted to the canvas, with the caption beneath.

    Every link is drawn, including zero-length ones. Skipping degenerate
    geometry would hide duplicated node pairs at the exact moment somebody is
    looking for duplicated node pairs.
    """

    xy = {int(node.node_id): (float(node.x), float(node.y)) for node in nodes}
    xs = [point[0] for point in xy.values()] or [0.0]
    ys = [point[1] for point in xy.values()] or [0.0]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    span_x = max(max_x - min_x, 1e-9)
    span_y = max(max_y - min_y, 1e-9)
    plot_w = CANVAS_W - 2 * MARGIN
    plot_h = CANVAS_H - CAPTION_H - 2 * MARGIN
    scale = min(plot_w / span_x, plot_h / span_y)
    off_x = MARGIN + (plot_w - span_x * scale) / 2.0
    off_y = MARGIN + (plot_h - span_y * scale) / 2.0

    def project(point: tuple[float, float]) -> tuple[float, float]:
        # y is flipped: SVG grows downward, the generator's plane grows upward.
        return (
            off_x + (point[0] - min_x) * scale,
            off_y + (max_y - point[1]) * scale,
        )

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CANVAS_W:.0f} '
        f'{CANVAS_H:.0f}" width="{CANVAS_W:.0f}" height="{CANVAS_H:.0f}">',
        f'<rect width="{CANVAS_W:.0f}" height="{CANVAS_H:.0f}" fill="#ffffff"/>',
        f'<title>{_escape(title)}</title>',
        '<g stroke-linecap="round">',
    ]
    for link in links:
        src = xy.get(int(link.src_node_id))
        dst = xy.get(int(link.dst_node_id))
        if src is None or dst is None:
            raise KeyError(
                f"link {getattr(link, 'link_id', '?')} names a node that is not in "
                "the node set; refusing to draw a graph the topology does not have"
            )
        x1, y1 = project(src)
        x2, y2 = project(dst)
        width, colour = _style_for(link)
        parts.append(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{colour}" stroke-width="{width}"/>'
        )
    parts.append("</g>")

    text_y = CANVAS_H - CAPTION_H + 26.0
    parts.append(
        f'<text x="{MARGIN:.0f}" y="{text_y:.0f}" font-family="monospace" '
        f'font-size="17" fill="#111111">{_escape(title)}</text>'
    )
    for index, line in enumerate(caption_lines):
        parts.append(
            f'<text x="{MARGIN:.0f}" y="{text_y + 22.0 * (index + 1):.0f}" '
            f'font-family="monospace" font-size="13" fill="#333333">'
            f"{_escape(line)}</text>"
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def verify_topology_record_integrity(
    topology: Any,
    record: dict[str, Any],
    *,
    arm: str,
    case: str,
) -> None:
    """Verify that current generated topology matches the audited record identity."""
    from metroflow.city.morphology_control_table import source_topology_fingerprint

    if len(topology.nodes) != record["node_count"]:
        raise ValueError(
            f"topology record identity mismatch for {arm} {case}: "
            f"current topology node count ({len(topology.nodes)}) != recorded ({record['node_count']})"
        )
    recorded_fingerprint = record.get("source_topology_fingerprint")
    if not isinstance(recorded_fingerprint, str):
        raise ValueError(
            f"topology record identity mismatch for {arm} {case}: "
            "record has no source_topology_fingerprint"
        )
    current_fingerprint = source_topology_fingerprint(topology)
    if current_fingerprint != recorded_fingerprint:
        raise ValueError(
            f"topology record identity mismatch for {arm} {case}: "
            f"current source topology fingerprint ({current_fingerprint}) != "
            f"recorded ({recorded_fingerprint})"
        )


def render_case(case: RenderCase, scores: dict[tuple[str, str], dict[str, Any]]) -> str:
    from metroflow.benchmarks.morphology_control_table import (
        build_arm_topology,
        build_osm_topology,
    )

    if (case.arm, case.case) not in scores:
        raise KeyError(f"no recorded scores for {case.arm} {case.case}")
    record = scores[(case.arm, case.case)]

    if case.arm == "osm":
        topology = build_osm_topology(_REPO_ROOT / "artifacts" / "osm_control" / case.style_id)
        title = f"osm / {case.style_id} -- {case.note}"
    else:
        topology = build_arm_topology(arm=case.arm, style_id=case.style_id, seed=case.seed)
        title = f"{case.arm} / {case.style_id} / seed {case.seed} -- {case.note}"

    verify_topology_record_integrity(topology, record, arm=case.arm, case=case.case)
    caption = caption_for(scores, arm=case.arm, case=case.case)
    return render_svg(
        nodes=topology.nodes,
        links=topology.links,
        title=title,
        caption_lines=caption,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(_DEFAULT_OUT))
    parser.add_argument(
        "--check",
        action="store_true",
        help="re-render and compare against what is committed, writing nothing",
    )
    args = parser.parse_args(argv)

    out = Path(args.out).resolve()
    scores = load_scores()
    mismatches: list[str] = []

    if not args.check:
        out.mkdir(parents=True, exist_ok=True)

    for case in RENDER_SET:
        svg = render_case(case, scores)
        path = out / f"{case.slug}.svg"
        if args.check:
            if not path.exists():
                mismatches.append(f"{path.name}: missing")
            elif path.read_text(encoding="utf-8") != svg:
                mismatches.append(f"{path.name}: bytes changed")
        else:
            path.write_text(svg, encoding="utf-8")
            print(f"wrote {path.relative_to(_REPO_ROOT)}")

    if args.check:
        for problem in mismatches:
            print(f"MISMATCH {problem}")
        if mismatches:
            print(f"{len(mismatches)} render(s) do not reproduce")
            return 1
        print(f"all {len(RENDER_SET)} renders reproduce byte-for-byte")
    return 0


if __name__ == "__main__":
    sys.exit(main())
