"""Independent exact Fraction FIFO cohort-prefix contract."""
from fractions import Fraction as F
import pytest
from metroflow.v1.fifo_cohort_moments import CohortPart, CohortPacket, fifo_prefix_moments


def packets():
    return (
        CohortPacket((CohortPart(1, F(3), F(6)), CohortPart(2, F(1), F(5)))),
        CohortPacket((CohortPart(1, F(6), F(12)), CohortPart(2, F(2), F(10)))),
    )


def test_fractional_head_cut_preserves_each_route_mass_and_birth_moment():
    assert fifo_prefix_moments(packets(), F(2)) == {
        1: (F(3, 2), F(3)), 2: (F(1, 2), F(5, 2))
    }
    assert fifo_prefix_moments(packets(), F(6)) == {
        1: (F(9, 2), F(9)), 2: (F(3, 2), F(15, 2))
    }
    assert fifo_prefix_moments(packets(), F(12)) == {
        1: (F(9), F(18)), 2: (F(3), F(15))
    }


def test_prefix_observable_coarsening_if_and_only_if_per_mass_slopes_agree():
    original = packets()
    merged = (CohortPacket((
        CohortPart(1, F(9), F(18)),
        CohortPart(2, F(3), F(15)),
    )),)
    for s in (F(0), F(1), F(2), F(4), F(5), F(6), F(8), F(11), F(12)):
        assert fifo_prefix_moments(original, s) == fifo_prefix_moments(merged, s)
    changed_age = (original[0], CohortPacket((
        CohortPart(1, F(6), F(12)), CohortPart(2, F(2), F(16)),
    )))
    changed_merged = (CohortPacket((
        CohortPart(1, F(9), F(18)), CohortPart(2, F(3), F(21)),
    )),)
    assert fifo_prefix_moments(changed_age, F(2)) != fifo_prefix_moments(changed_merged, F(2))


def test_invalid_service_or_nonpositive_packet_mass_fails_closed():
    for s in (F(-1), F(13)):
        with pytest.raises(ValueError):
            fifo_prefix_moments(packets(), s)
    with pytest.raises(ValueError):
        fifo_prefix_moments((CohortPacket((CohortPart(1, F(0), F(0)),)),), F(0))


def test_exhaustive_small_fifo_cohort_prefix_and_merge_certificate():
    """Exact rational finite sweep, with independent prefix conservation bounds."""
    cases = 0
    for a in range(1, 5):
        for b in range(1, 5):
            for m1 in range(1, 4):
                for m2 in range(1, 4):
                    for birth1 in (-2, 0, 3):
                        for birth2 in (-1, 2):
                            profile = (
                                CohortPart(1, F(m1), F(m1 * birth1)),
                                CohortPart(2, F(m2), F(m2 * birth2)),
                            )
                            first = CohortPacket(tuple(CohortPart(x.route, x.mass * a,
                                                   x.birth_moment * a) for x in profile))
                            second = CohortPacket(tuple(CohortPart(x.route, x.mass * b,
                                                   x.birth_moment * b) for x in profile))
                            merged = CohortPacket(tuple(CohortPart(x.route, x.mass * (a+b),
                                                     x.birth_moment * (a+b)) for x in profile))
                            limit = (a+b) * (m1+m2)
                            for s in (F(0), F(1, 2), F(a*(m1+m2)), F(a*(m1+m2))+F(1, 2),
                                      F(limit)):
                                original = fifo_prefix_moments((first,second),s)
                                single = fifo_prefix_moments((merged,),s)
                                assert original == single
                                assert sum((v[0] for v in original.values()),F(0)) == s
                                assert all(F(0)<=v[0]<=s for v in original.values())
                                cases += 1
    assert cases == 4*4*3*3*3*2*5


def test_fifo_physical_service_semigroup_and_resume_moments():
    """S_(a+b) physical prefix equals S_a and S_b on its exact residual."""
    from metroflow.v1.fifo_cohort_moments import fifo_remainder
    cases=0
    original=packets()
    for a in [F(0),F(1,2),F(1),F(2),F(4),F(6),F(9),F(12)]:
        remains=fifo_remainder(original,a)
        initial=fifo_prefix_moments(original,a)
        for b in [F(0),F(1,2),F(1),F(2),F(5),F(8),F(12)]:
            if a+b>12:continue
            additional=fifo_prefix_moments(remains,b)
            direct=fifo_prefix_moments(original,a+b)
            for r in direct:
                assert direct[r][0] == initial[r][0]+additional.get(r,(F(0),F(0)))[0]
                assert direct[r][1] == initial[r][1]+additional.get(r,(F(0),F(0)))[1]
            cases+=1
    assert cases>=20
