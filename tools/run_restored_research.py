"""Reproducible bounded research runs; simulation uses only the standard library."""

from pathlib import Path
import argparse
from collections import Counter
from dataclasses import asdict
import json
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from metroflow.restored_city import generate, STYLES
from metroflow.restored_geometry import crossing_audit, components
from metroflow.restored_zoning import attach_zones
from metroflow.restored_traffic import compile_traffic, run_layered
from metroflow.environment.demand import plan_commute
from metroflow.active_suffix import Config, Demand, Road, Model
from metroflow.active_suffix.routing import braess_reference


def write(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")


def map_case(out, style, seed):
    start = time.perf_counter()
    city = generate(style, seed=seed)
    audit = crossing_audit(city)
    stock, distances = attach_zones(city)
    summary = dict(
        style=style,
        seed=seed,
        nodes=len(city.nodes),
        sections=len(city.sections),
        weak_components=len(set(components(city).values())),
        facilities=dict(Counter(s.facility for s in city.sections)),
        rejected=dict(city.rejected),
        illegal_crossings=len(audit["illegal"]),
        separated_contacts=len(audit["grade_separated"]),
        population=sum(z.residents for z in stock.zones),
        jobs=sum(z.jobs for z in stock.zones),
        housing_capacity=sum(z.housing_capacity for z in stock.zones),
        max_access_distance_m=max(distances.values()),
        wall_s=time.perf_counter() - start,
    )
    write(out / f"map_{style}_{seed}.json", summary)
    assert summary["population"] == 100000 and summary["jobs"] == 40000
    assert not audit["illegal"], audit["illegal"]
    return summary


def traffic_case(out, style, closure=False, horizon=300.0, dt=5.0):
    start = time.perf_counter()
    road_map = generate(style)
    city, distances = attach_zones(road_map)
    network = compile_traffic(road_map)
    plan = plan_commute(
        city,
        network.roads,
        divisions=3,
        profile=((0.0, 3600.0, 1.0),),
        allowed_turns=network.allowed_turns,
    )
    cfg = Config(
        dt_s=dt,
        route_refresh_s=30.0,
        paths_per_od=2,
        adaptive_routes=True,
        max_routes_per_od=4,
        max_live_suffixes=12000,
        event_budget=24000,
    )
    failures = (("bridge:6", 60.0, 180.0, 0.0),) if closure else ()
    report, state = run_layered(network, plan.demands, horizon, cfg, failures)
    report.update(
        style=style,
        seed=17,
        resident_stock=city.population,
        job_stock=city.jobs,
        planning_ledger=dict(plan.ledger),
        balance_iterations=plan.balance_iterations,
        max_margin_error=plan.max_margin_error,
        districts=len(plan.areas),
        max_access_distance_m=max(distances.values()),
        wall_s=time.perf_counter() - start,
    )
    key = f"{style}_" + ("bridge_closed" if closure else "baseline") + f"_{int(horizon)}s"
    if dt != 5.0:
        key += f"_dt{dt:g}"
    write(out / f"traffic_{key}.json", report)
    write(out / f"checkpoint_{key}.json", asdict(state) if state is not None else {})
    write(
        out / f"input_{key}.json",
        dict(
            map=asdict(road_map),
            plan=asdict(plan),
            config=asdict(cfg),
            compiled=dict(
                roads=[asdict(r) for r in network.roads],
                turns=sorted(network.allowed_turns),
                crosswalk=[asdict(b) for b in network.crosswalk],
                map_fingerprint=network.map_fingerprint,
            ),
        ),
    )
    assert report["status"] == "HORIZON_REACHED", report["status"]
    assert report["max_storage_ratio"] <= 1.0 + 1e-10
    assert report["max_mass_error"] <= 1e-8 * max(1.0, report["released"])
    assert report["per_car_records"] == 0
    return {
        k: report[k]
        for k in (
            "style",
            "resident_stock",
            "directed_roads",
            "legal_turns",
            "districts",
            "demand_schedules",
            "time_s",
            "released",
            "completed",
            "active",
            "pending",
            "max_mass_error",
            "max_storage_ratio",
            "peak_live_suffixes",
            "peak_arrival_records",
            "wall_s",
        )
    }


def controls(out):
    results = dict(braess_without=braess_reference(), braess_with=braess_reference(shortcut=True))
    assert results["braess_with"]["mean_cost_min"] > results["braess_without"]["mean_cost_min"]
    # Exact single-link low-density timing oracle, separated from signal/network calibration.
    timing = []
    for dt in (4.0, 2.0, 1.0, 0.5):
        r = Road("r", "O", "D", 100.0, 10.0, 2.0, 100.0)
        m = Model(
            (r,),
            (Demand("O", "D", 0.0, 4.0, 0.01),),
            Config(dt_s=dt, paths_per_od=1, interaction_rate_s=0.0),
        )
        s = m.initial()
        for _ in range(round(100 / dt)):
            s = m.step(s)
        mean = s.vehicle_seconds / s.completed
        timing.append(dict(dt_s=dt, exact_s=10.0, measured_s=mean, error_s=mean - 10.0))
        assert 0 <= mean - 10.0 <= 4 * dt
    results["time_refinement"] = timing
    write(out / "controls.json", results)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--part", choices=("map", "traffic", "controls"), required=True)
    parser.add_argument("--style", choices=STYLES, default="grid_core")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--horizon", type=float, default=300.0)
    parser.add_argument("--closure", action="store_true")
    parser.add_argument("--dt", type=float, default=5.0)
    parser.add_argument(
        "--out", type=Path, default=Path("artifacts/restored_layers_20261024/resume")
    )
    args = parser.parse_args()
    if args.part == "map":
        result = map_case(args.out, args.style, args.seed)
    elif args.part == "traffic":
        result = traffic_case(args.out, args.style, args.closure, args.horizon, args.dt)
    else:
        result = controls(args.out)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
