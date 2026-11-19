"""Sharp no-fit affine probe-speed interval from positive six-moment traffic states.

Given a fixed physically realizable kinetic measure, optimize over the ENTIRE
cone of nonnegative affine selection laws. No CTA weights or driver parameters
are fitted. This is an observation-model sensitivity theorem, not measured GPS
instrument calibration. Mixed classes share one common hypothetical law.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from .kcmb import _validate_class_moments

_NAMES=("sigma0_at_u0","sigma0_at_u1","sigma1_at_u0","sigma1_at_u1")


@dataclass(frozen=True, slots=True)
class AffineProbeSpeedEnvelope:
    min_speed_mps: float
    max_speed_mps: float
    vertex_speeds_mps: tuple[float|None,float|None,float|None,float|None]
    supported_vertices: tuple[str,...]
    vertex_support_veh: tuple[float,float,float,float]
    population_mean_speed_mps: float
    claim_scope: str = "sharp_over_all_nonnegative_common_affine_weights_given_six_moments"


def _contributions(moments, U):
    try:
        y=tuple(float(x) for x in moments)
    except (TypeError,ValueError,OverflowError) as exc:
        raise ValueError("six numerical kinetic moments required") from exc
    if len(y)!=6:
        raise ValueError("expected six kinetic moment fields")
    if (isinstance(U,bool) or not isinstance(U,(int,float)) or
        not math.isfinite(U) or U<=0):
        raise ValueError("finite positive physical speed scale required")
    _validate_class_moments(y,1e-12*max(1.,sum(y[:2])))
    m0,m1,j0,j1,z0,z1=y
    ds=(m0-j0,j0,m1-j1,j1)
    ns=(U*(j0-z0),U*z0,U*(j1-z1),U*z1)
    if any(not math.isfinite(a) or not math.isfinite(b) for a,b in zip(ds,ns)):
        raise ValueError("nonfinite selected-probe numerator or support")
    # Do not use a sampling cutoff: all strictly positive supports participate.
    # A negative tiny cancellation is evidence of a numerically unresolved
    # moment, never a physical zero.
    if any(a < 0 or b < 0 for a,b in zip(ds,ns)):
        raise ValueError("negative endpoint probe support/moment")
    return ds,ns,U*(j0+j1),m0+m1


def _combine(parts):
    denom=[[],[],[],[]]
    numer=[[],[],[],[]]
    raw_num=[]
    raw_den=[]
    for ds,ns,unweighted,mass in parts:
        for j in range(4):
            denom[j].append(ds[j]); numer[j].append(ns[j])
        raw_num.append(unweighted);raw_den.append(mass)
    support=tuple(math.fsum(v) for v in denom)
    selected=tuple(math.fsum(v) for v in numer)
    if math.fsum(support)<=0:
        raise ValueError("no positive probe support in these kinetic states")
    values=[]
    for d,n in zip(support,selected):
        if d<=0:
            if n!=0:
                raise ValueError("zero-support probe has a nonzero selected moment")
            values.append(None)
            continue
        v=n/d
        if v<0 or not math.isfinite(v):
            raise ValueError("nonphysical selected probe speed")
        values.append(v)
    supported=[x for x in values if x is not None]
    total_mass=math.fsum(raw_den)
    if total_mass<=0:
        raise ValueError("positive vehicle mass needed")
    return AffineProbeSpeedEnvelope(
        min(supported),max(supported),tuple(values),
        tuple(name for name,val in zip(_NAMES,values) if val is not None),
        support,math.fsum(raw_num)/total_mass
    )


def affine_probe_speed_envelope(moments, U:float)->AffineProbeSpeedEnvelope:
    """Exact sharp [lower,upper] over ALL nonnegative class-affine probe laws."""
    return _combine((_contributions(moments,U),))


def pooled_affine_probe_speed_envelope(
    states:Iterable[tuple[tuple[float,...],float]]
)->AffineProbeSpeedEnvelope:
    """One common unknown affine probe law over all cells/classes."""
    return _combine(_contributions(y,U) for y,U in states)
