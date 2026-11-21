"""Reproduce finite exact-rational evidence separately from physical V03 benchmark."""
import json
from pathlib import Path
from fractions import Fraction as Q
from tools.research.v03_fifo_nonclosure_exact_20261121 import exact_witness, fifo_departure, rank
ROOT=Path(__file__).resolve().parents[2]
EVIDENCE=ROOT/"artifacts/v03_fifo_closure_20261121/THEORY_EXACT_WITNESSES.json"
def read():return json.loads(EVIDENCE.read_bytes())

def test_uniform_finite_moment_witnesses_are_exactly_equal_but_fifo_observable_differs():
    r=read()
    assert r["theorem_status"]=="PROVED_BY_FINITE_DIFFERENCES_UNIFORMLY_IN_ALL_P"
    assert r["finite_assertion_status"]=="CHECKED_P_0_TO_10_AND_J_2_TO_7"
    assert [x["p"] for x in r["moment_witnesses"]]==list(range(11))
    for p,old in enumerate(r["moment_witnesses"]):
        got=exact_witness(p)
        assert got==old
        assert len(got["first_p_moments_exactly_equal"])==p+1
        assert all(got["first_p_moments_exactly_equal"])
        assert got["fifo_served_birth_moment_plus"]=="0"
        assert got["fifo_served_birth_moment_minus"]=="1"
    a=fifo_departure([(Q(0),Q(3)),(Q(1),Q(2)),(Q(2),Q(3))],Q(2))
    b=fifo_departure([(Q(0),Q(1)),(Q(1),Q(6)),(Q(2),Q(1))],Q(2))
    assert a==[(Q(0),Q(2))]
    assert b==[(Q(0),Q(1)),(Q(1),Q(1))]

def test_sharp_route_rank_finite_examples_in_tested_range():
    r=read()
    assert [x["destinations"] for x in r["rank_lower_bounds"]]==list(range(2,8))
    for e in r["rank_lower_bounds"]:
        j=e["destinations"]
        basis=[[int(k==i)-int(k==0) for i in range(j)] for k in range(1,j)]
        assert rank(list(map(list,zip(*basis))))==e["rank_destination_flux_on_fixed_mass"]==j-1
        assert rank([[1]*j])==1

def test_claim_boundary_does_not_silently_promote_finite_math_to_full_original_physics():
    r=read()
    assert "not full original V03 100k physical acceptance" in r["nonclaims"]
    assert "not proof against every nonlinear state encoding" in r["nonclaims"]
