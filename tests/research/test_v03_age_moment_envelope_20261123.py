"""Independent exact finite assertions for the moment envelope theory."""
from fractions import Fraction as F
from itertools import product

import pytest

from metroflow.v1.age_moment_envelope import (
    AgeMomentBlock, censored_tail_upper_bound, cdf_envelope,
    from_birth_moment, stop_loss_envelope,
)


def direct_loss(atoms, u):
    return sum((mass * max(age - u, F(0)) for age, mass in atoms), F(0))


def test_both_sharp_extrema_are_attained_for_every_threshold():
    block = AgeMomentBlock(3, 9, 1, 9)
    lower_atoms = ((F(3), F(3)),)
    upper_atoms = ((F(1), F(9, 4)), (F(9), F(3, 4)))
    for i in range(-2, 21):
        u = F(i, 2)
        env = stop_loss_envelope((block,), u)
        assert env.lower == direct_loss(lower_atoms, u)
        assert env.upper == direct_loss(upper_atoms, u)
        assert env.upper - env.lower <= env.uniform_gap_bound == F(9, 2)


def test_2790_exact_distributions_and_2520_cdf_secant_cases():
    envelope_checks = cdf_checks = 0
    peak_ratio = F(0)
    for lo, width, mass in product((F(0), F(1), F(3)),
                                   (F(1), F(2), F(4)),
                                   (F(1), F(3, 2))):
        hi = lo + width
        ages = (lo, lo + width / 2, hi)
        for i in range(5):
            for j in range(5 - i):
                weights = (F(i, 4), F(j, 4), F(4 - i - j, 4))
                atoms = tuple((age, mass * p) for age, p in zip(ages, weights))
                moment = sum((age * amount for age, amount in atoms), F(0))
                block = AgeMomentBlock(mass, moment, lo, hi)
                source = mass + F(2)
                for twice_u in range(int(2 * hi) + 3):
                    u = F(twice_u, 2)
                    env = stop_loss_envelope((block,), u)
                    actual = direct_loss(atoms, u)
                    assert env.lower <= actual <= env.upper
                    assert (env.upper - env.lower <= env.uniform_gap_bound
                            <= mass * width / 4)
                    peak_ratio = max(peak_ratio,
                                     (env.upper - env.lower) / (mass * width))
                    envelope_checks += 1
                    if u >= F(1, 2):
                        cdf = cdf_envelope((block,), u, F(1, 2), source)
                        actual_cdf = sum((amount for age, amount in atoms
                                          if age <= u), F(0)) / source
                        actual_gt = sum((amount for age, amount in atoms
                                         if age > u), F(0))
                        assert cdf.lower <= actual_cdf <= cdf.upper
                        assert cdf.strict_tail_lower <= actual_gt <= cdf.strict_tail_upper
                        cdf_checks += 1
    assert envelope_checks == 2790
    assert cdf_checks == 2520
    assert peak_ratio == F(1, 4)
    print("EXACT_ENVELOPE_CASES=2790 EXACT_CDF_CASES=2520 MAX_GAP_RATIO=1/4")


def test_known_mean_alone_is_not_substituted_for_the_age_distribution():
    # Two true original ages 1 and 5 have mean3, but K(3)=2, not zero.
    atoms = ((F(1), F(1)), (F(5), F(1)))
    coarse = stop_loss_envelope((AgeMomentBlock(2, 6, 0, 6),), 3)
    assert direct_loss(atoms, F(3)) == 2
    assert (coarse.lower, coarse.upper) == (0, 3)
    assert coarse.lower < direct_loss(atoms, F(3)) < coarse.upper


def test_actual_partition_refinement_is_nested_and_reaches_atom_exactness():
    atoms = tuple((F(i), F(1 + i % 3, 2)) for i in range(9))

    def moment_block(subset):
        return AgeMomentBlock(
            sum((mass for _, mass in subset), F(0)),
            sum((age * mass for age, mass in subset), F(0)),
            min(age for age, _ in subset), max(age for age, _ in subset),
        )

    levels = (
        (moment_block(atoms),),
        (moment_block(atoms[:5]), moment_block(atoms[5:])),
        tuple(moment_block(atoms[a:b]) for a, b in
              ((0, 2), (2, 4), (4, 5), (5, 7), (7, 9))),
        tuple(moment_block((atom,)) for atom in atoms),
    )
    total_mass = sum((mass for _, mass in atoms), F(0))
    total_moment = sum((age * mass for age, mass in atoms), F(0))
    for i in range(-2, 20):
        u = F(i, 2)
        envs = [stop_loss_envelope(level, u) for level in levels]
        actual = direct_loss(atoms, u)
        assert all(x.mass == total_mass and x.age_moment == total_moment
                   for x in envs)
        assert all(x.lower <= actual <= x.upper for x in envs)
        assert all(a.lower <= b.lower and b.upper <= a.upper
                   for a, b in zip(envs, envs[1:]))
        assert envs[-1].lower == actual == envs[-1].upper


