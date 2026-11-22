"""Exact route age-square moment and variance regression contracts."""
from fractions import Fraction as F
import pytest
from metroflow.v1.transient_dispersion import (
    QuadraticBoundaryEvent, finite_second_residence_balance,
)


def test_completed_and_unfinished_same_route_age_square_stock():
    e=QuadraticBoundaryEvent
    x=finite_second_residence_balance(
        F(0),F(5),{1:(F(2),F(0),F(0))},
        [e(F(3),1,"out",F(1),F(0),F(0))],
    )
    a=x[1]
    assert a.area_age==F(17)
    assert a.terminal_age2==F(25)
    assert a.output_age2==F(9)
    assert 2*a.area_age + a.entry_age2+a.initial_age2-a.terminal_age2==a.output_age2
    assert a.output_mean==F(3)
    assert a.output_variance==F(0)


def test_preaged_external_route_flow_and_exact_output_dispersion():
    e=QuadraticBoundaryEvent
    x=finite_second_residence_balance(
        F(0),F(5),{1:(F(2),F(0),F(0)),2:(F(0),F(0),F(0))},
        [
            e(F(2),2,"in",F(1),F(-1),F(1)),
            e(F(3),1,"out",F(1),F(0),F(0)),
            e(F(4),2,"out",F(1),F(-1),F(1)),
            e(F(5),1,"out",F(1),F(0),F(0)),
        ],
    )
    assert x[1].output_age1==F(8)
    assert x[1].output_age2==F(34)
    assert x[1].output_mean==F(4)
    assert x[1].output_variance==F(1)
    assert x[2].entry_age2==F(9)
    assert x[2].output_age2==F(25)
    assert x[2].area_age==F(8)


def test_born_time_second_moment_is_not_identifiable_from_first():
    a=finite_second_residence_balance(F(4),F(4),{1:(F(2),F(4),F(8))},[])
    b=finite_second_residence_balance(F(4),F(4),{1:(F(2),F(4),F(10))},[])
    assert a[1].final_mass==b[1].final_mass==F(2)
    assert a[1].final_birth1==b[1].final_birth1==F(4)
    assert a[1].age_variance==F(0)
    assert b[1].age_variance==F(1)


def test_clock_origin_covariance_of_both_birth_moments_and_physical_age():
    e=QuadraticBoundaryEvent
    base=finite_second_residence_balance(
        F(0),F(5),{1:(F(2),F(0),F(0))},[
            e(F(3),1,"out",F(1),F(0),F(0)),
            e(F(5),1,"out",F(1),F(0),F(0)),
        ])
    for shift in (F(-7),F(3,2),F(11)):
        shifted=finite_second_residence_balance(
            shift,shift+F(5),{1:(F(2),F(2)*shift,F(2)*shift*shift)},[
                e(F(3)+shift,1,"out",F(1),shift,shift*shift),
                e(F(5)+shift,1,"out",F(1),shift,shift*shift)])
        for attribute in ("output_age1","output_age2","area_age","output_variance"):
            assert getattr(shifted[1],attribute)==getattr(base[1],attribute)


def test_wrong_second_origin_moment_or_negative_mass_is_rejected():
    with pytest.raises(ValueError):
        finite_second_residence_balance(F(4),F(4),
            {1:(F(2),F(4),F(7))},[])
    with pytest.raises(ValueError):
        finite_second_residence_balance(F(0),F(1),{},[
            QuadraticBoundaryEvent(F(1),1,"out",F(1),F(0),F(0))])
