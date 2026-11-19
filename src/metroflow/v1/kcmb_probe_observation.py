"""Six-moment exact affine probe-selection observation maps (research only).

The declared weights model a hypothetical inclusion intensity for each
latent control sigma and realised dimensionless velocity u=v/U. This is
not an implementation of the Chicago Traffic Tracker's unspecified bus-GPS
aggregation. Observation maps are pure read-only functions of the existing
KCMB physical micro-kinetic moment projection.

For each physical class, the 6-tuple is (m0,m1,j0,j1,z0,z1), where each field
has vehicle-equivalent units and j,z carry dimensionless velocity moments.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from .kcmb import _validate_class_moments


@dataclass(frozen=True, slots=True)
class AffineProbeWeights:
    """Hypothetical nonnegative w_sigma(u)=a_sigma+b_sigma*u, u in [0,1]."""

    a0: float = 1.0
    b0: float = 0.0
    a1: float = 1.0
    b1: float = 0.0

    def __post_init__(self) -> None:
        for key in ("a0", "b0", "a1", "b1"):
            value=getattr(self,key)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
                raise ValueError("finite numerical probe weight required")
            object.__setattr__(self,key,float(value))
        for a,b in ((self.a0,self.b0),(self.a1,self.b1)):
            if a<0 or a+b<0:
                raise ValueError("probe weight must be nonnegative at u=0 and u=1")


def _terms(moments, vmax_mps: float, weights: AffineProbeWeights):
    if not isinstance(weights,AffineProbeWeights):
        raise ValueError("registered affine probe weights required")
    if (isinstance(vmax_mps,bool) or
        not isinstance(vmax_mps,(int,float)) or
        not math.isfinite(vmax_mps) or vmax_mps<=0):
        raise ValueError("finite positive physical maximum speed required")
    try:
        field=tuple(float(x) for x in moments)
    except (TypeError,ValueError,OverflowError) as exc:
        raise ValueError("invalid six kinetic moment fields") from exc
    if len(field)!=6:
        raise ValueError("six conditioned kinetic moment fields required")
    m0,m1,j0,j1,z0,z1=field
    _validate_class_moments(field,1e-12*max(1.,m0+m1))
    denominator=math.fsum((weights.a0*m0,weights.b0*j0,
                           weights.a1*m1,weights.b1*j1))
    numerator=math.fsum((weights.a0*j0,weights.b0*z0,
                         weights.a1*j1,weights.b1*z1))
    if not math.isfinite(denominator) or not math.isfinite(numerator):
        raise ValueError("nonfinite probe support or weighted moment")
    if denominator < -1e-12 or numerator < -1e-12 or (
            numerator > denominator + 1e-11*max(1.,denominator)):
        raise ValueError("probe moment violates realizability/support")
    return float(vmax_mps)*max(0.,numerator),max(0.,denominator)


def selected_probe_mean_speed(moments, vmax_mps: float, weights: AffineProbeWeights) -> float:
    """Instantaneous selected speed [m/s] if probe support >0; else refuse."""
    numerator,denominator=_terms(moments,vmax_mps,weights)
    if denominator<=0:
        raise ValueError("no positive probe support in this kinetic state")
    value=numerator/denominator
    if value<-1e-12 or value>vmax_mps+1e-11*max(1.,vmax_mps):
        raise ValueError("probe selected speed outside physical support")
    return min(float(vmax_mps),max(0.,value))


def pooled_probe_mean_speed(states: Iterable[tuple[tuple[float,...],float,AffineProbeWeights]]) -> float:
    """Support-weighted *pooled* selected mean over cells and physical classes.

    The tuples are (six moments, speed parameter [m/s], class observation
    weight). Empty/zero-support cells are omitted, not treated as zero-speed.
    """
    numerators=[]
    denominators=[]
    for moments,U,weights in states:
        numerator,denominator=_terms(moments,U,weights)
        numerators.append(numerator)
        denominators.append(denominator)
    if not denominators or math.fsum(denominators)<=0:
        raise ValueError("no positive probe support across pooled observations")
    return math.fsum(numerators)/math.fsum(denominators)


def stationary_six_moments(
    p: float,k_per_s: float,tau_s: float,*,mass: float=1.
) -> tuple[float,float,float,float,float,float]:
    """Exact stationary local Markov six moments (frozen rates; no transport)."""
    for name,value in (
        ("p",p),("k",k_per_s),("tau",tau_s),("mass",mass)
    ):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            raise ValueError(f"finite stationary kinetic {name} required")
    if not 0<=p<=1 or k_per_s<=0 or tau_s<=0 or mass<0:
        raise ValueError("stationary kinetic parameters outside physical bounds")
    scaled_k=k_per_s*tau_s
    scaled_alpha=k_per_s*p*tau_s
    if not all(map(math.isfinite,(scaled_k,scaled_alpha))):
        raise ValueError("stationary kinetic product overflow")
    j1=p*(1+scaled_alpha)/(1+scaled_k)
    j0=p-j1
    z1=j1*(2+scaled_alpha)/(2+scaled_k)
    z0=j1-z1
    out=(mass*(1-p),mass*p,mass*j0,mass*j1,mass*z0,mass*z1)
    _validate_class_moments(out,1e-12*max(1.,mass))
    return out
