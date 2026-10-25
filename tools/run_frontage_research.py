"""Small terrain/stock-to-physical-access experiments; stdlib core."""

from pathlib import Path
import sys
import json
import time
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from metroflow.restored_city import generate, STYLES
from metroflow.restored_zoning import attach_zones
from metroflow.restored_geometry import crossing_audit, components
from metroflow.restored_traffic import compile_traffic
from metroflow.frontage_growth import Site, grow_access


def main():
    out = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts/frontage_interval_20261024/map")
    )
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for style in STYLES:
        start = time.perf_counter()
        city = generate(style)
        stock, _ = attach_zones(city)
        # Exogenous declared activity sites, unchanged across this construction.
        selected = sorted(
            (z for z in stock.zones if z.residents > 0),
            key=lambda z: (-(z.residents + z.jobs), z.id),
        )[:8]
        sites = tuple(Site(z.id, (z.x_m, z.y_m), float(z.residents + z.jobs)) for z in selected)
        result = grow_access(city, sites, budget_m=900.0, max_roads=4, max_length_m=350.0)
        audit = crossing_audit(result.city)
        compiled = compile_traffic(result.city)
        assert not audit["illegal"]
        assert result.used_length_m <= 900.0 + 1e-8 and result.admitted

        def mu(c):
            return len(c.sections) - len(c.nodes) + len(set(components(c).values()))

        assert mu(city) == mu(result.city)
        delta = sum(s.length_m for s in result.city.sections) - sum(
            s.length_m for s in city.sections
        )
        assert abs(delta - result.used_length_m) < 1e-7
        row = dict(
            style=style,
            admitted=result.admitted,
            rejected=result.rejected,
            used_length_m=result.used_length_m,
            cycle_rank_before=mu(city),
            cycle_rank_after=mu(result.city),
            nodes_before=len(city.nodes),
            nodes_after=len(result.city.nodes),
            sections_before=len(city.sections),
            sections_after=len(result.city.sections),
            total_length_increment=delta,
            illegal_crossings=0,
            road_count=len(compiled.roads),
            wall_s=time.perf_counter() - start,
        )
        (out / f"{style}.json").write_text(
            json.dumps(
                dict(
                    before=asdict(city),
                    after=asdict(result.city),
                    sites=[asdict(s) for s in sites],
                    result=row,
                ),
                indent=2,
                allow_nan=False,
            )
        )
        rows.append(row)
    (out / "results.json").write_text(json.dumps(rows, indent=2, allow_nan=False))
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
