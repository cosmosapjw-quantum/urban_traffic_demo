"""Bounded audit: resolution sensitivity, geometry and failure classification."""

from pathlib import Path
import sys
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from metroflow.environment.terrain import synthetic_terrain, compile_network, intersects
from metroflow.environment.landuse import zone_city
from metroflow.environment.demand import plan_commute
from metroflow.environment.coupling import road_physics, run_commute
from metroflow.active_suffix import Config
from metroflow.active_suffix.routing import braess_reference


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts/terrain_zones_20261024")
    out.mkdir(parents=True, exist_ok=True)
    t = synthetic_terrain()
    g = compile_network(t)
    c = zone_city(t, g, 100000, 40000)
    roads, _ = road_physics(c)
    sensitivity = []
    coords = {n.id: (n.x_m, n.y_m) for n in g.nodes}
    for e in g.links:
        if e.kind == "surface":
            assert not any(
                intersects(coords[e.u], coords[e.v], r, 6.0) for r in t.water + t.protected
            )
        assert e.grade <= 0.12
    for divisions in (2, 3, 4):
        p = plan_commute(c, roads, divisions=divisions, profile=((0.0, 3600.0, 1.0),))
        sensitivity.append(
            dict(
                divisions=divisions,
                districts=len(p.areas),
                ledger=dict(p.ledger),
                max_margin_error=p.max_margin_error,
            )
        )
    tiny = synthetic_terrain(n=6)
    small = zone_city(tiny, compile_network(tiny), 3000, 1200)
    r, _ = road_physics(small)
    p = plan_commute(small, r, divisions=2, profile=((0.0, 300.0, 1.0),))
    blocked, state = run_commute(small, p, 30.0, Config(dt_s=5.0, paths_per_od=1, event_budget=1))
    assert blocked["status"] == "BLOCKED_RESOURCE" and state.released == 0
    before = braess_reference(shortcut=False)
    after = braess_reference(shortcut=True)
    assert abs(before["mean_cost_min"] - 65) < 1e-8 and abs(after["mean_cost_min"] - 80) < 1e-8
    receipt = dict(
        status="PASS_SCOPED",
        geometry_illegal_surface_edges=0,
        district_sensitivity=sensitivity,
        budget_counterexample=blocked,
        braess_static=dict(
            before_minutes=before["mean_cost_min"],
            after_minutes=after["mean_cost_min"],
            scope="unchanged static oracle; not proof of dynamic equilibrium",
        ),
        warning="Local-trip resolution changes with districts; no empirical convergence claimed.",
    )
    (out / "audit_receipt.json").write_text(json.dumps(receipt, indent=2, allow_nan=False))
    print(json.dumps(receipt, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
