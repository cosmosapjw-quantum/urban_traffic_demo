"""Exact constant-control kinematics and projected braking, SI units.

Speeds saturate at zero, not at a road speed cap. Breakpoints and interior
relative-speed zeros give the maximum closure; final stopping positions alone
are insufficient. This is not an empirical safety certification.
"""
import math


def motion(v,a,t):
    """Distance and speed under constant acceleration until rest, then rest."""
    if not all(map(math.isfinite,(v,a,t))) or v<0 or t<0:
        raise ValueError('finite v>=0, t>=0 and acceleration required')
    q=min(t,v/(-a)) if a<0 else t
    return v*q+.5*a*q*q,max(0.,v+a*q)


def hold_brake(v,a,dt,b,t):
    """Hold acceleration a for dt, then brake at b>0 until rest."""
    if not all(map(math.isfinite,(dt,b,t))) or dt<0 or b<=0 or t<0:
        raise ValueError('invalid hold/braking clock')
    x,w=motion(v,a,min(t,dt))
    if t<=dt:return x,w
    y,z=motion(w,-b,t-dt)
    return x+y,z


def _extreme(relative,breaks):
    points=sorted(set(breaks));candidates=list(points)
    for lo,hi in zip(points,points[1:]):
        d0=relative(lo)[1];d1=relative(hi)[1]
        if d1!=d0:
            root=lo-d0*(hi-lo)/(d1-d0)
            if lo<root<hi:candidates.append(root)
    # Earliest witness on an exactly flat maximum is deterministic.
    return max(((relative(t)[0],-t) for t in candidates),key=lambda p:(p[0],p[1]))


def maximum_closure(v,w,a,dt,b,B):
    """sup_{t>=0}(follower displacement - worst-braking leader displacement).

    Leader initial speed w is a conservative lower bound. Follower control is
    held, then fallback full braking; the leader brakes immediately at B>0.
    """
    if not all(map(math.isfinite,(v,w,a,dt,b,B))) or min(v,w,dt)<0 or min(b,B)<=0:
        raise ValueError('invalid braking envelope')
    vh=motion(v,a,dt)[1]
    cuts=[0.,dt,w/B,dt+vh/b]
    if a<0 and 0<v/(-a)<dt:cuts.append(v/(-a))
    def relative(t):
        xf,vf=hold_brake(v,a,dt,b,t);xl,vl=motion(w,-B,t)
        return xf-xl,vf-vl
    value,negative_time=_extreme(relative,cuts)
    return max(0.,value),-negative_time


def interval_closure(v,w,a,leader_accel,dt):
    """Exact maximum closing displacement during one applied-control interval."""
    if not math.isfinite(dt) or dt<0:raise ValueError('invalid interval')
    motion(v,a,dt);motion(w,leader_accel,dt)
    cuts=[0.,dt]
    for speed,accel in ((v,a),(w,leader_accel)):
        if accel<0 and 0<speed/(-accel)<dt:cuts.append(speed/(-accel))
    def relative(t):
        xf,vf=motion(v,a,t);xl,vl=motion(w,leader_accel,t)
        return xf-xl,vf-vl
    value,negative_time=_extreme(relative,cuts)
    return max(0.,value),-negative_time


def passage_in_interval(v,a,distance,dt):
    """First hit on the same applied trajectory; None means not yet reached."""
    if not math.isfinite(distance) or distance<0:raise ValueError('invalid passage distance')
    total,_=motion(v,a,dt)
    if distance==0:return 0.
    if distance>total:return None
    # Stable quadratic root; stopping plateau uses its FIRST arrival, not dt.
    if a==0:return distance/v
    discriminant=max(0.,v*v+2*a*distance)
    return 2*distance/(v+math.sqrt(discriminant))
