"""Light sandbox probes, not a 100k full-day transport benchmark."""

from pathlib import Path
import sys
import json
import time
import platform
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from metroflow.environment.terrain import synthetic_terrain, compile_network
from metroflow.environment.landuse import zone_city
from metroflow.environment.demand import plan_commute
from metroflow.environment.coupling import road_physics, run_commute
from metroflow.active_suffix import Config


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts/terrain_zones_20261024")
    out.mkdir(parents=True, exist_ok=True)
    cases = []
    planning = []
    # Population amplitude versus representation; no person object is created.
    t = synthetic_terrain(n=12)
    g = compile_network(t)
    for pop in (1000, 10000, 100000):
        start = time.perf_counter()
        city = zone_city(t, g, pop, pop * 2 // 5)
        roads, _ = road_physics(city)
        p = plan_commute(city, roads, divisions=4, profile=((0.0, 3600.0, 1.0),))
        planning.append(
            dict(
                population=pop,
                districts=len(p.areas),
                demand_schedules=len(p.demands),
                matrix_cells=len(p.areas) ** 2,
                iterations=p.balance_iterations,
                max_margin_error=p.max_margin_error,
                ledger=dict(p.ledger),
                seconds=time.perf_counter() - start,
            )
        )
    for n, pop, div, release, horizon in (
        (6, 3000, 2, 300.0, 1800.0),
        (12, 100000, 4, 3600.0, 300.0),
    ):
        start = time.perf_counter()
        t = synthetic_terrain(n=n)
        g = compile_network(t)
        c = zone_city(t, g, pop, pop * 2 // 5)
        roads, _ = road_physics(c)
        p = plan_commute(c, roads, divisions=div, profile=((0.0, release, 1.0),))
        config = Config(
            dt_s=5.0,
            route_refresh_s=30.0,
            paths_per_od=2,
            adaptive_routes=True,
            max_routes_per_od=4,
            event_budget=12000,
            max_live_suffixes=4096,
        )
        result, state = run_commute(c, p, horizon, config)
        result["seconds"] = time.perf_counter() - start
        cases.append(result)
        assert result["status"] != "BLOCKED_RESOURCE", result["blocker"]
        assert result["max_mass_error"] < 1e-7
        assert result["max_storage_ratio"] <= 1 + 1e-10
        if pop == 3000:
            assert result["status"] == "CLEARED_SCOPED"
        if pop == 100000:
            assert result["status"] == "HORIZON_REACHED"
            assert result["mean_network_journey_s"] is None
            assert result["not_yet_released"] > 0
        (out / f"trips_{pop}.json").write_text(json.dumps(asdict(p), indent=2, allow_nan=False))
        (out / f"traffic_{pop}.json").write_text(json.dumps(result, indent=2, allow_nan=False))
        (out / f"checkpoint_{pop}.json").write_text(json.dumps(asdict(state), allow_nan=False))
    receipt = dict(
        status="PASS_SCOPED",
        python=platform.python_version(),
        planning=planning,
        cases=[{k: v for k, v in c.items() if k != "trace"} for c in cases],
        limits=[
            "one-way work trips only",
            "noncar/local trips unresolved",
            "100k transport observed only 300 seconds",
            "no empirical calibration",
            "no game comparison",
        ],
    )
    (out / "traffic_receipt.json").write_text(json.dumps(receipt, indent=2, allow_nan=False))
    print(json.dumps(receipt, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
