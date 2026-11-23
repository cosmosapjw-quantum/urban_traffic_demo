"""Exact rational checks of fixed-service FIFO stability.

Initially empty fluid server; continuous nondecreasing E, absolutely continuous
nondecreasing C, E(0)=C(0)=0. C is fixed independently of composition.
This does not implement a city model or prove coupled-network stability.

Run with Python stdlib only. Optional --out writes the complete JSON receipt.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from dataclasses import dataclass
from fractions import Fraction as F
import json
from pathlib import Path
import random


PROOF = r"""### Fixed-service causal transport stability

Let E, Etilde:[0,T]->[0,M] be continuous nondecreasing eligible-arrival
cumulatives with E(0)=Etilde(0)=0. Let C be the same absolutely continuous,
nondecreasing cumulative service opportunity in both cases, C(0)=0, fixed
independently of commodity composition. The initially empty work-conserving
fluid-server departure is

    D_E(t) = C(t) + inf_{0<=s<=t} (E(s)-C(s)).

Then 0<=D_E(t)<=E(t), D_E is nondecreasing, and departure increments do not
exceed increments of C. The choice s=t gives D_E<=E; nonnegativity follows
from E(s)>=0 and C(s)<=C(t). For t2>=t1, candidates with s<=t1 are at least
D_E(t1), while candidates with s in [t1,t2] are at least E(t1)>=D_E(t1),
establishing monotonicity. Extending the infimum interval can only decrease
the running infimum, yielding the service-increment bound. Where the queue
E-D_E is positive, continuity makes the running minimum locally unchanged,
so available service is used; this is the reflection solution of the
initially empty work-conserving fluid queue.

For each t, the two functions inside the infima differ by at most
epsilon=||E-Etilde||_{infinity,[0,T]}. The elementary inequality
|inf f-inf g|<=||f-g||_infinity therefore gives

    ||D_E-D_Etilde||_infinity <= epsilon.

Now let F:[0,M]->R be a commodity cumulative profile with Lipschitz
constant <=1, and let Fbar have ||F-Fbar||_infinity<=delta/4 on that same
mass domain. With both departure ranks in [0,M], the triangle inequality
gives

    |F(D_E(t))-Fbar(D_Etilde(t))|
      <= |F(D_E(t))-F(D_Etilde(t))|
         + |F(D_Etilde(t))-Fbar(D_Etilde(t))|
      <= epsilon + delta/4.

Here E,D,M,epsilon,delta have mass units, C is cumulative mass service,
and F returns commodity mass. For a scalar attribute cumulative with
Lipschitz constant L and approximation error eta, the bound becomes
L*epsilon+eta, with the corresponding attribute units.

