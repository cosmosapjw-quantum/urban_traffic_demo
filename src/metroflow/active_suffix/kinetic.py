"""Local two-state active traffic moment and bounded-rational choice.

These are a declared kinetic-inspired closure, not an evaluated Boltzmann
collision integral or a calibrated car-following law. All costs use seconds.
"""
import math


def relax_activity(fraction:float, restart_rate:float, stop_rate:float, dt:float)->float:
    """Exact frozen-rate evolution of p' = alpha(1-p)-nu*p."""
    if not (0<=fraction<=1 and restart_rate>0 and stop_rate>=0 and dt>=0):
        raise ValueError('invalid activity/rates/time')
    if not all(math.isfinite(x) for x in (fraction,restart_rate,stop_rate,dt)):
        raise ValueError('nonfinite kinetic input')
    rate=restart_rate+stop_rate; eq=restart_rate/rate
    return fraction+(eq-fraction)*(-math.expm1(-rate*dt))


def passage_time(length_m:float,speed_mps:float,restart_rate:float,stop_rate:float)->float:
    """Mean first-passage time for initially moving, homogeneous stop/restart."""
    if not all(math.isfinite(x) for x in (length_m,speed_mps,restart_rate,stop_rate)):
        raise ValueError('nonfinite passage-time input')
    if length_m<0 or speed_mps<=0 or restart_rate<=0 or stop_rate<0:
        raise ValueError('invalid passage-time parameters')
    return length_m/speed_mps*(1+stop_rate/restart_rate)


def relax_choice(old,costs_s,dt,response_s,temperature_s,path_size=None):
    """Exact frozen-target BGK preference relaxation, not in-flight teleportation."""
    if len(old)!=len(costs_s) or response_s<=0 or temperature_s<0 or dt<0:
        raise ValueError('invalid choice dimensions/time/temperature')
    if any(p<0 or not math.isfinite(p) for p in old) or any(math.isnan(c) or c<0 for c in costs_s):
        raise ValueError('negative/NaN probabilities or travel costs')
    if not all(math.isfinite(x) for x in (dt,response_s,temperature_s)):
        raise ValueError('nonfinite response settings')
    legal=[i for i,c in enumerate(costs_s) if math.isfinite(c)]
    if not legal: return tuple(0. for _ in old)
    ps=tuple(path_size) if path_size is not None else (1.,)*len(old)
    if len(ps)!=len(old) or any(not math.isfinite(x) or x<=0 for x in ps):
        raise ValueError('path size must be positive')
    cmin=min(costs_s[i] for i in legal)
    weights={i:(math.exp(-(costs_s[i]-cmin)/temperature_s)*ps[i]
                if temperature_s>0 else float(costs_s[i]<=cmin+1e-12)*ps[i]) for i in legal}
    total=math.fsum(weights.values()); prior=math.fsum(old[i] for i in legal)
    mix=-math.expm1(-dt/response_s)
    if prior==0: mix=1.
    return tuple((1-mix)*old[i]/prior+mix*weights[i]/total if i in legal and prior>0
                 else weights[i]/total if i in legal else 0. for i in range(len(old)))
