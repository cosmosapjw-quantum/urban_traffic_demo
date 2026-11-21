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
