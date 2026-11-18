"""Independent bounded model sanity checks; not production V1 acceptance."""
from __future__ import annotations
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import math
import random
import sys

PATH = Path(__file__).resolve().parents[2] / "tools/research/frozen_relaxation_oracle.py"
spec = spec_from_file_location("urban_v1_frozen_oracle", PATH)
assert spec is not None and spec.loader is not None
oracle = module_from_spec(spec)
sys.modules[spec.name] = oracle
spec.loader.exec_module(oracle)


def test_exact_frozen_vs_independent_rk4_across_species_and_resonances():
    rng = random.Random(20261118)
    for case in range(24):
        count = 1 + case % 3
        weights = [.2 + rng.random() for _ in range(count)]
        weights = [w / sum(weights) for w in weights]
        taus = [.5 + i for i in range(count)]
        gamma = sum(w / tau for w, tau in zip(weights, taus))
        species = []
        for i, (weight, tau) in enumerate(zip(weights, taus)):
            if case % 4 == 0 and i == 0:
                lam = gamma
            elif case % 4 == 1 and i == 0:
                lam = gamma + 1e-8
            elif case % 4 == 2 and i == 0:
                lam = 0.0
            else:
                lam = 0.02 + rng.random() * 1.5
            restart = lam * rng.random()
            species.append(oracle.Species(weight, tau, rng.random(),
                                          restart, lam - restart))
        t, u = .2 + 4 * rng.random(), 5 + 20 * rng.random()
        v0 = rng.random() * u
        exact = oracle.exact_frozen(t, u, v0, tuple(species))
        rk4 = oracle.rk4(t, u, v0, tuple(species), 2400)
        for x, y in zip(exact, rk4):
            assert math.isclose(x, y, abs_tol=2e-9, rel_tol=3e-10), (case, exact, rk4)


def test_mass_and_first_birth_moment_do_not_determine_cumulative_curve():
    a, b = ((0.0, .5), (2.0, .5)), ((1.0, 1.0),)
    moments = lambda mu: (sum(m for _, m in mu), sum(t*m for t, m in mu))
    cumulative = lambda mu, t: sum(m for s, m in mu if s <= t)
    assert moments(a) == moments(b) == (1.0, 1.0)
    assert cumulative(a, .5) == .5 and cumulative(b, .5) == 0.


def test_mean_gap_jensen_and_rare_slow_class_limitation():
    hazard = lambda h: .3 * (10. / (h + 5.)) ** 2
    assert (hazard(4.) + hazard(96.)) / 2 > 18 * hazard(50.)
    for weight in (.1, 1e-6, 1e-12):
        assert min(20., 5. if weight > 0 else 20.) == 5.
    assert min(20., 20.) == 20.
