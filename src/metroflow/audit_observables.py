"""Explicit observation and necessary realizability audits (SI units, stdlib).

These functions diagnose model assumptions. They do not silently modify traffic
physics or certify empirical realism. Every stationary conversion below assumes
positive constant class speeds on a homogeneous link.
"""
import cmath
import math
from collections import defaultdict


def speed_measure(speeds, weights, length_m, *, measure):
    """Convert stationary spatial-density vs entrance-flow weights explicitly.

    A stopped atom prevents the invertible stationary conversion used here and
    is rejected, not silently removed. Finite transient cohorts need their own
    first-passage calculation and are outside this identity.
    """
    speeds, weights = tuple(speeds), tuple(weights)
    if (not speeds or len(speeds) != len(weights)
            or any(not math.isfinite(v) or v <= 0 for v in speeds)):
        raise ValueError('stationary conversion needs positive finite speeds')
    if (any(not math.isfinite(w) or w < 0 for w in weights)
            or math.fsum(weights) <= 0 or not math.isfinite(length_m) or length_m < 0):
        raise ValueError('invalid observation weights or length')
    total = math.fsum(weights)
    p = tuple(w/total for w in weights)
    if measure == 'space':
        space = p
        mean = math.fsum(w*v for w,v in zip(space,speeds))
        entry = tuple(w*v/mean for w,v in zip(space,speeds))
    elif measure == 'entry':
        entry = p
        inv = math.fsum(w/v for w,v in zip(entry,speeds))
        space = tuple((w/v)/inv for w,v in zip(entry,speeds))
        mean = 1./inv
    else:
        raise ValueError("measure must be 'space' or 'entry'")
    return dict(space_weights=space, entry_weights=entry, space_mean_mps=mean,
                time_mean_mps=math.fsum(w*v for w,v in zip(entry,speeds)),
                mean_entry_trip_s=math.fsum(w*length_m/v for w,v in zip(entry,speeds)),
                scope='stationary homogeneous positive-speed mixture')


def edie_observables(vehicle_seconds, vehicle_metres, length_m, duration_s):
    """Observations on ONE fixed road-space/time rectangle, not source waiting.

    Numerators are residence and distance accumulated inside that rectangle.
    In a vacuum the speed is undefined (None), not zero-speed stopped traffic.
    """
    if (any(not math.isfinite(x) or x < 0 for x in (vehicle_seconds,vehicle_metres))
            or any(not math.isfinite(x) or x <= 0 for x in (length_m,duration_s))):
        raise ValueError('invalid observation rectangle or integrals')
    if vehicle_seconds == 0 and vehicle_metres != 0:
        raise ValueError('nonzero distance with zero residence')
    area=length_m*duration_s
    return dict(density_veh_m=vehicle_seconds/area, flow_veh_s=vehicle_metres/area,
                space_time_mean_mps=vehicle_metres/vehicle_seconds if vehicle_seconds else None)


def ring_requirements(masses,gaps,follower_speeds,leader_speeds,vehicle_length_m,lane_length_m):
    """Necessary checks for one homogeneous closed single-lane periodic ensemble.

    Each follower occurs once, each vehicle is also somebody's leader; therefore
    velocity marginals match and the sum of gaps plus vehicle lengths is the lane
    length. Equal marginals do NOT prove a spatial cycle realization. Exact speed
    bins are compared here; no hidden smoothing or tolerance-bin merge is used.
    Conditional pair experiments must not be relabelled as this ensemble.
    """
    arrays=tuple(map(tuple,(masses,gaps,follower_speeds,leader_speeds)))
    m,h,v,w=arrays
    if (not m or any(len(a)!=len(m) for a in arrays)
            or any(not math.isfinite(x) or x<0 for a in arrays for x in a)
            or any(not math.isfinite(x) or x<=0 for x in (vehicle_length_m,lane_length_m))):
        raise ValueError('invalid homogeneous ring inputs')
    mass=math.fsum(m)
    if mass<=0:raise ValueError('nonempty ring mass required')
    required=math.fsum(mi*(hi+vehicle_length_m) for mi,hi in zip(m,h))
    vf,vl=defaultdict(float),defaultdict(float)
    for mi,vi,wi in zip(m,v,w):vf[vi]+=mi/mass;vl[wi]+=mi/mass
    residual=math.fsum(abs(vf[s]-vl[s]) for s in vf.keys()|vl.keys())
    length_ok=abs(required-lane_length_m)<=1e-10*max(1.,required,lane_length_m)
    return dict(represented_count=mass, required_lane_length_m=required,
                supplied_lane_length_m=lane_length_m, length_consistent=length_ok,
                velocity_marginal_l1=residual,
                necessary_conditions_pass=length_ok and residual<=1e-12,
                sufficient_realizability_proved=False)


def ovm_modes(optimal_speed_slope_per_s,response_s,wavenumber,relative_speed_gain_s=0.):
    """Continuous-time, homogeneous-ring, safety-inactive nominal linearization.

    dv_i/dt=(U(h_i)-v_i)/tau + gamma*(v_next-v_i).
    tau*lambda^2 + [1-tau*gamma*(exp(ik)-1)]*lambda
        - U'(h)*(exp(ik)-1)=0.
    This does not linearize the sampled robust filter or delayed observations.
    """
    a,tau,k,gamma=optimal_speed_slope_per_s,response_s,wavenumber,relative_speed_gain_s
    if (not all(map(math.isfinite,(a,tau,k,gamma))) or a<0 or tau<=0 or gamma<0):
        raise ValueError('invalid nominal stability parameters')
    delta=cmath.exp(1j*k)-1
    bb=1.-tau*gamma*delta
    root=cmath.sqrt(bb*bb+4*tau*a*delta)
    modes=((-bb+root)/(2*tau),(-bb-root)/(2*tau))
    return dict(modes_per_s=tuple((z.real,z.imag) for z in modes),
                largest_real_part_per_s=max(z.real for z in modes),
                longwave_real_k2_coefficient_per_s=tau*a*a-tau*gamma*a-a/2,
                scope='nominal unconstrained continuous-time conditional linearization')
