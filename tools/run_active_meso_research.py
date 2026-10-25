#!/usr/bin/env python3
"""Bounded experiments, no per-vehicle histories; stdlib scientific execution."""

from __future__ import annotations
import argparse
from dataclasses import replace
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from metroflow.active_meso import ActiveMeso, MesoLink, DriverGroup, MesoConfig
from metroflow.kinetic_routes import wardrop_affine


def diamond(dt=1.0, policy="relaxed"):
    links = (
        MesoLink("sa", "s", "a", 150.0, 15.0, 0.5, 25.0),
        MesoLink("at", "a", "t", 300.0, 15.0, 0.3, 45.0),
        MesoLink("sb", "s", "b", 240.0, 15.0, 0.5, 35.0),
        MesoLink("bt", "b", "t", 240.0, 15.0, 0.6, 35.0),
    )
    groups = (
        DriverGroup("normal", "s", "t", 15.0, 0.2, 0.03),
        DriverGroup("cautious", "s", "t", 12.0, 0.12, 0.04),
    )
    cfg = MesoConfig(dt=dt, route_every=max(1, round(10 / dt)), max_paths=2)
    if policy == "greedy":
        cfg = replace(cfg, temperature_s=0.01, cost_tau_s=0.01, choice_tau_s=0.01)
    return ActiveMeso(links, groups, cfg)


def run_diamond(dt=1.0, policy="relaxed", closure=True):
    sim = diamond(dt, policy)
    s = sim.initial_state()
    history = []
    maxerr = 0.0
    peak = 0.0
    jumps = []
    started = perf_counter()
    for i in range(round(1500 / dt)):
        t = i * dt
        previous = s.shares
        control = {"at": 0.0} if closure and 200 <= t < 400 else {}
        s = sim.step(s, (0.45 * dt, 0.2 * dt) if t < 600 else None, capacity_scale=control)
        d = sim.diagnostics(s)
        maxerr = max(maxerr, abs(d["mass_error"]), d["max_group_mass_error"])
        peak = max(peak, max(n / e.storage_veh for n, e in zip(d["occupancy"], sim.links)))
        # Exclude closure transitions from the smooth-response comparison.
        if i % sim.config.route_every == 0 and t not in (200.0, 400.0):
            jumps.append(max(abs(a - b) for a, b in zip(s.shares, previous)))
        if i % max(1, round(5 / dt)) == 0:
            history.append(d)
    return dict(
        dt=dt,
        policy=policy,
        closure=closure,
        elapsed_s=perf_counter() - started,
        final=sim.diagnostics(s),
        fingerprint=sim.fingerprint(s),
        group_completed=s.completed,
        peak_storage_ratio=peak,
        max_mass_error=maxerr,
        max_regular_share_jump=max(jumps),
        sum_regular_share_changes=sum(jumps),
        history=history,
        routes=[
            dict(group=sim.groups[g].name, links=[sim.links[e].key for e in p])
            for g, p, _ in sim.routes
        ],
    )


def service_cases():
    rows = []
    for rate in (0.02, 0.05, 0.07, 0.15):
        for dt in (10.0, 5.0, 2.5, 1.0):
            for signal in (False, True):
                sim = ActiveMeso(
                    (MesoLink("e", "s", "t", 1500.0, 15.0, rate, 225.0),),
                    (DriverGroup("g", "s", "t", braking_rate=0.0),),
                    MesoConfig(dt=dt),
                )
                s = replace(sim.initial_state(), ready=(160.0,), released=(160.0,))
                red_leak = 0.0
                for i in range(round(600 / dt)):
                    green = not signal or (i * dt) % 60 < 30
                    old = s.completed[0]
                    s = sim.step(s, green={"e": green})
                    if not green:
                        red_leak += s.completed[0] - old
                expected = rate * 600 * (0.5 if signal else 1.0)
                error = s.completed[0] - expected
                assert abs(error) < 1e-9 and red_leak == 0.0
                rows.append(
                    dict(
                        rate_vps=rate,
                        dt=dt,
                        signal=signal,
                        completed=s.completed[0],
                        expected=expected,
                        error=error,
                        red_leak=red_leak,
                    )
                )
    return rows


