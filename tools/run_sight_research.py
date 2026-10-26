"""Bounded matched-input map cases; no graphics in the scientific core."""

from pathlib import Path
import sys
import json
import time
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from metroflow.restored_city import generate, STYLES
from metroflow.restored_zoning import attach_zones
from metroflow.restored_geometry import crossing_audit, components
from metroflow.frontage_growth import Site, grow_access
from metroflow.sight_frontage import SightRule, SightClass


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    reports = []
    rule = SightRule((SightClass(), SightClass("freight", 1.5, 3.0, 2.3)))
    for style in STYLES:
        start = time.perf_counter()
        city = generate(style)
        stock, _ = attach_zones(city)
        selected = sorted(
            (z for z in stock.zones if z.residents > 0),
            key=lambda z: (-(z.residents + z.jobs), z.id),
        )[:8]
        sites = tuple(Site(z.id, (z.x_m, z.y_m), float(z.residents + z.jobs)) for z in selected)
        old = grow_access(city, sites, budget_m=900.0, max_roads=4, max_length_m=350.0)
        current = grow_access(
            city, sites, budget_m=900.0, max_roads=4, max_length_m=350.0, admission_rule=rule
        )
        audit = crossing_audit(current.city)

        def mu(c):
            return len(c.sections) - len(c.nodes) + len(set(components(c).values()))

        assert not audit["illegal"] and mu(city) == mu(current.city)
        assert (
            abs(
                sum(s.length_m for s in current.city.sections)
                - sum(s.length_m for s in city.sections)
                - current.used_length_m
            )
            < 1e-7
        )
        row = dict(
            style=style,
            baseline_roads=len(old.admitted),
            sight_roads=len(current.admitted),
            baseline_length_m=old.used_length_m,
            sight_length_m=current.used_length_m,
            baseline_admitted=old.admitted,
            sight_admitted=current.admitted,
            rejected=current.rejected,
            illegal_crossings=0,
            cycle_rank=mu(city),
            seconds=time.perf_counter() - start,
        )
        (out / (style + ".json")).write_text(
            json.dumps(
                dict(result=row, city=asdict(current.city), baseline=asdict(old.city)),
                allow_nan=False,
            )
        )
        reports.append(row)
    (out / "MAP_RESULTS.json").write_text(json.dumps(reports, indent=2, allow_nan=False))
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "artifacts/axiom_gap_20261024/map")
