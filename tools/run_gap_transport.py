"""Small, repeatable conditional-gap experiments; no car-by-car population."""

from pathlib import Path
from dataclasses import replace, asdict
import sys
import math
import json
import random
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from metroflow.foundation_kinetics import VehicleClass, target_speed
from metroflow.gap_transport import PairBin, PairState, LeaderReport, step, moments, ViabilityError
from metroflow.stopping_envelope import (
    motion,
    maximum_closure,
    interval_closure,
    passage_in_interval,
)


def scenario(delay=0.0, dt=0.25, filtered=True):
    c = VehicleClass(brake_mps2=5.0)
    s = PairState(0.0, (PairBin(c, 100.0, 65.0, 20.0, 15.0),))
    history = [LeaderReport(0.0, 15.0)]
    rows = []
    minimum = math.inf
    first_hit = None
    for _ in range(round(30.0 / dt)):
        t = s.time_s
        p = s.bins[0]
        available = [r for r in history if r.stamp_s <= t - delay]
        report = available[-1] if available else history[0]
        aL = -6.0 if 3.0 <= t < 6.0 else 1.0 if 8.0 <= t < 13.0 else 0.0
        if filtered:
            nxt, proof = step(s, (report,), (aL,), dt, 20.0, 6.0)
            a = proof[0]["acceleration_mps2"]
            m = proof[0]["min_gap_m"]
        else:
            a = max(
                -c.brake_mps2,
                min(
                    c.accel_mps2,
                    (target_speed(c, p.h, 20.0) - p.v) * (-math.expm1(-dt / c.response_s)) / dt,
                ),
            )
            dx, v = motion(p.v, a, dt)
            dl, w = motion(p.w, aL, dt)
            m = p.h - interval_closure(p.v, p.w, a, aL, dt)[0]
            if m < 0:
                rows.append(
                    dict(
                        time_s=t + dt,
                        gap_m=p.h + dl - dx,
                        speed_mps=v,
                        leader_speed_mps=w,
                        accel_mps2=a,
                        min_gap_m=m,
                    )
                )
                return dict(
                    status="PHYSICAL_OVERLAP",
                    trace=rows,
                    min_gap_m=min(minimum, m),
                    mass=100.0,
                    bins=1,
                )
            nxt = PairState(t + dt, (replace(p, h=p.h + dl - dx, v=v, w=w, x=p.x + dx),))
        minimum = min(minimum, m)
        if first_hit is None and nxt.bins[0].x >= 60.0:
            hit = passage_in_interval(p.v, a, 60.0 - p.x, dt)
            first_hit = t + hit
        s = nxt
        history.append(LeaderReport(s.time_s, s.bins[0].w))
        rows.append(
            dict(
                time_s=s.time_s,
                gap_m=s.bins[0].h,
                speed_mps=s.bins[0].v,
                leader_speed_mps=s.bins[0].w,
                accel_mps2=a,
                min_gap_m=m,
            )
        )
    return dict(
        status="HORIZON_REACHED",
        delay_s=delay,
        dt_s=dt,
        min_gap_m=minimum,
        mass=moments(s)["mass"],
        bins=len(s.bins),
        position_m=s.bins[0].x,
        first_60m_s=first_hit,
        trace=rows,
    )


def stress():
    rng = random.Random(720)
    rows = []
    for case in range(60):
        v, w = rng.uniform(0.0, 25.0), rng.uniform(0.0, 25.0)
        b, B = rng.uniform(2.0, 8.0), rng.uniform(2.0, 8.0)
        dt = rng.choice((0.1, 0.25, 0.5))
        c = VehicleClass(brake_mps2=b)
        gap = c.min_gap_m + maximum_closure(v, w, -b, dt, b, B)[0] + rng.uniform(0.01, 20.0)
        s = PairState(0.0, (PairBin(c, 1000.0, gap, v, w),))
        mn = gap
        for k in range(25):
            r = LeaderReport(s.time_s, s.bins[0].w)
            aL = -B if k < 8 else rng.uniform(-B, 2.0)
            s, proof = step(s, (r,), (aL,), dt, 20.0, B)
            mn = min(mn, proof[0]["min_gap_m"])
        assert mn >= 2.0 - 1e-8 and s.bins[0].mass == 1000.0
        rows.append(dict(case=case, dt_s=dt, brake=b, leader_brake=B, min_gap_m=mn))
    return rows


def free_passages():
    rows = []
    for dt in (2.0, 1.0, 0.5, 0.25):
        c = VehicleClass()
        s = PairState(0.0, (PairBin(c, 100000.0, 50.0, 10.0, 10.0),))
        hit = None
        for _ in range(round(12 / dt)):
            p = s.bins[0]
            old = s
            s, proof = step(s, (LeaderReport(s.time_s, 10.0),), (0.0,), dt, 10.0, 6.0)
            if hit is None and s.bins[0].x >= 103.0:
                hit = old.time_s + passage_in_interval(
                    p.v, proof[0]["acceleration_mps2"], 103.0 - p.x, dt
                )
        assert abs(hit - 10.3) < 1e-10
        rows.append(
            dict(
                dt_s=dt,
                first_passage_s=hit,
                exact_s=10.3,
                represented_mass=s.bins[0].mass,
                phase_nodes=1,
            )
        )
    return rows


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    cases = {str(d): scenario(d) for d in (0.0, 0.5, 1.0, 2.0)}
    unconstrained = scenario(filtered=False)
    s = PairState(0.0, (PairBin(VehicleClass(), 100.0, 3.0, 20.0, 0.0),))
    try:
        step(s, (LeaderReport(0.0, 0.0),), (0.0,), 0.25, 20.0, 6.0)
    except ViabilityError as e:
        blocked = dict(
            status="UNCERTIFIED_INITIAL_STATE",
            checkpoint_preserved=(e.checkpoint == s),
            state=asdict(s),
            reason=str(e),
        )
    else:
        raise AssertionError("infeasible state was not rejected")
    result = dict(
        scope="conditional leader-driven phase ensemble; not closed city/platoon physics",
        scenarios=cases,
        unfiltered=unconstrained,
        stress=stress(),
        free_passage=free_passages(),
        infeasible=blocked,
        transient_counterexample=dict(
            final_distance_difference_m=-31.25,
            maximum_closure_m=maximum_closure(20.0, 15.0, -8.0, 0.5, 8.0, 2.0)[0],
            witness_s=5 / 6,
        ),
        seconds=time.perf_counter() - t0,
    )
    (out / "TRAFFIC_RESULTS.json").write_text(json.dumps(result, indent=2, allow_nan=False))
    print(
        json.dumps(
            dict(
                scenarios={
                    k: {a: b for a, b in v.items() if a != "trace"} for k, v in cases.items()
                },
                unfiltered_status=unconstrained["status"],
                unfiltered_min=unconstrained["min_gap_m"],
                stress_cases=len(result["stress"]),
                free_passage=result["free_passage"],
                seconds=result["seconds"],
            ),
            indent=2,
        )
    )
    return result


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "artifacts/gap_viability_20261024/traffic")
