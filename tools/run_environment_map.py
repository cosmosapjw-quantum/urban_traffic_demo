"""Small reproducible map/stock audit, no rendering dependency."""

from pathlib import Path
import sys
import json
import math
import time
import platform
from dataclasses import asdict
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from metroflow.environment.terrain import synthetic_terrain, compile_network, cell_slope, height
from metroflow.environment.landuse import zone_city


def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts/terrain_zones_20261024")
    target.mkdir(parents=True, exist_ok=True)
    cases = []
    for n, pop in ((6, 3000), (8, 20000), (12, 100000)):
        for seed in (7, 17, 41):
            start = time.perf_counter()
            t = synthetic_terrain(n=n, seed=seed)
            g = compile_network(t)
            c = zone_city(t, g, pop, pop * 2 // 5)
            assert sum(z.residents for z in c.zones) == pop
            assert sum(z.jobs for z in c.zones) == pop * 2 // 5
            assert all(
                z.residents <= z.housing_capacity and z.jobs <= z.job_capacity for z in c.zones
            )
            # An independently evaluated interior gradient must not exceed the corner bound.
            err = 0.0
            for y in range(n):
                for x in range(n):
                    a, b, cc, d = (
                        height(t, x, y),
                        height(t, x + 1, y),
                        height(t, x, y + 1),
                        height(t, x + 1, y + 1),
                    )
                    bound = cell_slope(t, x, y)
                    for u, v in ((0.13, 0.27), (0.5, 0.5), (0.79, 0.86)):
                        val = (
                            math.hypot(
                                (1 - v) * (b - a) + v * (d - cc), (1 - u) * (cc - a) + u * (d - b)
                            )
                            / t.spacing_m
                        )
                        err = max(err, val - bound)
            assert err <= 1e-12
            cases.append(
                dict(
                    n=n,
                    seed=seed,
                    population=pop,
                    jobs=c.jobs,
                    nodes=len(g.nodes),
                    physical_links=len(g.links),
                    bridges=sum(e.kind == "bridge" for e in g.links),
                    components=len(set(dict(g.components).values())),
                    housing_capacity=sum(z.housing_capacity for z in c.zones),
                    job_capacity=sum(z.job_capacity for z in c.zones),
                    zone_counts=dict(Counter(z.use for z in c.zones)),
                    rejected=dict(g.rejected),
                    slope_bound_excess=err,
                    seconds=time.perf_counter() - start,
                )
            )
            if n == 12 and seed == 17:
                (target / "city_100k.json").write_text(
                    json.dumps(asdict(c), indent=2, allow_nan=False)
                )
    result = dict(
        status="PASS_SCOPED",
        python=platform.python_version(),
        cases=cases,
        scope="terrain-aware coarse test environment and finite stocks; no empirical realism",
    )
    (target / "map_receipt.json").write_text(json.dumps(result, indent=2, allow_nan=False))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
