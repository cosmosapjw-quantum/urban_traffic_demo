"""V02 frozen synthetic city audit; no hidden portal registration or seed search.

Each case is independently checkpointed, then rendered from its frozen JSON.
Registered access and hypothetical boundary-node access have distinct support.
"""

from dataclasses import asdict
from pathlib import Path
import argparse
import csv
from collections import Counter
import gzip
import lzma
import hashlib
import json
import math
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from metroflow.terrain_city.network import generate, STYLES  # noqa: E402
from metroflow.terrain_city.area_access import AreaAccess, Portal  # noqa: E402
from metroflow.v1.city import load_city  # noqa: E402

PRIMARY = (
    ("planned_plain", "planned", "flat"),
    ("polycentric_river", "polycentric", "river"),
    ("radial_plain", "radial", "flat"),
    ("coastal_port", "polycentric", "coast"),
    ("valley_city", "corridor", "valley"),
    ("lake_city", "polycentric", "lake"),
)
SEEDS = (7, 17, 41)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_frozen(path):
    raw = Path(path).read_bytes()
    return json.loads(gzip.decompress(raw) if str(path).endswith(".gz") else lzma.decompress(raw))


def audit_city(city):
    nodes = {n.id: n for n in city.roadmap.nodes}
    degree = Counter()
    detours = []
    for section in city.roadmap.sections:
        degree[section.start] += 1
        degree[section.end] += 1
        direct = math.dist(nodes[section.start].xyz, nodes[section.end].xyz)
        if direct:
            detours.append(section.length_m / direct)
    registered = {p.block_id for p in city.portals}
    served = sum(b.residents for b in city.face_graph.blocks if b.id in registered)
    # Explicit counterfactual boundary-node doors: never relabel these registered.
    samples = []
    for block in city.face_graph.blocks:
        if not block.residents:
            continue
        polygon = tuple(nodes[k].xyz[:2] for k in block.boundary)
        area = AreaAccess(polygon)
        doors = tuple(Portal(k, nodes[k].xyz[:2]) for k in block.boundary)
        for xy, weight, _ in area.quadrature(0):
            cost, _ = area.portal_costs(xy, doors, 1.4)
            samples.append((cost, weight * block.residents))
    total = sum(b.residents for b in city.face_graph.blocks)
    thresholds = (30, 60, 120, 300, 600)
    cdf = [
        [x, math.fsum(w for t, w in samples if t <= x) / total if total else 0] for x in thresholds
    ]
    report = city.report()
    return dict(
        **report,
        geometry_flags=[],
        geometry_flags_basis="canonical compile_city centreline/mask/layer validation; no pavement certification",
        registered_portal_count=len(city.portals),
        registered_served_residents=served,
        registered_unserved_residents=total - served,
        registered_access_cdf=None,
        registered_access_status="UNSUPPORTED_NO_REGISTERED_PORTALS"
        if not city.portals
        else "NOT_RUN",
        declared_boundary_access_cdf=cdf,
        declared_boundary_access_scope="depth0 uniform-area quadrature; all boundary nodes as hypothetical doors; not registered service; no quantile certificate",
        declared_boundary_access_mass=math.fsum(w for _, w in samples),
        degree_histogram={str(k): v for k, v in sorted(Counter(degree.values()).items())},
        block_area_range_m2=[
            min((b.area_m2 for b in city.face_graph.blocks), default=0),
            max((b.area_m2 for b in city.face_graph.blocks), default=0),
        ],
        mean_block_compactness=math.fsum(
            4 * math.pi * b.area_m2 / b.perimeter_m**2 for b in city.face_graph.blocks
        )
        / max(1, len(city.face_graph.blocks)),
        mean_section_detour=math.fsum(detours) / max(1, len(detours)),
    )


