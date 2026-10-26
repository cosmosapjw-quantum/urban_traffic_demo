"""Bounded map experiment. Reuses fixed city seeds/sites and exact terrain rays."""

from pathlib import Path
from dataclasses import asdict
import sys
import json
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from metroflow.restored_city import generate, STYLES
from metroflow.restored_zoning import attach_zones
from metroflow.restored_geometry import crossing_audit, components
from metroflow.frontage_growth import Site, grow_access
from metroflow.sight_frontage import SightRule, SightClass


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    old = SightRule((SightClass(), SightClass("freight", 1.5, 3.0, 2.3)))
    new = SightRule(
        (
            SightClass(reaction_accel_mps2=1.0),
            SightClass("freight", 1.5, 3.0, 2.3, reaction_accel_mps2=0.7),
        ),
        approach_step_m=5.0,
    )
    for style in STYLES:
        start = time.perf_counter()
        c = generate(style)
        stock, _ = attach_zones(c)
        zones = sorted(
            (z for z in stock.zones if z.residents > 0),
            key=lambda z: (-(z.residents + z.jobs), z.id),
        )[:8]
        sites = tuple(Site(z.id, (z.x_m, z.y_m), float(z.residents + z.jobs)) for z in zones)
        results = [
            grow_access(c, sites, budget_m=900.0, max_roads=4, max_length_m=350.0, admission_rule=r)
            for r in (old, new)
        ]
        row = {"style": style, "cases": []}
        for label, res in zip(("parent_single_eye", "accelerating_scan"), results):
            audit = crossing_audit(res.city)

            def cycle(city):
                return len(city.sections) - len(city.nodes) + len(set(components(city).values()))

            assert not audit["illegal"] and cycle(c) == cycle(res.city)
            length_error = (
                sum(s.length_m for s in res.city.sections)
                - sum(s.length_m for s in c.sections)
                - res.used_length_m
            )
            assert abs(length_error) < 1e-7 and res.used_length_m <= 900.0 + 1e-9
            row["cases"].append(
                dict(
                    mode=label,
                    admitted=res.admitted,
                    rejected=res.rejected,
                    length_m=res.used_length_m,
                    cycle=cycle(res.city),
                    length_error_m=length_error,
                )
            )
            (out / f"{style}_{label}.json").write_text(json.dumps(asdict(res), allow_nan=False))
        row["seconds"] = time.perf_counter() - start
        rows.append(row)
        print(style, [x["length_m"] for x in row["cases"]], flush=True)
    (out / "MAP_RESULTS.json").write_text(json.dumps(rows, indent=2, allow_nan=False))
    return rows


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "artifacts/gap_viability_20261024/map")
