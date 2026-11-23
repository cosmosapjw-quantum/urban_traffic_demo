"""Independent bounded exact audit; original author tests are not executed here."""
from fractions import Fraction as F
from itertools import product
from pathlib import Path
import hashlib
import json
from math import ceil
from metroflow.v1.fifo_route_observability import (
    PassageProbe, FIFOArrivalEnvelope, RouteEdge, route_certificate,
    compose_route, FiniteResponseField,
)

ROOT = Path(__file__).resolve().parents[2]
COUNTS = {}
def expect_error(fn):
    try:
        fn()
    except ValueError:
        return
    raise AssertionError("expected ValueError")

def env(probes=(), *, tau=0, gamma=1, decision=5, horizon=1000, context="audit"):
    return FIFOArrivalEnvelope(probes, context=context, decision_s=decision,
        entry_horizon_s=horizon, tau_min_s=tau, gamma=gamma)

def p(x, lo, hi, *, context="audit", stamp=5, delivered=5):
    return PassageProbe(context, x, lo, hi, stamp, delivered)

# Enumerate a different complete finite family, directly from inequalities.
# On t=0,1,2, y2<=5 caps every monotone value at 5; integer Gamma/tau/data
# give integer endpoint extrema. Piecewise-linear rows extend to horizon 5.
intervals0 = [(a,b) for a in range(4) for b in range(a,4)]
intervals2 = [(a,b) for a in range(2,6) for b in range(a,6)]
cases = feasible = 0
for gamma, tau in product((1,2),(0,1)):
    rows = [ys for ys in product(range(6), repeat=3)
            if all(y >= t+tau for t,y in enumerate(ys))
            and all(0 <= b-a <= gamma for a,b in zip(ys,ys[1:]))]
    for a,b in product(intervals0,intervals2):
        expected = [ys for ys in rows if a[0] <= ys[0] <= a[1]
                    and b[0] <= ys[2] <= b[1]]
        cases += 1
        try:
            model = env((p(0,*a),p(2,*b)),tau=tau,gamma=gamma,horizon=5)
        except ValueError:
            assert not expected
            continue
        assert expected
        feasible += 1
        for t in range(3):
            actual = model.at(t)
            assert actual.lower == min(ys[t] for ys in expected)
            assert actual.upper == max(ys[t] for ys in expected)
COUNTS["integer_family_cases"] = cases
COUNTS["integer_family_feasible"] = feasible

# Empty/singleton/duplicate/unknown-upper and finite-domain boundaries.
for gamma in (None,1,2):
    model = env(gamma=gamma,tau=1)
    assert model.at(5).lower == 6 and model.at(5).upper is None
    assert compose_route((model,model),5).lower == 7
    assert compose_route((model,model),5).upper is None
singleton = env(tau=1,decision=0,horizon=0)
assert singleton.at(0).lower == 1 and singleton.at(0).upper is None
duplicate = env((p(1,2,4),p(1,3,5)))
assert (duplicate.at(1).lower,duplicate.at(1).upper) == (3,4)
expect_error(lambda: env((p(1,2,2),p(1,3,3))))
unknown = env((p(1,2,3),),gamma=None)
assert unknown.at(0).upper == 3 and unknown.at(5).upper is None
expect_error(lambda: unknown.at(-1))
expect_error(lambda: unknown.at(1001))
expect_error(lambda: env((p(0,1,1,delivered=6),)))
expect_error(lambda: env((p(0,1,1,context="other"),)))
expect_error(lambda: p(2,1,3))
expect_error(lambda: PassageProbe("audit",0,1,1,1,1,kind="mean"))
expect_error(lambda: compose_route((unknown,),4))
# Upper alone leaves the next domain, while the lower remains inside.
first = env((p(0,0,0,stamp=0,delivered=0),),gamma=2,decision=0,horizon=10)
second = env(decision=0,horizon=F(3,2))
expect_error(lambda: compose_route((first,second),1))
expect_error(lambda: route_certificate(
    (RouteEdge("a","O","X",first),RouteEdge("b","X","D",second)),"O","D",1))
# Lower itself exhausts the next domain after unknown upper propagation.
expect_error(lambda: compose_route(
    (env(tau=3,decision=0,horizon=10),env(decision=0,horizon=2)),0))
COUNTS["boundary_block"] = "passed"

# Independent simple-path enumeration and direct affine evaluation at future
# clocks, including zero-time cycles and ties; no author path fixture reused.
arc_nodes = (("a","O","D"),("b","O","X"),("c","X","D"),
             ("d","O","Y"),("e","Y","D"),("f","X","Y"),
             ("g","Y","X"),("h","X","O"))
