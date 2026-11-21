"""Original FIFO ideal priority-theory finitely probed versus all-quota observability."""
from fractions import Fraction as F
from pathlib import Path
import json
from tools.research.v03_fifo_finite_quota_probes_20261121 import finite_probe_witness
from tools.research.v03_fifo_priority_quantile_exact_20261121 import curve,w1_mass

ROOT=Path(__file__).resolve().parents[2]
REC=ROOT/"artifacts/v03_quantile_capture_20261121/R8_THEORY_FINITE_QUOTA_PROBES.json"

def test_all_five_fraction_witnesses_reproduce_original_source_exactly():
    j=json.loads(REC.read_bytes())
    assert j["status"]=="CONSTRUCTIVE_PROOF_WITH_EXACT_FINITE_WITNESSES"
    assert len(j["fraction_cases"])==5
    for row in j["fraction_cases"]:
        knots=[F(x) for x in row["probe_quota_knots"]]
        assert finite_probe_witness(knots)==row
        a=[(F(t),F(m),d) for t,m,d in row["baseline"]]
        b=[(F(t),F(m),d) for t,m,d in row["counterexample"]]
        assert a!=b
        for q in knots:assert curve(a,q)==curve(b,q)
        q=F(row["interior_quota"])
        assert abs(curve(a,q)[0]-curve(b,q)[0])==F(row["strict_interior_A_difference"])>0
        assert w1_mass(a,b)==F(row["W1_exact"])>0

def test_complete_observable_but_finite_probes_cannot_identify_cohort_priority():
    # Same sampled observations include exact route-wise cumulative counts.
    two=[(F(2),F(1),"a")]
    split=[(F(1),F(1,2),"a"),(F(3),F(1,2),"a")]
    assert [curve(two,q) for q in (F(0),F(1))]==[curve(split,q) for q in (F(0),F(1))]
    assert curve(two,F(1,4))[0]!=curve(split,F(1,4))[0]
    assert curve(two,F(1,4))[1]==curve(split,F(1,4))[1]
