"""Small mathematical checks for MetroFlow theory-only route comparison.

This imports a scratch exact-rational fluid-server helper. It is not production
code, a native MetroFlow test, or a city benchmark.
"""
from fractions import Fraction as F
from math import exp, log, sqrt
import json
import random
from pathlib import Path
from check_causal_service_stability import (
    Curve, cumulative_curve, departure_curve, queue_recurrence, sup_distance,
)


def variation_difference(a, b):
    xs = sorted(set(a.xs + b.xs))
    ds = [a.at(x) - b.at(x) for x in xs]
    return max(ds) - min(ds), sum(abs(v-u) for u,v in zip(ds,ds[1:]))


cases = []
for seed in (17, 41, 137, 2691):
    rng = random.Random(seed)
    for k in range(32):
        e = cumulative_curve(rng, 6 + k % 7, 17)
        et = cumulative_curve(rng, 6 + k % 7, 19)
        c = cumulative_curve(rng, 6 + k % 7, 13)
        ct = cumulative_curve(rng, 6 + k % 7, 23)
        d, dt = departure_curve(e,c), departure_curve(et,ct)
        assert sup_distance(d,queue_recurrence(e,c,d.xs)) == 0
        assert sup_distance(dt,queue_recurrence(et,ct,dt.xs)) == 0
        ee = sup_distance(e,et)
        osc,tv = variation_difference(c,ct)
        de = sup_distance(d,dt)
        assert de <= ee + osc <= ee + tv
        cases.append(dict(seed=seed,case=k,departure_error=str(de),
                          eligibility_error=str(ee),capacity_oscillation=str(osc),
                          capacity_rate_L1_error=str(tv),bound=str(ee+osc)))

xs=(F(0),F(1),F(2))
e=Curve(xs,(F(0),F(0),F(3)))
c=Curve(xs,(F(0),F(1),F(1)))
ct=Curve(xs,(F(0),F(0),F(2)))
d,dt=departure_curve(e,c),departure_curve(e,ct)
assert sup_distance(c,ct)==1 and sup_distance(d,dt)==2

eps=F(1,10000)
rank=Curve((F(0),1-eps,F(1)),(F(0),F(0),eps))
average=Curve((F(0),F(1)),(F(0),eps))
prefix_error=sup_distance(rank,average)
assert prefix_error == eps*(1-eps)
throughput_difference=1-eps

original=[(F(i,4),F(1,5)) for i in range(5)]
reduced=[(F(0),F(1,4)),(F(1,2),F(1,2)),(F(1),F(1,4))]
moments=lambda atoms:[sum(w*p**k for p,w in atoms) for k in range(3)]
assert moments(original)==moments(reduced)==[F(1),F(1,2),F(3,8)]
# Affine latent dynamics maps degree <=2 polynomials into the same span.
r,lam=F(1,5),F(1,2)
derivative=[F(0),r-lam*F(1,2),2*r*F(1,2)-2*lam*F(3,8)]
assert derivative==[F(0),F(-1,20),F(-7,40)]

# Dimensionless time and state scales for this stability illustration.
gamma,kappa,tau=0.4,0.5,2.0
undamped_lam=(-1+sqrt(1+4*gamma*kappa*tau))/(2*tau)
k,beta,chi,tau_z,delay=0.6,0.1,0.5,10.0,3.0
wn,wv,wz,eta=1.0,0.6,0.6,0.005
inequalities=[(k-eta)*wn-gamma*wv-beta*wz,
              (1-eta*tau)*wv-kappa*wn,
              (1-eta*tau_z)*wz-chi*exp(eta*delay)*wn]
assert undamped_lam>0 and k>gamma*kappa+beta*chi
assert min(inequalities)>0

kap=5.0
soft=20.0-kap*log(1+float(eps)*(exp(15.0/kap)-1))
soft_bound=kap*log(1/float(eps))
assert 5.0 <= soft <= 20.0 and soft-5.0 <= soft_bound

receipt={
    "status":"numerically_checked_finite_mathematical_instances",
    "native_city_execution":"NOT_RUN",
    "joint_arrival_capacity_cases":len(cases),
    "exact_rational_bounds_and_independent_queue_recurrence":True,
    "sharp_capacity_sup_norm_example":{"capacity_sup_error":"1","departure_sup_error":"2",
        "departure_original_at_2":str(d.at(F(2))),"departure_changed_at_2":str(dt.at(F(2)))},
    "rare_blocked_commodity":{"rare_mass":str(eps),"composition_prefix_error":str(prefix_error),
        "departure_difference_at_1":str(throughput_difference),"zero_supply":True},
    "positive_moment_reconstruction":{"source_atoms":5,"reconstructed_atoms":3,
        "moments_0_to_2":[str(x) for x in moments(reduced)],
        "latent_moment_time_derivatives":[str(x) for x in derivative]},
    "softmin_example":{"kappa_m_per_s":kap,"rare_fraction":float(eps),
        "hard_min_m_per_s":5.0,"weighted_softmin_m_per_s":soft},
    "coupled_feedback_example":{"undamped_positive_eigenvalue_per_scaled_time":undamped_lam,
        "damped_small_gain_margin":k-gamma*kappa-beta*chi,
        "exponential_rate_per_scaled_time":eta,"weighted_inequality_slacks":inequalities},
    "cases":cases,
}
out=Path(__file__).with_name("metroflow_controlled_routes_checks.json")
out.write_text(json.dumps(receipt,indent=2)+"\n")
summary={key:value for key,value in receipt.items() if key!="cases"}
print(json.dumps(summary,indent=2))