for seed in range(24):
    pars = [( (seed+3*i)%3, 1+((seed>> (i%4))&1)) for i in range(8)]
    graph = []
    for (key,tail,head),(tau,gamma) in zip(arc_nodes,pars):
        graph.append(RouteEdge(key,tail,head,env((p(0,tau,tau+1),),
                     tau=tau,gamma=gamma)))
    paths = []
    def walk(node,seen,indices):
        if node == "D":
            paths.append(indices)
            return
        for i,(_,tail,head) in enumerate(arc_nodes):
            if tail == node and head not in seen:
                walk(head,seen|{head},indices+(i,))
    walk("O",{"O"},())
    bounds = {}
    for path in paths:
        lo = hi = F(5)
        for i in path:
            tau,gamma = pars[i]
            lo += tau
            hi = gamma*hi+tau+1
        bounds[tuple(arc_nodes[i][0] for i in path)] = (lo,hi)
    cert = route_certificate(graph,"O","D",5)
    assert cert.lower_optimum_s == min(x[0] for x in bounds.values())
    assert cert.upper_selected_s == min(x[1] for x in bounds.values())
    assert bounds[cert.selected_edges][1] == cert.upper_selected_s
    assert cert.regret_bound_s >= 0
COUNTS["graph_configurations"] = 24

# Independently integrate the manufactured field using a closed primitive.
def primitive(t):
    t = F(t)
    assert 0 <= t <= 100
    if t <= 20:
        return 2*t+t*t/40
    if t <= 40:
        return 4*t-t*t/40-20
    return 2*t+20
def root_bracket(entry,length,width=F(1,10**10)):
    lo,hi = F(entry),F(100)
    assert primitive(hi)-primitive(entry) >= length
    while hi-lo > width:
        mid=(lo+hi)/2
        if primitive(mid)-primitive(entry) < length:
            lo=mid
        else:
            hi=mid
    return lo,hi
j=json.loads((ROOT/"artifacts/v03_origin_validation_20261123/R7_theory_experiment.json").read_text())
log=json.loads((ROOT/"artifacts/v03_origin_validation_20261123/R7_theory_experiment.log").read_text())
assert {k:v for k,v in j.items() if k!="checks"} == log
admitted={}
for length in (5,10,20,30):
    admitted[length]=[]
    for entry in (0,5,10,15):
        lo,hi=root_bracket(entry,length)
        stamp=ceil(hi)
        if stamp+1 <= 20:
            admitted[length].append((F(entry),lo,hi,stamp+1))
    assert admitted[length]
assert len(j["checks"]) == 124
for row in j["checks"]:
    length=F(row["length_m"]);entry=F(row["entry_s"])
    lo,hi=map(F,row["actual_bracket"])
    predlo,predhi=map(F,row["predicted"])
    assert hi-lo <= F(1,10**10)
    assert primitive(lo)-primitive(entry) <= length <= primitive(hi)-primitive(entry)
    assert predlo == entry+length/F(31,10)
    assert predhi == min(upper+F(31,19)*(entry-x)
                        for x,lower,upper,delivery in admitted[length])
    assert predlo <= lo <= hi <= predhi
# Actual direct and detour satisfy independent total-distance equations.
for name,length in (("actual_direct",10),("actual_detour",40)):
    lo,hi=map(F,j["route"][name]["exact"])
    assert primitive(lo)-primitive(20) <= length <= primitive(hi)-primitive(20)
# Target one-sided endpoints from V=v+2*v' and the initial velocity.
forcing=[F(2),F(21,10),F(31,10),F(29,10),F(19,10),F(2)]
assert (min(forcing),max(forcing)) == tuple(map(F,j["input"]["invariant_speed_bounds_mps"]))
field=FiniteResponseField(((0,2),(20,3),(40,2),(100,2)),2)
assert field.distance(0,100)==primitive(100)
end=field.exit_band(0,220)
assert end.lower <= 100 <= end.upper and end.upper==100
expect_error(lambda: field.exit_band(99,3))
COUNTS["raw_withheld_exact_brackets"] = 124
COUNTS["admitted_probe_counts"]={str(k):len(v) for k,v in admitted.items()}
COUNTS["independent_route_integrals"] = 2
# Exact scientific inputs, including frozen proof and raw receipts.
hashes={}
for rel in ["docs/research/V03_FIFO_ROUTE_OBSERVABILITY_THEORY_20261123.md",
            "src/metroflow/v1/fifo_route_observability.py",
            "tests/research/test_v03_fifo_route_observability_20261123.py",
            "artifacts/v03_origin_validation_20261123/R7_theory_experiment.py",
            "artifacts/v03_origin_validation_20261123/R7_theory_experiment.json"]:
    hashes[rel]=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()
assert hashes["docs/research/V03_FIFO_ROUTE_OBSERVABILITY_THEORY_20261123.md"] == "0f03c9ff12000102dcdd8d4e264288dd931ddff1bc656d56740ce42894b52785"
for rel,digest in j["provenance"]["file_sha256"].items():
    assert hashes[rel] == digest
print(json.dumps({"status":"INDEPENDENT_EXACT_CHECKS_PASSED","counts":COUNTS,
                  "source_sha256":hashes,
                  "author_pytest_execution":"NOT_RERUN_BY_THIS_REVIEWER"},indent=2))