Scope: initially empty server, identical externally fixed C, one fixed
profile comparison, and common mass domain. This does not control a
MetroFlow node whose rates/receiving supply change with the altered head
composition. It also does not infer eligibility from total stock or
replace the finite-response speed law. If E is generated from that law,
its error epsilon must be established separately.
"""


@dataclass(frozen=True)
class Curve:
    xs: tuple[F, ...]
    ys: tuple[F, ...]

    def __post_init__(self):
        if len(self.xs) != len(self.ys) or len(self.xs) < 2:
            raise ValueError("curve shape")
        if any(b <= a for a, b in zip(self.xs, self.xs[1:])):
            raise ValueError("curve knots must strictly increase")
        if any(b < a for a, b in zip(self.ys, self.ys[1:])):
            raise ValueError("cumulative values must be nondecreasing")

    def at(self, x):
        x = F(x)
        if not self.xs[0] <= x <= self.xs[-1]:
            raise ValueError("query outside curve")
        i = bisect_right(self.xs, x) - 1
        if i == len(self.xs) - 1:
            return self.ys[-1]
        a, b = self.xs[i:i+2]
        return self.ys[i] + (self.ys[i+1] - self.ys[i]) * (x-a) / (b-a)


def validate_server(E, C):
    if E.xs[0] != 0 or C.xs[0] != 0 or E.xs[-1] != C.xs[-1]:
        raise ValueError("common time domain must start at zero")
    if E.ys[0] != 0 or C.ys[0] != 0:
        raise ValueError("initially empty zero-origin cumulatives required")


def reflected_value(E, C, t):
    """Exact infimum: affine E-C reaches its minimum at a knot or t."""
    knots = {x for x in E.xs + C.xs if x <= t}
    knots.add(F(t))
    return C.at(t) + min(E.at(x)-C.at(x) for x in knots)


def departure_curve(E, C):
    """Include exact queue-emptying times, not only original input knots."""
    validate_server(E, C)
    base = sorted(set(E.xs + C.xs))
    knots = set(base)
    record = F(0)
    for a, b in zip(base, base[1:]):
        va, vb = E.at(a)-C.at(a), E.at(b)-C.at(b)
        if vb < record < va:
            knots.add(a + (b-a)*(record-va)/(vb-va))
        record = min(record, vb)
    xs = tuple(sorted(knots))
    return Curve(xs, tuple(reflected_value(E, C, t) for t in xs))


def queue_recurrence(E, C, extra_knots=()):
    """Independent queue balance on intervals of constant arrival/service rates.

    Each interval serves min(previous backlog + arrivals, service opportunity).
    No running minimum or reflection formula is used here.
    """
    validate_server(E, C)
    xs = tuple(sorted(set(E.xs + C.xs + tuple(extra_knots))))
    backlog = F(0)
    departed = F(0)
    values = [departed]
    for a, b in zip(xs, xs[1:]):
        arrived = E.at(b)-E.at(a)
        capacity = C.at(b)-C.at(a)
        served = min(backlog + arrived, capacity)
        departed += served
        backlog = backlog + arrived - served
        assert backlog >= 0 and departed <= E.at(b)
        values.append(departed)
    return Curve(xs, tuple(values))


def sup_distance(A, B):
    if (A.xs[0], A.xs[-1]) != (B.xs[0], B.xs[-1]):
        raise ValueError("different curve domains")
    return max(abs(A.at(x)-B.at(x)) for x in set(A.xs+B.xs))


def composition_knots(rank_curve, time_curve):
    """All time knots where a PL time curve crosses a PL rank-profile knot."""
    knots = set(time_curve.xs)
    for ta, tb, qa, qb in zip(time_curve.xs, time_curve.xs[1:],
                               time_curve.ys, time_curve.ys[1:]):
        if qb == qa:
            continue
        for q in rank_curve.xs:
            if qa < q < qb:
                knots.add(ta+(tb-ta)*(q-qa)/(qb-qa))
    return knots


def output_sup_distance(profile, D, approx, Dtilde):
    # The output difference is affine between these knots, so this is a
    # continuous-time supremum for this exact PL instance, not time sampling.
    knots = composition_knots(profile, D) | composition_knots(approx, Dtilde)
    return max(abs(profile.at(D.at(t))-approx.at(Dtilde.at(t))) for t in knots), len(knots)


def cumulative_curve(rng, intervals, denominator):
    xs = tuple(F(i) for i in range(intervals+1))
    ys = [F(0)]
    for _ in range(intervals):
        ys.append(ys[-1] + F(rng.randint(0, 30), denominator))
    return Curve(xs, tuple(ys))


def perturb_arrivals(rng, E):
    ys = [F(0)]
    for a, b in zip(E.ys, E.ys[1:]):
        increment = max(F(0), b-a+F(rng.randint(-2, 2), 29))
        ys.append(ys[-1]+increment)
    return Curve(E.xs, tuple(ys))


def make_profile(rng, M, atoms=24, atoms_per_block=3):
    xs = tuple(M*F(i, atoms) for i in range(atoms+1))
    ys = [F(0)]
    for a, b in zip(xs, xs[1:]):
        rho = F(rng.randint(0, 4), 4)
        ys.append(ys[-1]+rho*(b-a))
    profile = Curve(xs, tuple(ys))
    indices = tuple(range(0, atoms+1, atoms_per_block))
    assert indices[-1] == atoms
    approx = Curve(tuple(xs[i] for i in indices), tuple(ys[i] for i in indices))
    delta = max(b-a for a, b in zip(approx.xs, approx.xs[1:]))
    assert sup_distance(profile, approx) <= delta/4
    return profile, approx, delta


def check_case(seed, case_id):
    rng = random.Random(seed*1000+case_id)
    intervals = 8 + case_id % 9
    E = cumulative_curve(rng, intervals, 17)
    Et = perturb_arrivals(rng, E)
    C = cumulative_curve(rng, intervals, 13)  # one SAME C for both models
    D, Dt = departure_curve(E, C), departure_curve(Et, C)
    for arrival, departure in ((E, D), (Et, Dt)):
        ref = queue_recurrence(arrival, C, departure.xs)
        assert sup_distance(ref, departure) == 0
        for t in departure.xs:
            assert 0 <= departure.at(t) <= arrival.at(t)
        for a, b in zip(departure.xs, departure.xs[1:]):
            assert 0 <= departure.at(b)-departure.at(a) <= C.at(b)-C.at(a)
    epsilon = sup_distance(E, Et)
    departure_error = sup_distance(D, Dt)
    assert departure_error <= epsilon
    M = max(E.ys[-1], Et.ys[-1], F(1))
    profile, approx, delta = make_profile(rng, M)
    output_error, knots = output_sup_distance(profile, D, approx, Dt)
    assert output_error <= epsilon + delta/4
    return {"seed": seed, "case": case_id, "epsilon": str(epsilon),
            "departure_sup_error": str(departure_error), "delta": str(delta),
            "profile_sup_error": str(sup_distance(profile, approx)),
            "output_sup_error": str(output_error),
            "output_bound": str(epsilon+delta/4),
            "exact_output_breakpoints": knots,
            "queue_balance_reference_equal": True,
            "same_service_curve": True}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    cases = [check_case(seed, i) for seed in (7, 17, 41, 2691) for i in range(24)]

    # Manual nontrivial draining example: constant E'=1, C'=2 until t=1,
    # then C'=0. The first interval has zero queue; the second accumulates it.
    E = Curve((F(0), F(1), F(2)), (F(0), F(1), F(2)))
    C = Curve((F(0), F(1), F(2)), (F(0), F(2), F(2)))
    D = departure_curve(E, C)
    assert D.ys == (F(0), F(1), F(1))

    # Genuine interior draining kink: backlog 1 at t=1 and net drain rate 2
    # thereafter; empty at t=3/2. Original knots alone would miss that kink.
    E2 = Curve((F(0), F(1), F(2)), (F(0), F(1), F(1)))
    C2 = Curve((F(0), F(1), F(2)), (F(0), F(0), F(2)))
    D2 = departure_curve(E2, C2)
    assert F(3, 2) in D2.xs and D2.at(F(3, 2)) == 1
    assert sup_distance(D2, queue_recurrence(E2, C2, D2.xs)) == 0

    # Assumption boundary: identical arrivals, changed C, zero input error,
    # yet different departures. This checks why fixed C must stay explicit.
    zero_service = Curve(E.xs, (F(0), F(0), F(0)))
    changed_service_error = sup_distance(departure_curve(E, E),
                                         departure_curve(E, zero_service))
    assert changed_service_error == 2 and sup_distance(E, E) == 0

    report = {
        "schema": "METROFLOW_FIXED_SERVICE_CAUSAL_STABILITY_EXACT_RATIONAL_V1",
        "status": "EXACT_RATIONAL_CHECKS_PASSED",
        "cases_checked": len(cases),
        "exact_output_breakpoints_checked": sum(c["exact_output_breakpoints"] for c in cases),
        "independent_queue_balance_matches": len(cases)*2+1,
        "interior_emptying_kink": "t=3/2, D=1 exactly",
        "changed_service_negative_control": {"arrival_sup_error": "0",
                                              "departure_sup_error": str(changed_service_error)},
        "arithmetic": "fractions.Fraction throughout; PL suprema evaluated at all breakpoints",
        "scope": "initially empty work-conserving scalar fluid server; same composition-independent service C; fixed rank profiles",
        "not_claimed": ["coupled MetroFlow network stability", "original source-byte parity",
                        "full-city execution", "V03 acceptance"],
        "proof": PROOF,
        "cases": cases}
    text = json.dumps(report, indent=2) + "\n"
    if args.out:
        args.out.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
