#!/usr/bin/env python3
"""Increasing finite stop-go research experiments; no V03 acceptance credit."""
from __future__ import annotations
import argparse
from dataclasses import asdict
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import random
import time

from metroflow.foundation_kinetics import VehicleClass, characteristic
from metroflow.v1.stop_go_window_certificate import (
    BoundStatus, ClippedMotionLaw, ExAnteBasis, ForcingWindow, JointServiceWindow,
    QueueRankBound, WindowPhase, evaluate_link_bound, motion_distance_lower,
)

ROOT = Path(__file__).resolve().parents[2]
TIERS = [(16,4),(64,16),(256,64),(512,256)]  # histories, forcing windows per history


def exact_route_side_check():
    # Positive-series remainder for exp(2): after term10, subsequent ratios<=2/12.
    lower = sum((Fraction(2)**k/Fraction(math.factorial(k)) for k in range(11)),Fraction(0))
    first_omitted = Fraction(2)**11/Fraction(math.factorial(11))
    upper = lower + first_omitted/(1-Fraction(2,12))
    assert Fraction(7)<lower<upper<Fraction(8)
    # r=exp(-2) lies in (1/8,1/7). A2 at n=3 becomes:
    # L3-20 = 4*r*((1-r)*(1+r*r)+r**4) > 4*(1/8)*(6/7)=3/7.
    strict_distance_gap = Fraction(3,7)
    motion_upper = Fraction(3)*8
    joint_service = Fraction(14)+14-Fraction(2)*10
    # Exact rational ceil retains the tagged mass-rank service argument.
    windows = math.ceil(Fraction(5,1)/joint_service)
    route_a_upper = motion_upper+windows*10
    route_b_lower = Fraction(72,1)/2  # 72m / known speed cap2m/s; queue delay nonnegative
    assert joint_service==8 and windows==1
    assert route_a_upper==34 and route_b_lower==36 and route_a_upper<route_b_lower
    return {
        "status":"DERIVED_WITH_EXACT_RATIONAL_SIDE_CHECK",
        "exp2_lower_fraction":str(lower),"exp2_upper_fraction":str(upper),
        "r_interval":["1/8","1/7"],"motion_distance_strict_gap_lower_m":str(strict_distance_gap),
        "joint_service_lower_veh":str(joint_service),"service_windows":windows,
        "route_a_upper_s":str(route_a_upper),"route_b_lower_s":str(route_b_lower),
        "strict_route_separation_s":str(route_b_lower-route_a_upper),
        "b_lower_authority":"declared legal path length72m, speed cap2m/s, nonnegative service delay",
        "scope":"same entry clock0, fixed contexts, ex ante guarantees; no production rerouting",
    }


def decimal_lower(law, n, initial):
    with localcontext() as ctx:
        ctx.prec=85
        D=Decimal.from_float
        tau,b,A=D(law.relaxation_s),D(law.speed_cap_m_s),D(law.acceleration_m_s2)
        H,J=Decimal(8),Decimal(16)
        eta=min(Decimal(1),A*tau/b)
        memory=1-(-Decimal(n)*H/tau).exp()
        return +(tau*D(initial)*memory+eta*(Decimal(n)*J-b*tau*(1-(-J/(b*tau)).exp())*memory/(1-(-H/tau).exp())))


def service_exit(ready, mass):
    """Independent periodic integration: actual service2veh/s on [3,7] mod10."""
    time_now=ready
    waiting=0.0
    remaining=mass
    while remaining>1e-12:
        phase=time_now-10*math.floor(time_now/10)
        if phase<3:
            delay=3-phase
            time_now+=delay
            waiting+=delay
        elif phase>=7:
            delay=13-phase
            time_now+=delay
            waiting+=delay
        else:
            served=min(remaining,2*(7-phase))
            time_now+=served/2
            remaining-=served
    return time_now,waiting


def root_in_segment(vehicle, speed, target, duration, remaining):
    lo,hi=0.0,duration
    for _ in range(56):
        mid=(lo+hi)/2
        if characteristic(vehicle,speed,target,mid)[0]>=remaining:
            hi=mid
        else:
            lo=mid
    return (lo+hi)/2


