"""Independent finite exact Fraction checks for FIFO priority quantile theorem."""
from fractions import Fraction as F
from itertools import combinations, product
from collections import defaultdict
from tools.research.v03_fifo_priority_quantile_exact_20261121 import (
    curve,breakpoints,w1_mass,quantile,witness
)

def test_hand_derived_convex_and_priority_quantile_derivatives():
    c=witness()
    assert c["A_vs_quota_integer_grid"]==["0","0","0","1","4","7","10"]
    assert c["priority_derivative_slopes"]==["0","0","1","3","3","3"]
    rows=[(F(0),F(2),"a"),(F(1),F(1),"b"),(F(3),F(3),"a")]
    for a,b in zip(breakpoints(rows),breakpoints(rows)[1:]):
        mid=(a+b)/2
        assert (curve(rows,mid)[0]-curve(rows,a)[0])/(mid-a)==quantile(rows,mid)
        assert sum(curve(rows,mid)[1].values(),F(0))==mid

def test_w1_bound_exhaustive_small_nontrivial_cohorts_and_sharp_case():
    bytotal=defaultdict(list)
    for k in [1,2,3]:
        for taus in combinations(range(5),k):
            for masses in product([1,2,3],repeat=k):
                rows=[(F(t),F(m),str(i%2)) for i,(t,m) in enumerate(zip(taus,masses))]
                bytotal[sum(masses)].append(rows)
    checked=0
    for group in bytotal.values():
        for first,second in combinations(group,2):
            distance=w1_mass(first,second)
            assert distance>=0
            knots=sorted(set(breakpoints(first)+breakpoints(second)))
            observed=max(abs(curve(first,q)[0]-curve(second,q)[0]) for q in knots)
            assert observed<=distance
            checked+=1
    assert checked>3000
    a=[(F(0),F(7,3),"a")]
    b=[(F(5,2),F(7,3),"a")]
    assert w1_mass(a,b)==F(35,6)
    assert abs(curve(a,F(7,3))[0]-curve(b,F(7,3))[0])==F(35,6)

def test_priority_and_origin_birth_non_equivalence_counterexamples():
    a=[(F(1),F(1),"a"),(F(1),F(1),"b")]
    b=[(F(1),F(1),"b"),(F(1),F(1),"a")]
    assert all(curve(a,F(i,2))[0]==curve(b,F(i,2))[0] for i in range(5))
    assert curve(a,F(1,2))[1]!=curve(b,F(1,2))[1]
    # Chronological FIFO priority tau=(0,1), inherited ORIGIN birth attrs
    # in reverse order (2,0) produce decreasing marked slopes.
    origin_moment=[F(0),F(2),F(2)]
    assert origin_moment[1]-origin_moment[0] > origin_moment[2]-origin_moment[1]
