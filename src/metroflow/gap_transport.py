"""Conditional pair phase transport, not individual vehicles or a closed network.

Follower quadrature carries mass; leader speed is a conditional mark, not a
second counted population. Gap evolves exactly with relative displacement.
Safety assumes fresh exact local gap/speed, truthful possibly stale leader-speed
reports, leader acceleration >= -B, immediate actuation of bounded held control,
and available full-braking fallback. Delayed gap sensing is NOT covered.
"""
from dataclasses import dataclass,replace
import math
from .foundation_kinetics import VehicleClass,target_speed
from .stopping_envelope import motion,maximum_closure,interval_closure

ROUNDING_M=1e-9

@dataclass(frozen=True,slots=True)
class PairBin:
    vehicle:VehicleClass
    mass:float
    h:float
    v:float
    w:float
    x:float=0.

    def __post_init__(self):
        if not isinstance(self.vehicle,VehicleClass):raise ValueError('invalid physical class')
        if any(not math.isfinite(z) or z<0 for z in (self.mass,self.h,self.v,self.w)) or not math.isfinite(self.x):
            raise ValueError('invalid pair quadrature')

@dataclass(frozen=True,slots=True)
class PairState:
    time_s:float
    bins:tuple[PairBin,...]

    def __post_init__(self):
        if not math.isfinite(self.time_s) or self.time_s<0:raise ValueError('invalid physical clock')
        if not isinstance(self.bins,tuple) or not self.bins:raise ValueError('nonempty immutable bins required')

@dataclass(frozen=True,slots=True)
class LeaderReport:
    stamp_s:float
    speed_mps:float

    def __post_init__(self):
        if any(not math.isfinite(z) or z<0 for z in (self.stamp_s,self.speed_mps)):
            raise ValueError('invalid leader report')

class ViabilityError(RuntimeError):
    """The stated robust certificate is empty, not a universal crash theorem."""


def lower_speed(report,now,B):
    if not math.isfinite(now) or now<0 or not math.isfinite(B) or B<=0:
        raise ValueError('invalid report clock/braking bound')
    if report is None:return 0.
    if report.stamp_s>now:raise ValueError('future report is not admissible')
    return max(0.,report.speed_mps-B*(now-report.stamp_s))


def control(p,report,now,dt,cap,B):
    """Least modification of nominal acceleration within the viable interval.

    Crucially does NOT read p.w: physical truth cannot leak into perception.
    Bisection uses monotonicity of projected displacement with held acceleration.
    """
    if not math.isfinite(dt) or dt<=0:raise ValueError('positive finite control interval required')
    c=p.vehicle;wlow=lower_speed(report,now,B)
    target=target_speed(c,p.h,cap)
    desired=(target-p.v)*(-math.expm1(-dt/c.response_s))/dt
    desired=max(-c.brake_mps2,min(c.accel_mps2,desired))
    allowance=p.h-c.min_gap_m
    envelope=lambda a:maximum_closure(p.v,wlow,a,dt,c.brake_mps2,B)[0]
    low=-c.brake_mps2
    if allowance < -ROUNDING_M or envelope(low)>allowance+ROUNDING_M:
        raise ViabilityError('no robustly certified control under the declared information/bounds')
    if envelope(desired)<=allowance:return desired
    if envelope(low)>allowance:return low  # at most ROUNDING_M numerical residual
    high=desired
    for _ in range(56):
        mid=(low+high)/2
        if envelope(mid)<=allowance:low=mid
        else:high=mid
    return low


def step(state,reports,leader_accels,dt,cap,B):
    """Immutable push-forward; infeasible decisions preserve the entire input.

    Leader controls are external scenario inputs. This closes a conditional pair
    problem but does not derive the leader's acceleration from the same ensemble.
    """
    if len(reports)!=len(state.bins) or len(leader_accels)!=len(state.bins):
        raise ValueError('one report/control per conditional bin required')
    if not math.isfinite(dt) or dt<=0 or not math.isfinite(B) or B<=0:
        raise ValueError('invalid control interval or leader braking bound')
    if any(not math.isfinite(a) or a < -B for a in leader_accels):
        raise ValueError('leader control violates declared lower acceleration bound')
    out=[];proof=[]
    try:
        for p,r,aL in zip(state.bins,reports,leader_accels):
            wlow=lower_speed(r,state.time_s,B)
            # Validate the declared exact sensor contract outside the controller.
            # With zero age, no acceleration uncertainty can change the report.
            # Stale reports retain only the stated one-sided acceleration bound.
            if (r is not None and r.stamp_s==state.time_s
                    and not math.isclose(r.speed_mps,p.w,rel_tol=0.,abs_tol=1e-10)):
                raise ValueError('current exact report contradicts physical leader speed')
            if p.w+1e-10<wlow:
                raise ValueError('physical leader contradicts admitted report/braking bound')
            a=control(p,r,state.time_s,dt,cap,B)
            dx,v=motion(p.v,a,dt);dl,w=motion(p.w,aL,dt)
            closing,at=interval_closure(p.v,p.w,a,aL,dt)
            minimum=p.h-closing
            if minimum<p.vehicle.min_gap_m-ROUNDING_M:
                raise ArithmeticError('applied trajectory violates certified minimum gap')
            h=p.h+dl-dx
            out.append(replace(p,h=h,v=v,w=w,x=p.x+dx))
            proof.append(dict(min_gap_m=minimum,min_gap_time_s=state.time_s+at,
                              acceleration_mps2=a,leader_lower_mps=wlow,
                              projected_closure_m=maximum_closure(p.v,wlow,a,dt,p.vehicle.brake_mps2,B)[0]))
    except (ViabilityError,ValueError,ArithmeticError) as exc:
        exc.checkpoint=state
        raise
    return PairState(state.time_s+dt,tuple(out)),tuple(proof)


def moments(state):
    """Only follower mass is inventoried; preserve bins/classes in the state."""
    total=math.fsum(p.mass for p in state.bins)
    if total==0:return dict(mass=0.,mean_v=0.,variance_v=0.,mean_h=0.)
    v=math.fsum(p.mass*p.v for p in state.bins)/total
    return dict(mass=total,mean_v=v,
                variance_v=math.fsum(p.mass*(p.v-v)**2 for p in state.bins)/total,
                mean_h=math.fsum(p.mass*p.h for p in state.bins)/total)
