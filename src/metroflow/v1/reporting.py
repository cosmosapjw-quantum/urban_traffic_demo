"""C02 JSON/CSV and faithful 2D diagnostics from the actual executed city."""

import csv
import json
from pathlib import Path
from xml.sax.saxutils import escape


def write_scenario_report(out, result, city):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    (out / "city.json").write_text(
        json.dumps(city.to_dict(), sort_keys=True, allow_nan=False) + "\n"
    )
    with (out / "hourly.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=("time_s", "released_veh", "completed_veh", "active_veh")
        )
        writer.writeheader()
        writer.writerows(result["hourly"])
    with (out / "stages.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("stage", "persons", "vehicles", "cargo_kg"))
        for stage, amounts in result["demand"]["trip_amounts"].items():
            writer.writerow((stage, amounts["persons"], amounts["vehicles"], amounts["cargo_kg"]))
    points = [n.xyz for n in city.roadmap.nodes]
    width = max(p[0] for p in points) + 20
    height = max(p[1] for p in points) + 20
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
    ]
    for s in city.roadmap.sections:
        xy = " ".join(f"{p[0]},{p[1]}" for p in s.points)
        lines.append(
            f'<polyline points="{xy}" fill="none" stroke="#445577" stroke-width="3"><title>{escape(s.id)}</title></polyline>'
        )
    for b in city.face_graph.blocks:
        lines.append(
            f'<text x="{b.xy[0]}" y="{b.xy[1]}" font-size="14">{escape(b.id)}: {b.residents} residents</text>'
        )
    lines.append("</svg>")
    (out / "city.svg").write_text("\n".join(lines))