def test_birth_moment_translation_preserves_the_observed_age_measure():
    base = from_birth_moment(F(3, 2), 3, 5, 0, 4)
    assert base == AgeMomentBlock(F(3, 2), F(9, 2), 1, 5)
    for shift in (F(-17), F(19, 3), F(1000)):
        shifted = from_birth_moment(F(3, 2), 3 + F(3, 2) * shift,
                                    5 + shift, shift, 4 + shift)
        assert shifted == base


def test_zero_mass_and_degenerate_support_have_exact_limits():
    zero = AgeMomentBlock(0, 0, 0, 12)
    atom = AgeMomentBlock(F(3, 2), F(9, 2), 3, 3)
    for u in (F(-1), F(0), F(3), F(4)):
        env = stop_loss_envelope((zero, atom), u)
        assert env.lower == env.upper == F(3, 2) * max(3 - u, 0)
        assert env.uniform_gap_bound == 0
    all_pending = cdf_envelope((), 0, 1, 5)
    assert all_pending.lower == all_pending.upper == 0
    assert censored_tail_upper_bound(stop_loss_envelope((), 0), 1, 5) == 1


def test_invalid_moments_support_source_and_secant_steps_are_rejected():
    for args in ((-1, 0, 0, 1), (1, 0, -1, 1), (1, 0, 2, 1),
                 (1, -1, 0, 1), (1, 2, 0, 1), (0, 1, 0, 3)):
        with pytest.raises(ValueError):
            AgeMomentBlock(*args)
    with pytest.raises(ValueError):
        from_birth_moment(1, 2, 1, 0, 2)
    env = stop_loss_envelope((AgeMomentBlock(1, 1, 0, 2),), 1)
    for delta in (0, -1):
        with pytest.raises(ValueError):
            censored_tail_upper_bound(env, delta)
    for source in (0, F(1, 2)):
        with pytest.raises(ValueError):
            censored_tail_upper_bound(env, 1, source)
    with pytest.raises(ValueError):
        cdf_envelope((AgeMomentBlock(1, 1, 0, 2),), 1, 0)


def test_cdf_equality_atoms_and_pending_source_are_kept_distinct():
    blocks = (AgeMomentBlock(1, 3, 3, 3), AgeMomentBlock(1, 5, 5, 5))
    for threshold, expected in ((0, F(0)), (3, F(1, 3)),
                                (4, F(1, 3)), (5, F(2, 3))):
        cdf = cdf_envelope(blocks, threshold, 1, 3)
        assert cdf.lower == cdf.upper == expected
    env = stop_loss_envelope(blocks, 3)
    assert env.lower == env.upper == 2
    assert censored_tail_upper_bound(env, 2, 3) == F(2, 3)


def test_envelope_moment_sensitivity_is_at_most_one():
    for lo, hi, mass in ((F(0), F(4), F(1)), (F(2), F(8), F(3, 2))):
        moment = mass * (lo + hi) / 2
        for delta in (F(-1, 4), F(1, 3)):
            a = AgeMomentBlock(mass, moment, lo, hi)
            b = AgeMomentBlock(mass, moment + delta, lo, hi)
            for twice_u in range(-2, int(2 * hi) + 3):
                ea = stop_loss_envelope((a,), F(twice_u, 2))
                eb = stop_loss_envelope((b,), F(twice_u, 2))
                assert abs(ea.lower - eb.lower) <= abs(delta)
                assert abs(ea.upper - eb.upper) <= abs(delta)


def test_more_non_nested_bins_do_not_imply_monotone_refinement():
    atoms = tuple((F(i), F(1 + i % 3, 2)) for i in range(9))

    def block(subset):
        return AgeMomentBlock(sum(m for a, m in subset),
                              sum(a * m for a, m in subset),
                              min(a for a, m in subset),
                              max(a for a, m in subset))

    old = (block(atoms[:5]), block(atoms[5:]))
    crossed = tuple(block(atoms[i:i + 2]) for i in range(0, 9, 2))
    a = stop_loss_envelope(old, F(9, 2))
    b = stop_loss_envelope(crossed, F(9, 2))
    assert a.lower == a.upper == F(37, 4)
    assert b.lower == F(35, 4) < a.lower
    assert b.upper == a.upper
