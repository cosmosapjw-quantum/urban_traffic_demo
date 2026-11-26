#!/usr/bin/env python3
"""Join clipped motion, joint node service and marked FIFO transport.

Prescribed ex ante controls; this is a research composition, not native V03.
Motion ready time is numerically checked with the independent source
characteristic. Given that binary-float time as an explicit rational input,
mass/birth/exit profile comparisons use exact Fraction arithmetic.
"""
from __future__ import annotations
from dataclasses import asdict
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import time

from metroflow.foundation_kinetics import VehicleClass, characteristic
from metroflow.v1.stop_go_window_certificate import (
    BoundStatus, ClippedMotionLaw, ExAnteBasis, ForcingWindow,
    JointServiceWindow, QueueRankBound, evaluate_link_bound,
)
from metroflow.v1.rank_profile_transport import (
    MarkedMass, RankProfile, RankSegment, ServiceWindow,
    representation_stats, serve_windows, transport_moments,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts/v03_constructive_remodel_20261123/R7_composed_model.json"

def motion_ready():
    car = VehicleClass(response_s=2.0, accel_mps2=1.0, brake_mps2=1.0)
    position, speed, elapsed = 0.0, 0.0, 0.0
    for duration, target in [(4.0, 0.0), (4.0, 4.0)] * 3:
        dx, next_speed = characteristic(car, speed, target, duration)
        if position + dx >= 20.0:
            lo, hi = 0.0, duration
            for _ in range(70):
                mid = (lo + hi) / 2
                if position + characteristic(car, speed, target, mid)[0] >= 20.0:
                    hi = mid
                else:
                    lo = mid
            return 10.0 + elapsed + hi, (10.0 + elapsed + lo, 10.0 + elapsed + hi)
        position, speed, elapsed = position + dx, next_speed, elapsed + duration
    raise AssertionError("declared motion oracle did not reach endpoint")

def actual_service(ready):
    # Periodic green [0,7], receiving [3,10], shifted by entry=10.
    # Both margins have integral 14 veh; their joint service is 8 veh/cycle.
    remaining, now = F(5), ready
    windows = []
    zero_wait = F(0)
    while remaining:
        cycle = (now - 10) // 10
        left, right = F(10 + cycle * 10 + 3), F(10 + cycle * 10 + 7)
        if now < left:
            zero_wait += left - now
            now = left
        elif now >= right:
            nxt = left + 10
            zero_wait += nxt - now
            now = nxt
            right += 10
        amount = min(remaining, 2 * (right - now))
        end = now + amount / 2
        windows.append(ServiceWindow(now, end, 2))
        remaining, now = remaining - amount, end
    return tuple(windows), zero_wait

def materialized_oracle(raw, schedule):
    # Independent mutable proportional-head FIFO, not RankView methods.
    queue = [{g: [m, b] for g, m, b in row} for row in raw]
    result = {}
    for window in schedule:
        remaining, clock = window.rate * (window.end - window.start), window.start
        while remaining:
            head = queue[0]
            total = sum((v[0] for v in head.values()), F(0))
            amount = min(total, remaining)
            fraction, end = amount / total, clock + amount / window.rate
            for mark, (mass, birth) in head.items():
                dm, db = mass * fraction, birth * fraction
                previous = result.get(mark, (F(0), F(0), F(0)))
                result[mark] = tuple(a + b for a, b in zip(
                    previous, (dm, db, dm * (clock + end) / 2)))
                head[mark] = [mass - dm, birth - db]
            if amount == total:
                queue.pop(0)
            remaining, clock = remaining - amount, end
    assert not queue
    return result

def encode(value):
    if isinstance(value, F):
        return str(value)
    if isinstance(value, dict):
        return {k: encode(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [encode(v) for v in value]
    return value

def main():
    started = time.perf_counter()
    basis = ExAnteBasis("fixed-homogeneous-link-A", "declared periodic control and fixed source stock",
                        9.0, 10.0, 10000.0)
    bound = evaluate_link_bound(
        context=basis.context, decision_s=10.0, entry_s=10.0, length_m=20.0,
        law=ClippedMotionLaw(2.0, 4.0, 1.0, 1.0),
        forcing=ForcingWindow(basis, 8.0, 16.0),
        service=JointServiceWindow.from_marginals(
            basis=basis, window_s=10.0, capacity_veh_s=2.0,
            green_integral_lower_veh=14.0, receiving_integral_lower_veh=14.0),
        rank=QueueRankBound(basis, 5.0))
    assert bound.status is BoundStatus.BOUND_EVALUATED and bound.exit_upper_s == 44.0
    ready_float, ready_bracket = motion_ready()
    ready = F.from_float(ready_float)
    # These cohorts entered at [8,9] and [9,10], while V=0 and v=0;
    # all share displacement zero/target20 at decision10. Original births remain.
    raw = (
        (("red", F(2), F(1)), ("blue", F(1), F(1))),
        (("red", F(1, 2), F(1, 2)), ("blue", F(3, 2), F(3))),
    )
    profile = RankProfile(tuple(
        RankSegment(tuple(MarkedMass(*part) for part in row), F(20), (F(8+i), F(9+i)))
        for i, row in enumerate(raw)))
    assert profile.mass == 5 and profile.ready_prefix(20) == 5
    schedule, zero_wait = actual_service(ready)
    oracle = materialized_oracle(raw, schedule)
    refinements = []
    for factor in (1, 2, 8, 32):
        refined = tuple(
            ServiceWindow(w.start + (w.end-w.start)*k/factor,
                          w.start + (w.end-w.start)*(k+1)/factor, w.rate)
            for w in schedule for k in range(factor))
        slices = serve_windows(profile.view(), refined, require_complete=True)
        # Completed motion-to-endpoint coordinate; not a replacement for actual
        # velocity during queue waiting. Readiness has already been achieved.
        observed = transport_moments(slices, displacement=lambda _: F(20))
        exact = {m.mark: (m.mass, m.birth_moment, m.exit_moment) for m in observed.marks}
        assert exact == oracle
        assert sum((m.mass for m in observed.marks), F(0)) == 5
        assert sum((m.birth_moment for m in observed.marks), F(0)) == F(11, 2)
        refinements.append({"factor": factor, "service_slices": len(slices),
                            "exact_oracle_equal": True,
                            "representation": representation_stats([s.view for s in slices])})
    end = schedule[-1].end
    assert float(end) < bound.exit_upper_s < 10.0 + 72.0/2.0
    assert zero_wait == 6
    sources = [Path(__file__), ROOT/"src/metroflow/v1/stop_go_window_certificate.py",
               ROOT/"src/metroflow/v1/rank_profile_transport.py",
               ROOT/"src/metroflow/foundation_kinetics.py"]
    payload = {
        "schema": "V03_CONSTRUCTIVE_MODEL_COMPOSITION_V1",
        "status": "NUMERICALLY_CHECKED_MOTION_AND_EXACT_RATIONAL_TRANSPORT",
        "scope": "declared controls and fixed homogeneous motion; research integration, no native V03",
        "bound": asdict(bound), "motion_ready_float_s": ready_float,
        "motion_ready_float_bracket_s": ready_bracket,
        "motion_time_semantics": "Python characteristic numerical root, not a rigorous interval enclosure",
        "transport_time_semantics": "exact rational interpretation of that declared binary-float input",
        "actual_outlet_s": float(end), "actual_duration_s": float(end)-10,
        "actual_zero_service_wait_s": zero_wait,
        "original_birth_moment_veh_s": F(11, 2),
        "observed_by_mark": {k: {"mass_veh": v[0], "birth_moment_veh_s": v[1],
                                 "exit_moment_veh_s": v[2], "residence_moment_veh_s": v[2]-v[1]}
                             for k, v in oracle.items()},
        "refinement_comparisons": refinements,
        "route_discriminator": {"A_duration_upper_s": 34, "B_length_m": 72, "B_speed_cap_m_s": 2,
                                "B_duration_lower_s": 36, "conditional_strict_order_A_before_B": True,
                                "production_rerouting_executed": False},
        "sources": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sources},
        "original_full_day_credit": 0, "wall_s": time.perf_counter()-started,
    }
    OUT.write_text(json.dumps(encode(payload), ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({k: encode(payload[k]) for k in (
        "status", "motion_ready_float_s", "actual_duration_s", "actual_zero_service_wait_s",
        "route_discriminator", "wall_s")}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
