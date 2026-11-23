#!/usr/bin/env python3
"""R2 candidate checks only; research oracle, not production/acceptance code."""
from __future__ import annotations
from fractions import Fraction as F
from pathlib import Path
import hashlib, json, math, random, time
from metroflow.foundation_kinetics import VehicleClass, characteristic

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_suffix(".json")
started = time.perf_counter()

def lower_distance(n, H, J, upper_speed, tau, accel, v0=0.0):
    eta = min(1.0, accel*tau/upper_speed)
    end_memory = -math.expm1(-n*H/tau)
    forcing = n*J-upper_speed*tau*(-math.expm1(-J/(upper_speed*tau)))*end_memory/(-math.expm1(-H/tau))
    return tau*v0*end_memory + eta*forcing

def integrate(vehicle, schedule, v0=0.0):
    distance = 0.0
    v = v0
    for duration, target in schedule:
        dx, v = characteristic(vehicle, v, target, duration)
        distance += dx
    return distance, v

# Exact rational verification of the pointwise differential comparison.
comparison_count = 0
comparison_min_slack = None
for tau in [F(1,10),F(1),F(3)]:
    for upper in [F(1),F(4)]:
        for accel in [F(1,10),F(1),F(10)]:
            for brake in [F(1,5),F(2)]:
                eta = min(F(1),accel*tau/upper)
                for vi in range(11):
                    for fi in range(11):
                        v, drive = upper*vi/10, upper*fi/10
                        rhs = max(-brake,min(accel,(drive-v)/tau))
                        lower_rhs = (eta*drive-v)/tau
                        slack = rhs-lower_rhs
                        assert slack >= 0
                        comparison_min_slack = slack if comparison_min_slack is None else min(comparison_min_slack,slack)
                        comparison_count += 1

H,J,b,tau,accel,brake = 8.0,16.0,4.0,2.0,1.0,1.0
car = VehicleClass(response_s=tau,accel_mps2=accel,brake_mps2=brake)
unclipped = VehicleClass(response_s=tau,accel_mps2=100,brake_mps2=100)
ladder = []
for n in [1,2,4,8]:
    t0 = time.perf_counter()
    schedule = [(4.0,0.0),(4.0,b)]*n
    actual, speed = integrate(car,schedule)
    bound = lower_distance(n,H,J,b,tau,accel)
    sharp, _ = integrate(unclipped,schedule)
    sharp_bound = lower_distance(n,H,J,b,tau,100)
    assert actual+1e-11 >= bound
    assert abs(sharp-sharp_bound) <= 1e-11
    ladder.append({"windows":n,"physical_horizon_s":n*H,"distance_m":actual,
                   "distance_lower_m":bound,"terminal_speed_m_s":speed,
                   "unclipped_sharpness_error_m":abs(sharp-sharp_bound),
                   "wall_s":time.perf_counter()-t0})

rng = random.Random(20261123)
random_checks = 0
min_distance_slack = math.inf
for seed_case in range(80):
    schedule = []
    for n in range(1,9):
        values = [rng.random()*b for _ in range(8)]
        mass = sum(values)
        # Bin duration is one second. Raise insufficient forcing toward b,
        # preserving the exact declared per-frame minimum (roundoff guarded).
        if mass < J+1e-10:
            weight = (J+1e-10-mass)/(8*b-mass)
            values = [v+weight*(b-v) for v in values]
        assert sum(values) >= J-1e-11
        schedule.extend((1.0,v) for v in values)
        actual, _ = integrate(car,schedule)
        bound = lower_distance(n,H,J,b,tau,accel)
        min_distance_slack = min(min_distance_slack,actual-bound)
        assert actual+1e-10 >= bound
        random_checks += 1

length = 20.0
admissible_n = next(n for n in range(1,20) if lower_distance(n,H,J,b,tau,accel) >= length)
assert admissible_n == 3
motion_upper = admissible_n*H
schedule = [(4.0,0.0),(4.0,b)]*admissible_n
position = 0.0
v = 0.0
clock = 0.0
for duration,target in schedule:
    dx, end_v = characteristic(car,v,target,duration)
    if position+dx >= length:
        lo,hi = 0.0,duration
        for _ in range(65):
            mid=(lo+hi)/2
            if position+characteristic(car,v,target,mid)[0] >= length:
                hi=mid
            else:
                lo=mid
        motion_actual = clock+(lo+hi)/2
        break
    position += dx
    v=end_v
    clock += duration
else:
    raise AssertionError("motion did not complete")

# Exact service counterexample and constructive overlap bound.
C = F(2)
def capacity_count(green,receiving):
    return sum(min(C*F(g),F(r)) for g,r in zip(green,receiving))
green_bad = [1]*5+[0]*5
receiving_bad = [F(0)]*5+[C]*5
green_good = [0]*5+[1]*5
receiving_good = receiving_bad
bad,good = capacity_count(green_bad,receiving_bad),capacity_count(green_good,receiving_good)
assert bad == 0 and good == 10
assert sum(C*x for x in green_bad)==sum(C*x for x in green_good)==10
assert sum(receiving_bad)==sum(receiving_good)==10
green_overlap = [1]*7+[0]*3
receiving_overlap = [F(0)]*3+[C]*7
joint = capacity_count(green_overlap,receiving_overlap)
joint_lower = sum(C*x for x in green_overlap)+sum(receiving_overlap)-10*C
assert joint == joint_lower == 8
queued_rank_mass = 5.0  # all five veh-equivalents reach the queue together
service_upper = 10*math.ceil(queued_rank_mass/float(joint))