def run_tier(index, profiles, windows):
    start=time.perf_counter()
    rng=random.Random(20261123+index)
    bound_checks=0
    characteristic_segments=0
    decimal_checks=0
    maximum_float_error=0.0
    maximum_error_over_margin=0.0
    minimum_distance_slack=math.inf
    minimum_exit_slack=math.inf
    maximum_zero_service_wait=0.0
    maximum_motion_hit=0.0
    digest=hashlib.sha256()
    for case in range(profiles):
        tau=[.5,1,2,4][case%4]
        accel=[.25,.5,1,2,4][(case//4)%5]
        brake=[.125,.5,1,2,4][(case//20)%5]
        initial=[0.,1.,2.,3.][(case//100)%4]
        law=ClippedMotionLaw(tau,4,accel,brake)
        vehicle=VehicleClass(response_s=tau,accel_mps2=accel,brake_mps2=brake)
        horizon=8.0*windows
        basis=ExAnteBasis("declared-stop-go",f"tier{index}/case{case}: controls fixed before integration",0,0,horizon+100)
        forcing=ForcingWindow(basis,8,16,WindowPhase.ALIGNED,0)
        service=JointServiceWindow.from_marginals(
            basis=basis,window_s=10,capacity_veh_s=2,
            green_integral_lower_veh=14,receiving_integral_lower_veh=14)
        rank=QueueRankBound(basis,5)
        # Length chosen only from declared law/window parameters, before oracle.
        length=windows*16*law.eta/2
        prediction=evaluate_link_bound(context=basis.context,decision_s=0,entry_s=0,
            length_m=length,law=law,forcing=forcing,service=service,rank=rank,
            initial_speed_lower_m_s=initial)
        assert prediction.status is BoundStatus.BOUND_EVALUATED
        histories=[]
        for _ in range(windows):
            values=[0.,0.,0.,0.,4.,4.,4.,4.]
            rng.shuffle(values)
            histories.append(values)
        # Ex ante generator guarantees integral V=16m in each aligned8s window.
        speed=initial
        position=clock=0.0
        motion_hit=None
        for n,values in enumerate(histories,1):
            assert sum(Fraction.from_float(v) for v in values)==16
            digest.update(bytes(int(v) for v in values))
            for target in values:
                dx,next_speed=characteristic(vehicle,speed,target,1.0)
                if motion_hit is None and position+dx>=length:
                    motion_hit=clock+root_in_segment(vehicle,speed,target,1.0,length-position)
                position+=dx
                speed=next_speed
                clock+=1
                characteristic_segments+=1
            bound=motion_distance_lower(law,forcing,n,initial_speed_lower_m_s=initial)
            slack=position-bound.lower_m
            minimum_distance_slack=min(minimum_distance_slack,slack)
            assert slack>=-bound.guard_m
            bound_checks+=1
            if n in (1,windows):
                high_precision=decimal_lower(law,n,initial)
                error=abs(float(Decimal.from_float(bound.lower_m)-high_precision))
                maximum_float_error=max(maximum_float_error,error)
                maximum_error_over_margin=max(maximum_error_over_margin,error/bound.guard_m)
                assert error<=bound.guard_m
                decimal_checks+=1
        assert motion_hit is not None
        actual_exit,wait=service_exit(motion_hit,5)
        assert actual_exit<=prediction.exit_upper_s+1e-9
        minimum_exit_slack=min(minimum_exit_slack,prediction.exit_upper_s-actual_exit)
        maximum_zero_service_wait=max(maximum_zero_service_wait,wait)
        maximum_motion_hit=max(maximum_motion_hit,motion_hit)
    return {"tier":index,"profiles":profiles,"windows_per_profile":windows,
        "actual_physical_horizon_s":8*windows,"characteristic_segments":characteristic_segments,
        "distance_bound_checks":bound_checks,"decimal85_checks":decimal_checks,
        "maximum_float_distance_error_m":maximum_float_error,
        "maximum_error_over_declared_margin":maximum_error_over_margin,
        "minimum_actual_distance_minus_bound_m":minimum_distance_slack,
        "minimum_exit_upper_minus_actual_s":minimum_exit_slack,
        "maximum_actual_zero_service_wait_s":maximum_zero_service_wait,
        "maximum_actual_motion_hit_s":maximum_motion_hit,
        "history_sha256":digest.hexdigest(),"wall_s":time.perf_counter()-start}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--min-tier",type=int,default=1)
    parser.add_argument("--max-tier",type=int,default=4)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    if not 1<=args.min_tier<=args.max_tier<=len(TIERS):
        parser.error("require1<=min-tier<=max-tier<=4")
    started=time.perf_counter()
    tiers=[run_tier(i,*TIERS[i-1]) for i in range(args.min_tier,args.max_tier+1)]
    source_paths=["src/metroflow/v1/stop_go_window_certificate.py",
                  "src/metroflow/foundation_kinetics.py",
                  "tools/research/v03_stop_go_window_experiment_20261123.py"]
    result={"schema":"metroflow.stop_go_window.experiment.v1",
        "status":"NUMERICALLY_CHECKED_SCOPED",
        "model_status":"DERIVED_CONDITIONAL_ANALYTIC_BOUND",
        "numeric_status":"guarded float, separately checked with Decimal85; not directed interval certification",
        "original_v03_full_day_credit":0,"native_rust_invoked":False,
        "all_guarantees_available_at_s":0,"future_oracle_used_to_fit_bounds":False,
        "initial_inputs_generated_before_oracle":True,
        "route_discriminator":exact_route_side_check(),
        "tiers":tiers,"wall_s":time.perf_counter()-started,
        "sha256":{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in source_paths}}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
