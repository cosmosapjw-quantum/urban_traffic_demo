"""Independent rational residual audit of frozen finite-response calculations."""
from fractions import Fraction as F
from math import ceil
from pathlib import Path
import hashlib,json
from metroflow.v1.finite_response_probe_certificate import CompletedPassage,ResponseProbeCertificate

ROOT=Path(__file__).resolve().parents[2]
EPS=F(2,10**11) # exactly 2e-11 s, matching the declared numerical comparison.
def exp_pos(q):
    q=F(q);assert q>=0
    k=max(1,ceil(q));x=q/k
    term=total=F(1)
    for n in range(1,25):
        term*=x/n
        total+=term
    tail=(term*x/25)/(1-x/26)
    return total**k,(total+tail)**k
def exp_neg(q):
    lo,hi=exp_pos(q)
    return 1/hi,1/lo
def analytic_distance(t,h,mean,tau=F(10),T=F(5),u=F(15),side="slow"):
    t,h,mean,tau=map(F,(t,h,mean,tau));assert t>=u and h>=0
    el,eh=exp_pos(T/tau)
    rl,rh=exp_neg((t-u)/tau)
    cl,ch=T*rl/(eh-1),T*rh/(el-1)
    zl,zh=exp_neg(h/tau)
    ql,qh=1-zh,1-zl
    if side=="slow":
        return h+(mean-1)*cl*ql,h+(mean-1)*ch*qh
    assert side=="fast"
    return 3*h-(3-mean)*ch*qh,3*h-(3-mean)*cl*ql
def check_root(value,entry,length,mean,side,tau=F(10),u=F(15)):
    x=F(str(value))
    assert analytic_distance(entry,x-EPS,mean,tau=tau,u=u,side=side)[1] < length
    assert analytic_distance(entry,x+EPS,mean,tau=tau,u=u,side=side)[0] > length

base=ROOT/"artifacts/v03_origin_validation_20261123"
j=json.loads((base/"R8_response_probe_experiment.json").read_text())
checks=0
for row in j["rows"]:
    if row["kind"]!="withheld_constant_solution":
        continue
    m=F(row["true_speed_m_s"]);t=F(row["entry_s"]);length=F(row["length_m"])
    check_root(row["duration_bounds"]["lower_s"],t,length,m,"fast")
    check_root(row["duration_bounds"]["upper_s"],t,length,m,"slow")
    true=length/m
    assert F(str(row["duration_bounds"]["lower_s"]))-EPS<=true
    assert true<=F(str(row["duration_bounds"]["upper_s"]))+EPS
    checks+=2
assert checks==120
# Current module calls on fresh parameter combinations; the independent
# residual oracle does not import or call its distance/exponential routines.
runtime_cases=0
for tau in (3,10,40):
    for mean,delay,length in ((F(1),0,2),(F(3),1,5),(F(3,2),2,10),(F(5,2),7,2)):
        c=ResponseProbeCertificate("review",CompletedPassage("review",10,15,15,5*float(mean)),
                                   15+delay,tau,1,3)
        band=c.duration_bounds(15+delay,length)
        check_root(band.lower_s,F(15+delay),F(length),mean,"fast",tau=F(tau))
        check_root(band.upper_s,F(15+delay),F(length),mean,"slow",tau=F(tau))
        runtime_cases+=1
# A shift of the absolute clock changes no duration; no retrospective query.
c=ResponseProbeCertificate("review",CompletedPassage("review",110,115,116,10),116,10,1,3)
b=c.duration_bounds(116,10)
check_root(b.lower_s,F(116),F(10),F(2),"fast",u=F(115))
check_root(b.upper_s,F(116),F(10),F(2),"slow",u=F(115))
try:
    c.duration_bounds(115,10)
except ValueError:
    pass
else:
    raise AssertionError("retrospective query accepted")
expected={
 "docs/research/V03_FINITE_RESPONSE_PROBE_UPGRADE_20261123.md":"e570e9ee34a7ee3f9dc0a3393dd8c80ed6d89f9b931a32aca2171e56b1829148",
 "src/metroflow/v1/finite_response_probe_certificate.py":"9621fa474a0ef0d647f8fb10fdb33fa361427b59a8fdeedda9b680916b5f1903",
 "tests/research/test_v03_finite_response_probe_20261123.py":"bcbee4a6e4e6645f1fd387f8f069f5a133cd98add00a350e1d1ac2ac56bd2ed5",
 "artifacts/v03_origin_validation_20261123/R8_response_probe_experiment.py":"a11609ae0e59b11db43852e25075cec28e545015a033da0d159f53a89530be84",
 "artifacts/v03_origin_validation_20261123/R8_response_probe_experiment.json":"db5b5dc1a771b9bb4fc6e197cb07047461796b44d31b94b62aae55aeb62e619e"}
for rel,sha in expected.items():
    assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==sha
for rel,sha in j["source_sha256_before"].items():
    assert expected[rel]==sha==j["source_sha256_after"][rel]
summary=json.loads((base/"R8_response_probe_experiment.log").read_text())
assert all(j[k]==v for k,v in summary.items())
print(json.dumps({"status":"INDEPENDENT_RATIONAL_RESIDUAL_CHECKS_PASSED",
 "raw_numeric_endpoints_checked":checks,"new_runtime_cases":runtime_cases,
 "new_absolute_clock_shift_case":1,"comparison_tolerance_s":str(EPS),
 "oracle":"Fraction Taylor remainder bounds; signs exact, not a formal enclosure of the f64 outputs",
 "source_sha256":expected,"author_pytest":"READ_NOT_RERUN"},indent=2))
