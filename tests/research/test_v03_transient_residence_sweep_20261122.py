"""Independent finite cohort construction and time-origin covariance audit."""
from fractions import Fraction as F
from itertools import product
from metroflow.v1.transient_residence import BoundaryEvent as Event, finite_residence_balance

def test_exact_two_route_finite_horizon_360_crossings_against_direct_cohort_integrals():
    T=F(5)
    checked=0
    for mass_one,exit_one,entry_two,birth_two,mass_two in product(
        (1,2),(1,2,3,4,None),(1,2,3),(-2,0,1),(1,3)
    ):
        if birth_two>entry_two:
            continue
        for exit_two in (entry_two+1,None):
            initial={1:(F(mass_one),-F(mass_one))}
            events=[Event(F(entry_two),2,"in",F(mass_two),F(mass_two*birth_two))]
            if exit_one is not None:
                events.append(Event(F(exit_one),1,"out",F(mass_one),-F(mass_one)))
            if exit_two is not None:
                events.append(Event(F(exit_two),2,"out",F(mass_two),F(mass_two*birth_two)))
            # Source-generated order for distinct boundary times. Exactly
            # same-time events retain the original provided relative order.
            events.sort(key=lambda e:e.clock)
            measured=finite_residence_balance(F(0),T,initial,events)
            assert measured[1].area==F(mass_one*(exit_one if exit_one is not None else 5))
            assert measured[2].area==F(mass_two*((exit_two if exit_two is not None else 5)-entry_two))
            expected_one=F(mass_one*(exit_one+1)) if exit_one is not None else F(0)
            expected_two=F(mass_two*(exit_two-birth_two)) if exit_two is not None else F(0)
            assert (measured[1].output_delay,measured[2].output_delay)==(expected_one,expected_two)
            assert measured[2].entry_age==F(mass_two*(entry_two-birth_two))
            checked+=1
    assert checked==360

def test_global_clock_translation_preserves_actual_age_and_residence_observables():
    old=[Event(F(1),3,"out",F(1),F(-2)),
         Event(F(2),2,"in",F(1),F(-1)),
         Event(F(3),1,"out",F(1),F(0)),
         Event(F(4),2,"out",F(1),F(-1))]
    init={1:(F(2),F(0)),2:(F(0),F(0)),3:(F(1),F(-2))}
    baseline=finite_residence_balance(F(0),F(5),init,old)
    for shift in (F(-7),F(3,2),F(101)):
        translated=[Event(e.clock+shift,e.route,e.direction,e.mass,
                          e.birth_moment+shift*e.mass) for e in old]
        newinit={r:(m,b+shift*m) for r,(m,b) in init.items()}
        relocated=finite_residence_balance(shift,shift+5,newinit,translated)
        for route, original in baseline.items():
            shifted=relocated[route]
            # Physically meaningful ages, area and mass are origin-invariant.
            # Raw birth-moment H is covariant: H' = H + shift*N.
            assert (shifted.initial_age,shifted.entry_age,
                    shifted.output_delay,shifted.terminal_age,shifted.area,
                    shifted.final_mass)==(
                    original.initial_age,original.entry_age,original.output_delay,
                    original.terminal_age,original.area,original.final_mass)
            assert shifted.final_birth_moment==(
                original.final_birth_moment+shift*original.final_mass)