def render_svg(data, label, source_sha):
    """Project the exact frozen JSON into SVG; rounding is display-only in metres."""
    size = data["landscape"]["terrain"]["n"] * data["landscape"]["terrain"]["spacing_m"]
    scale = 800 / size

    def point(p):
        return f"{20 + p[0] * scale:.2f},{840 - p[1] * scale:.2f}"

    rows = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="840" height="900" viewBox="0 0 840 900">',
        '<rect width="840" height="900" fill="white"/>',
        f"<metadata>frozen_json_archive_sha256:{source_sha}</metadata>",
        f'<text x="20" y="20" font-size="15">{label}</text>',
    ]
    for kind, color in [("water", "#b7ddeb"), ("protected", "#deebc7")]:
        for p in data["landscape"][kind]:
            rows.append(
                f'<polygon points="{" ".join(point(x) for x in p["points"])}" fill="{color}"/>'
            )
    nodes = {n["id"]: n for n in data["roadmap"]["nodes"]}
    for b in data["blocks"]:
        rows.append(
            f'<polygon points="{" ".join(point(nodes[k]["xyz"]) for k in b["boundary"])}" fill="#f4eee4" stroke="#dbd2c3" stroke-width=".25"/>'
        )
    for section in sorted(data["roadmap"]["sections"], key=lambda s: s["facility"] != "surface"):
        color = "#b54329" if section["facility"] != "surface" else "#525b69"
        width = "1.8" if section["facility"] != "surface" else ".65"
        rows.append(
            f'<polyline points="{" ".join(point(x) for x in section["points"])}" fill="none" stroke="{color}" stroke-width="{width}"/>'
        )
    rows += [
        '<text x="20" y="865" font-size="12">red: bridge/elevated; blue: water; green: protected</text>',
        f'<text x="20" y="885" font-size="12">registered portals={len(data["portals"])}; unserved stock retained</text>',
        "</svg>",
    ]
    return "\n".join(rows) + "\n"


