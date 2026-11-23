"""RankMarkFlow-v0: exact-rational marked cumulative FIFO link, RESEARCH SHADOW ONLY.

This is a distinct scientific representation. It neither replaces MetroFlow native
road nor promises IEEE wire identity. All per-span marks remain explicit; finite
response is an admission bound on prefix service, not a reordered filter.
"""
from __future__ import annotations
from bisect import bisect_right
from dataclasses import dataclass
from fractions import Fraction

MODEL_VERSION = "rank_marked_flow_v0_exact_rational"
FIELDS = ("vehicles", "persons", "cargo_kg", "birth_vehicle_s")


def q(x):
    if isinstance(x, (bool, float)):
        raise TypeError("use exact int or Fraction, never f64 literals")
    return Fraction(x)


@dataclass(frozen=True)
class MarkSpan:
    vehicles: Fraction
    persons_per_vehicle: Fraction
    cargo_kg_per_vehicle: Fraction
    birth_s: Fraction
    ready_s: Fraction
    route: str
    vehicle_class: str

    def __post_init__(self):
        for k in ("vehicles", "persons_per_vehicle", "cargo_kg_per_vehicle", "birth_s", "ready_s"):
            v=getattr(self,k)
            if not isinstance(v,Fraction) or v<0:
                raise ValueError(f"{k} must be a nonnegative exact rational")
        if self.vehicles<=0 or not self.route or not self.vehicle_class:
            raise ValueError("positive source mass and nonblank route/class required")

    def rate(self):
        return (Fraction(1),self.persons_per_vehicle,
                self.cargo_kg_per_vehicle,self.birth_s)


def vec_add(a,b):
    return tuple(x+y for x,y in zip(a,b))


def vec_sub(a,b):
    return tuple(x-y for x,y in zip(a,b))


def vec_mul(a,c):
    return tuple(x*c for x in a)


class CumulativeMarkedFIFO:
    """Append-only input mark spans; serving advances one scalar rank endpoint."""

    def __init__(self):
        self._edges=[Fraction(0)]
        self._spans=[]
        self._prefix=[(Fraction(0),)*len(FIELDS)]
        self._departed=Fraction(0)

    @property
    def entered_rank(self):
        return self._edges[-1]

    @property
    def departed_rank(self):
        return self._departed

    @property
    def source_span_count(self):
        return len(self._spans)

    def enter(self,span:MarkSpan):
        if not isinstance(span,MarkSpan):
            raise TypeError("requires explicit MarkSpan")
        last=self._edges[-1]
        self._spans.append(span)
        self._edges.append(last+span.vehicles)
        self._prefix.append(vec_add(self._prefix[-1],vec_mul(span.rate(),span.vehicles)))

    def prefix(self,rank):
        rank=q(rank)
        if rank<0 or rank>self.entered_rank:
            raise ValueError("prefix beyond entered rank")
        if rank==self.entered_rank:
            return self._prefix[-1]
        k=bisect_right(self._edges,rank)-1
        return vec_add(self._prefix[k],
                       vec_mul(self._spans[k].rate(),rank-self._edges[k]))

    def stock(self):
        return vec_sub(self.prefix(self.entered_rank),self.prefix(self._departed))

    def arrived(self):
        return self.prefix(self.entered_rank)

    def exited(self):
        return self.prefix(self._departed)

    def ready_prefix(self,clock_s):
        clock_s=q(clock_s)
        limit=self._departed
        k=bisect_right(self._edges,limit)-1
        while k<len(self._spans):
            if self._spans[k].ready_s>clock_s:
                return limit
            limit=self._edges[k+1]
            k+=1
        return limit

    def serve(self,vehicles,clock_s):
        vehicles=q(vehicles)
        if vehicles<0 or vehicles>self.entered_rank-self._departed:
            raise ValueError("invalid offered FIFO mass")
        if self._departed+vehicles>self.ready_prefix(clock_s):
            raise ValueError("finite-response/FIFO prefix not eligible")
        before=self._departed
        after=before+vehicles
        flux=vec_sub(self.prefix(after),self.prefix(before))
        self._departed=after
        return flux

    def outgoing_marks(self,left,right):
        """Explicit route-mark expansion only when a consumer requests it."""
        left=q(left);right=q(right)
        if not (0<=left<=right<=self.entered_rank):
            raise ValueError("invalid source rank interval")
        ans=[]
        k=max(0,bisect_right(self._edges,left)-1)
        while k<len(self._spans) and self._edges[k]<right:
            lo=max(left,self._edges[k])
            hi=min(right,self._edges[k+1])
            if lo<hi:
                ans.append((hi-lo,self._spans[k]))
            k+=1
        return ans
