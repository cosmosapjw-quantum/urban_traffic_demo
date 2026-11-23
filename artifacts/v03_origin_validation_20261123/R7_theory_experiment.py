"""Reproduce the finite-response, past-only passage and route experiment."""
from fractions import Fraction as F
from math import ceil
from pathlib import Path
import hashlib
import json
import platform
import subprocess
import time

from metroflow.v1.fifo_route_observability import (
    PassageProbe, FIFOArrivalEnvelope, RouteEdge, FiniteResponseField,
    compose_route, route_certificate,
)

root = Path(__file__).resolve().parents[2]
start = time.perf_counter()
physics = FiniteResponseField(((0, 2), (20, 3), (40, 2), (100, 2)), 2)
vmin, vmax = physics.speed_bounds
models = {}
checks = []
for length in (5, 10, 20, 30):
    probes = []
    for entry in (0, 5, 10, 15):
        b = physics.exit_band(entry, length, F(1, 10**10))
        stamp = F(ceil(b.upper))
        if stamp + 1 <= 20:
            probes.append(PassageProbe("length:"+str(length), entry,
                                      b.lower, b.upper, stamp, stamp+1))
    model = FIFOArrivalEnvelope(probes, context="length:"+str(length),
                               decision_s=20, entry_horizon_s=60,
                               tau_min_s=F(length)/vmax, gamma=physics.gamma)
    models[length] = model
    for k in range(31):
        entry = F(20)+F(k, 2)
        predicted = model.at(entry)
        actual = physics.exit_band(entry, length, F(1, 10**10))
        assert predicted.lower <= actual.lower <= actual.upper <= predicted.upper
        assert physics.distance(entry, actual.lower) <= length
        assert physics.distance(entry, actual.upper) >= length
        checks.append(dict(length_m=str(length), entry_s=str(entry),
                           predicted=[str(predicted.lower),str(predicted.upper)],
                           actual_bracket=[str(actual.lower),str(actual.upper)]))
short, long = models[10], models[20]
edges = (RouteEdge("direct", "O", "D", short),
         RouteEdge("detour_1", "O", "X", long),
         RouteEdge("detour_2", "X", "D", long),
         RouteEdge("return", "X", "O", models[5]))
cert = route_certificate(edges, "O", "D", 20)
direct = compose_route((short,), 20)
detour = compose_route((long,long), 20)
actual_direct = physics.exit_band(20, 10, F(1,10**10))
actual_first = physics.exit_band(20, 20, F(1,10**10))
actual_detour_lower = physics.exit_band(actual_first.lower, 20, F(1,10**10)).lower
actual_detour_upper = physics.exit_band(actual_first.upper, 20, F(1,10**10)).upper
assert direct.upper < detour.lower
assert actual_direct.upper < actual_detour_lower

def encoded_band(b):
    return dict(exact=[str(b.lower),str(b.upper)],
                approximate_s=[float(b.lower),float(b.upper)])

files = [
    "src/metroflow/v1/fifo_route_observability.py",
    "tests/research/test_v03_fifo_route_observability_20261123.py",
    str(Path(__file__).resolve().relative_to(root)),
]
result = dict(
    status="EXACT_RATIONAL_REFERENCE_EXPERIMENT_COMPLETED",
    input=dict(velocity_knots_s_mps=[["0","2"],["20","3"],["40","2"],["100","2"]],
               relaxation_s="2", invariant_speed_bounds_mps=[str(vmin),str(vmax)],
               gamma=str(physics.gamma), decision_s="20", entry_query_domain_s=["0","60"],
               probe_entry_candidates_s=["0","5","10","15"], information_delay_s="1",
               physical_exit_bracket_width_s="1/10000000000"),
    interpretation="Manufactured exact finite-response solution under a fixed spatially homogeneous traffic field; not native V03 city evidence.",
    assertion_tested="124 withheld passages are enclosed by causal sharp FIFO/expansion envelopes; direct route upper is below every declared detour lower.",
    withheld_passages=len(checks), checks=checks,
    route=dict(selected_edges=list(cert.selected_edges),
               direct=encoded_band(direct), detour=encoded_band(detour),
               actual_direct=encoded_band(actual_direct),
               actual_detour=encoded_band(type(direct)(actual_detour_lower,actual_detour_upper)),
               strict_dominance_margin_s=str(detour.lower-direct.upper),
               regret_bound_s=str(cert.regret_bound_s),
               regret_bound_approx_s=float(cert.regret_bound_s)),
    provenance=dict(git_head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip(),
                    python=platform.python_version(),
                    scoped_git_status=subprocess.check_output(["git","status","--short","--",*files],cwd=root,text=True),
                    file_sha256={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in files}),
    elapsed_wall_s=time.perf_counter()-start,
)
output = Path(__file__).with_suffix(".json")
output.write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps({k:v for k,v in result.items() if k not in ("checks",)},indent=2))