def workload_cases():
    rows = []
    for mass in (1000.0, 10000.0, 100000.0):
        times = []
        for repeat in range(3):
            sim = diamond()
            s = sim.initial_state()
            start = perf_counter()
            for i in range(400):
                s = sim.step(s, (mass * 0.7, mass * 0.3) if i == 0 else None)
            times.append(perf_counter() - start)
        d = sim.diagnostics(s)
        rows.append(
            dict(
                released_mass=mass,
                state_values=sim.state_values,
                steps=400,
                median_elapsed_s=median(times),
                timings_s=times,
                final=d,
            )
        )
    return rows


def map_integration(path):
    city = json.loads(Path(path).read_text())
    links = []
    hierarchy = {"primary": (15.0, 0.8, 2), "secondary": (12.0, 0.55, 1), "local": (8.0, 0.35, 1)}
    for e in city["edges"]:
        speed, cap, lanes = hierarchy[e["hierarchy"]]
        for u, v in ((e["u"], e["v"]), (e["v"], e["u"])):
            links.append(
                MesoLink(
                    f"{e['edge_id']}:{u}>{v}",
                    str(u),
                    str(v),
                    e["length_m"],
                    speed,
                    cap,
                    e["length_m"] * 0.15 * lanes,
                )
            )

    def nearest(c):
        return str(
            min(
                city["nodes"], key=lambda n: (n["x_m"] - c["x_m"]) ** 2 + (n["y_m"] - c["y_m"]) ** 2
            )["node_id"]
        )

    a, b = map(nearest, city["centres"][:2])
    groups = (DriverGroup("outbound", a, b), DriverGroup("inbound", b, a, 12.0, 0.12, 0.04))
    chord = next((e for e in city["edges"] if e["role"] == "infill_chord"), None)
    if chord is not None:
        groups += (DriverGroup("infill_probe", str(chord["u"]), str(chord["v"]), 8.0, 0.2, 0.03),)
    arrival = (0.24, 0.16) + ((0.1,) if chord is not None else ())
    start = perf_counter()
    sim = ActiveMeso(
        links, groups, MesoConfig(dt=2.0, route_every=10, max_paths=2, max_state_values=20000)
    )
    compile_s = perf_counter() - start
    s = sim.initial_state()
    start = perf_counter()
    history = []
    maxerr = 0.0
    for i in range(600):
        s = sim.step(s, arrival if i < 120 else None)
        d = sim.diagnostics(s)
        maxerr = max(maxerr, abs(d["mass_error"]), d["max_group_mass_error"])
        if i % 10 == 0:
            history.append(d)
    return dict(
        map_fingerprint=city["fingerprint"],
        source="generated map, uncalibrated capacity priors",
        directed_links=len(links),
        compile_s=compile_s,
        run_s=perf_counter() - start,
        final=sim.diagnostics(s),
        max_mass_error=maxerr,
        group_completed=s.completed,
        history=history,
        fingerprint=sim.fingerprint(s),
        route_link_keys=[[sim.links[e].key for e in path] for _, path, _ in sim.routes],
        infill_edge_ids=[e["edge_id"] for e in city["edges"] if e["role"] == "infill_chord"],
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--map", type=Path)
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    diamonds = [run_diamond(dt) for dt in (2.0, 1.0, 0.5)]
    comparison = [run_diamond(1.0, mode, False) for mode in ("greedy", "relaxed")]
    edges = (
        ("s", "a", 0.0, 100.0),
        ("a", "t", 100.0, 0.0),
        ("s", "b", 100.0, 0.0),
        ("b", "t", 0.0, 100.0),
    )
    braess = dict(
        before=wardrop_affine(edges, "s", "t", tolerance=1e-8),
        after=wardrop_affine(edges + (("a", "b", 1.0, 0.0),), "s", "t", tolerance=1e-8),
    )
    payload = dict(
        contract="aggregate_active_matter_experiments_v1",
        diamond=diamonds,
        routing_response=comparison,
        service=service_cases(),
        workload=workload_cases(),
        braess_static=braess,
    )
    if args.map:
        payload["map_integration"] = map_integration(args.map)
    (args.output_dir / "traffic_results.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False)
    )
    print(
        json.dumps(
            dict(
                diamond=[
                    {k: v for k, v in x.items() if k not in ("history", "routes")} for x in diamonds
                ],
                service_count=len(payload["service"]),
                workload=payload["workload"],
                braess=braess,
                integration={
                    k: v for k, v in payload.get("map_integration", {}).items() if k != "history"
                },
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
