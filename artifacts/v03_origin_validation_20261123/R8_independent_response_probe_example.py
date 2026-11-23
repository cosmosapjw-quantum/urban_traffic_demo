"""Independent exact rational check of the new finite-response probe example."""
from fractions import Fraction as F
import json
from pathlib import Path

def exp_positive_interval(x, n=40):
    x=F(x)
    assert 0<=x<=1
    term=total=F(1)
    for k in range(1,n+1):
        term*=x/k
        total+=term
    first=term*x/(n+1)
    tail=first/(1-x/F(n+2))
    return total,total+tail

def exp_negative_interval(x):
    lo,hi=exp_positive_interval(x)
    return 1/hi,1/lo

ep_lo,ep_hi=exp_positive_interval(F(1,2))
r_lo,r_hi=exp_negative_interval(F(1,10))
C_lo=5*r_lo/(ep_hi-1)
C_hi=5*r_hi/(ep_lo-1)
beta_lo,beta_hi=C_lo/10,C_hi/10

def distance_bounds(h, side):
    h=F(h)
    elo,ehi=exp_negative_interval(h/10)
    zlo,zhi=1-ehi,1-elo
    if side=="slow":
        return h+C_lo*zlo,h+C_hi*zhi
    assert side=="fast"
    return 3*h-C_hi*zhi,3*h-C_lo*zlo

roots={"fast":(F("4.11801149"),F("4.11801150")),
       "slow":(F("6.62243855"),F("6.62243856"))}
for side,(lo,hi) in roots.items():
    assert distance_bounds(lo,side)[1]<10
    assert distance_bounds(hi,side)[0]>10

# Short explicit proof of strict route dominance uses only rational bounds.
ehalf_upper=F(79,48)+F(5,1728)
assert ehalf_upper==F(2849,1728)<F(33,20)
eseven_lower=1+F(7,10)+F(7,10)**2/2
assert eseven_lower==F(389,200)
dominance_extra=5*F(9,10)*(1-1/eseven_lower)/(F(33,20)-1)
assert dominance_extra==F(17010,5057)>3
assert distance_bounds(7,"slow")[0]>10

result={
 "status":"INDEPENDENT_RATIONAL_EXAMPLE_PASSED",
 "arithmetic":"Fraction-only assertions; displayed floats are not certificates",
 "decision_speed_interval_endpoint_enclosures_mps":{
   "lower":[str(1+beta_lo),str(1+beta_hi)],
   "upper":[str(3-beta_hi),str(3-beta_lo)]},
 "decision_speed_approx_mps":[float(1+beta_lo),float(3-beta_lo)],
 "duration_root_brackets_s":{key:list(map(str,val)) for key,val in roots.items()},
 "exact_dominance_lower_distance_m":"7 + 17010/5057 > 10",
 "global_speed_bound_route":"B upper 7 < A upper 10",
 "probe_information_route":"A upper < 7 = B exact",
 "true_field":"A v=V=2 gives 5 s; B v=V=2 over 14 m gives 7 s",
 "actual_global_choice_regret_s":2,
 "author_source_review":"PENDING_FREEZE",
}
print(json.dumps(result,indent=2))