def render_gallery(cases, output):
    """Optional Pillow diagnostic from the same frozen JSON, six representative views."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (1500, 1080), "white")
    draw = ImageDraw.Draw(image)
    for index, row in enumerate(cases):
        x0, y0 = (index % 3) * 500, (index // 3) * 540
        data = read_frozen(output / row["source"])
        size = data["landscape"]["terrain"]["n"] * data["landscape"]["terrain"]["spacing_m"]

        def xy(p):
            return x0 + 10 + p[0] * 480 / size, y0 + 510 - p[1] * 480 / size

        draw.text((x0 + 10, y0 + 5), row["case"] + " seed=" + str(row["seed"]), fill="black")
        for kind, color in [("water", "#b7ddeb"), ("protected", "#deebc7")]:
            for p in data["landscape"][kind]:
                draw.polygon([xy(p) for p in p["points"]], fill=color)
        for section in sorted(
            data["roadmap"]["sections"], key=lambda s: s["facility"] != "surface"
        ):
            draw.line(
                [xy(p) for p in section["points"]],
                fill="#b54329" if section["facility"] != "surface" else "#525b69",
                width=2 if section["facility"] != "surface" else 1,
            )
        draw.text(
            (x0 + 10, y0 + 520),
            "registered portals=" + str(len(data["portals"])) + "; stock retained",
            fill="black",
        )
    image.save(output / "REPRESENTATIVE_SIX.png")


def audit_case(output, case, style, terrain, seed, family, resolution=42):
    slug = f"{family}_{case}_s{seed}"
    source = output / (slug + ".json.xz")
    rowfile = output / (slug + ".audit.json")
    if rowfile.exists() and source.exists():
        row = json.loads(rowfile.read_text())
        if row["source_sha256"] == sha(source):
            if not (output / row["svg"]).is_file() or sha(output / row["svg"]) != row["svg_sha256"]:
                raise ValueError("frozen renderer changed or missing; preserve evidence")
            return row
        raise ValueError("frozen source changed; no silent overwrite")
    start = time.monotonic()
    if source.exists():
        data = read_frozen(source)
        city = load_city(data)
    else:
        atlas = generate(style, terrain, 8000.0, resolution, seed)
        city = load_city(json.loads(json.dumps(asdict(atlas), allow_nan=False)))
        data = city.to_dict()
        source.write_bytes(
            lzma.compress(
                json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(),
                preset=6,
            )
        )
    # Rebuild validator from the exact frozen JSON, not the in-memory generator.
    city = load_city(read_frozen(source))
    row = dict(
        case=case,
        style=style,
        terrain=terrain,
        seed=seed,
        family=family,
        resolution=resolution,
        source=source.name,
        source_sha256=sha(source),
        **audit_city(city),
    )
    svg = output / (slug + ".svg.xz")
    svg.write_bytes(
        lzma.compress(
            render_svg(read_frozen(source), slug, row["source_sha256"]).encode(), preset=6
        )
    )
    row.update(svg=svg.name, svg_sha256=sha(svg), wall_s=time.monotonic() - start)
    rowfile.write_text(json.dumps(row, indent=2, allow_nan=False) + "\n")
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-seeds", default="7,17,41")
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts/v1/map_audit")
    parser.add_argument("--png", action="store_true")
    args = parser.parse_args()
    if tuple(map(int, args.frozen_seeds.split(","))) != SEEDS:
        parser.error("V02 frozen seeds must remain7,17,41")
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    jobs = [
        (name, style, terrain, seed, "primary")
        for name, style, terrain in PRIMARY
        for seed in SEEDS
    ]
    jobs += [
        (style + "_" + terrain, style, terrain, SEEDS[i % 3], "mixed")
        for i, (style, terrain) in enumerate(
            (s, t) for s in STYLES for t in ("flat", "river", "coast", "valley", "lake")
        )
    ]
    for job in jobs:
        row = audit_case(args.out, *job)
        rows.append(row)
        print(
            f"{len(rows)}/38 {row['case']} s{row['seed']} {row['status']}",
            file=sys.stderr,
            flush=True,
        )
        result = dict(status="IN_PROGRESS", cases=rows)
        (args.out / "MATRIX.json").write_text(json.dumps(result, indent=2) + "\n")
    result = dict(
        status="AUDIT_COMPLETE_WITH_FINDINGS"
        if any(r["registered_unserved_residents"] for r in rows)
        else "PASS",
        geometry_status="PASS" if all(not r["geometry_flags"] for r in rows) else "NOT_ACCEPTED",
        population_feasibility_status="PASS"
        if all(r["status"] == "PASS" for r in rows)
        else "PHYSICAL_INFEASIBLE_RETAINED",
        correction_rounds=0,
        frozen_seeds=SEEDS,
        primary_cases=18,
        mixed_cases=20,
        cases=rows,
        unresolved=[
            "generated snapshots have no registered portals; actual registered resident access CDF unsupported; all unserved population retained"
        ],
        scope="synthetic centreline/mask/layer validation plus numerical and visual morphology audit; not historical-city reconstruction or pavement certification",
    )
    (args.out / "MATRIX.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    if args.png:
        render_gallery([r for r in rows if r["family"] == "primary" and r["seed"] == 7], args.out)
    (args.out / "MATRIX.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    with (args.out / "COMPARISON.csv").open("w", newline="") as stream:
        names = (
            "family",
            "case",
            "seed",
            "nodes",
            "sections",
            "blocks",
            "residents",
            "unplaced_residents",
            "registered_served_residents",
            "registered_unserved_residents",
            "mean_block_compactness",
            "mean_section_detour",
            "max_grade",
        )
        writer = csv.DictWriter(stream, fieldnames=names)
        writer.writeheader()
        writer.writerows({key: row[key] for key in names} for row in rows)
    print(json.dumps({k: v for k, v in result.items() if k != "cases"}))
    return 0 if result["geometry_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