# Periodic service: min(2*1_[0,7], 2*1_[3,10]) = 2 on [3,7].
remaining = queued_rank_mass
now = motion_actual
zero_service_wait = 0.0
while remaining > 1e-12:
    period = math.floor(now/10)
    phase = now-period*10
    if phase < 3:
        wait=3-phase
        now+=wait
        zero_service_wait+=wait
    elif phase >= 7:
        wait=10-phase+3
        now+=wait
        zero_service_wait+=wait
    else:
        amount=min(remaining,2*(7-phase))
        now+=amount/2
        remaining-=amount
exit_actual=now
assert exit_actual <= motion_upper+service_upper+1e-10
assert zero_service_wait > 0

# Alternative C: two completed integrals identify constant forcing and initial
# speed, but a single integral does not. No inference for arbitrary future V.
theta,initial,tau_c = 2.0,0.5,2.0
windows=[(0.0,1.0),(2.0,3.0)]
rows=[]
observations=[]
for left,right in windows:
    E=tau_c*(math.exp(-left/tau_c)-math.exp(-right/tau_c))
    G=right-left
    rows.append((E,G-E))
    observations.append(E*initial+(G-E)*theta)
(a0,b0),(a1,b1)=rows
det=a0*b1-a1*b0
identified_initial=(observations[0]*b1-observations[1]*b0)/det
identified_theta=(a0*observations[1]-a1*observations[0])/det
single_alternative_theta=1.5
single_alternative_initial=(observations[0]-b0*single_alternative_theta)/a0
assert abs(identified_initial-initial)<1e-12
assert abs(identified_theta-theta)<1e-12
assert abs(a0*single_alternative_initial+b0*single_alternative_theta-observations[0])<1e-12
assert abs(a1*single_alternative_initial+b1*single_alternative_theta-observations[1])>1e-2

result = {
 "schema":"metroflow.constructive.remodel.theory.portfolio.v1",
 "status":"NUMERICALLY_CHECKED_RESEARCH_PORTFOLIO",
 "base_commit":"90bfca2c2ddf081cbdf40d11b95ff820837d03b5",
 "declared_scope":"Fixed characteristic without mixing jumps, finite aligned forcing windows; separate FIFO ready-queue service, causal ex ante promises.",
 "claim_status":{"clipped_response_window_lemma":"DERIVED",
   "strict_service_and_fifo_inverse":"LITERATURE_SUPPORTED_REUSED",
   "native_general_spillback_guarantees":"UNRESOLVED",
   "production_routing_integration":"NOT_RUN","full_day_v03_credit":0},
 "pointwise_comparison":{"exact_fraction_cases":comparison_count,"minimum_slack":str(comparison_min_slack)},
 "forcing_window":{"H_s":H,"J_m":J,"speed_cap_m_s":b,"tau_s":tau,"accel_m_s2":accel,"brake_m_s2":brake,
                   "eta":min(1,accel*tau/b),"random_case_checks":random_checks,"minimum_distance_slack_m":min_distance_slack},
 "increasing_horizon_ladder":ladder,
 "constructive_stop_go_example":{"length_m":length,"motion_upper_s":motion_upper,
    "motion_actual_s":motion_actual,"motion_lower_at_upper_m":lower_distance(admissible_n,H,J,b,tau,accel),
    "service_window_s":10,"green_capacity_integral_veh":14,"receiving_integral_veh":14,
    "joint_service_lower_veh":str(joint_lower),"rank_mass_veh":queued_rank_mass,
    "service_upper_s":service_upper,"combined_upper_s":motion_upper+service_upper,
    "actual_final_rank_exit_s":exit_actual,"actual_zero_service_wait_s":zero_service_wait,
    "all_controls_declared_at_decision_s":0,"oracle_future_used_to_fit_bounds":False},
 "service_counterexample":{"same_green_integral_veh":10,"same_receiving_integral_veh":10,
    "antialigned_joint_service_veh":str(bad),"aligned_joint_service_veh":str(good)},
 "two_probe_alternative":{"model":"constant V over declared finite horizon, known tau; no node wait in measured motion integrals",
    "windows_s":windows,"integrals_m":observations,"determinant_s2":det,
    "identified_initial_m_s":identified_initial,"identified_forcing_m_s":identified_theta,
    "single_probe_alternative_initial_m_s":single_alternative_initial,
    "single_probe_alternative_forcing_m_s":single_alternative_theta},
 "tools":{"exa":"PRIMARY_AUTHOR_BOOK_DISCOVERED",
    "parallel":"PRIMARY_FARHI_AND_BOOK_FETCHED","scispace":"SCHOLARLY_DISCOVERY_USED",
    "wolfram_context":"MCP_-32603_INTERNAL_ERROR","wolfram_evaluator":"MCP_-32603_INTERNAL_ERROR"},
 "sources":[
  {"url":"https://leboudec.github.io/netcal/latex/netCalBook.pdf","locations":"Definition1.3.2; Proposition1.3.6; Theorems1.4.2 and1.4.6"},
  {"url":"https://arxiv.org/pdf/1408.3447","locations":"Definitions4-5; Theorems1-4; Section3 controlled road section"}],
 "source_sha256":hashlib.sha256((ROOT/"src/metroflow/foundation_kinetics.py").read_bytes()).hexdigest(),
 "script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 "wall_s":time.perf_counter()-started
}
OUT.write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result,indent=2))
