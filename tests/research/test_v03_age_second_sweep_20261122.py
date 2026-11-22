"""Independent exact two-cohort route age-square integration sweep.

Independent expected values integrate each cohort's (t-b) and (t-b)**2
over its actual occupancy interval, not the same code as the moment oracle.
"""
from fractions import Fraction as F
from itertools import product
from metroflow.v1.transient_dispersion import QuadraticBoundaryEvent as E,finite_second_residence_balance


def test_exact_route_age_square_sweep_finite_nonstationary_384_cases():
    t0,T=F(0),F(5)
    n=0
    for (m1,enter1,birth1,exit1,m2,enter2,birth2,exit2) in product(
            (1,2),(0,1),(-1,0),(None,3,5),
            (1,2),(1,2),(-2,0),(None,4)):
        if birth1>enter1 or birth2>enter2 or (exit1 is not None and exit1<enter1):
            continue
        ev=[
            E(F(enter1),1,"in",F(m1),F(m1*birth1),F(m1*birth1**2)),
            E(F(enter2),2,"in",F(m2),F(m2*birth2),F(m2*birth2**2)),
        ]
        if exit1 is not None: ev.append(E(F(exit1),1,"out",F(m1),F(m1*birth1),F(m1*birth1**2)))
        if exit2 is not None: ev.append(E(F(exit2),2,"out",F(m2),F(m2*birth2),F(m2*birth2**2)))
        ev.sort(key=lambda z:z.clock)
        actual=finite_second_residence_balance(t0,T,{},ev)
        for route,mass,entry,birth,exitclock in (
            (1,m1,enter1,birth1,exit1),(2,m2,enter2,birth2,exit2)):
            q=actual[route]
            finish=T if exitclock is None else F(exitclock)
            # An independently constructed exact person-time-integral:
            direct_integral=F(mass)*(finish*finish-F(entry*entry))/2-F(mass*birth)*(finish-F(entry))
            assert q.area_age==direct_integral
            assert q.entry_age2==F(mass*(entry-birth)**2)
            assert q.terminal_age2==(F(mass*(5-birth)**2) if exitclock is None else 0)
            assert q.output_age2==(F(mass*(exitclock-birth)**2) if exitclock is not None else 0)
            assert q.output_age1==(F(mass*(exitclock-birth)) if exitclock is not None else 0)
            assert q.age_variance is None if exitclock is not None else q.age_variance==0
        n+=1
    assert n==384
