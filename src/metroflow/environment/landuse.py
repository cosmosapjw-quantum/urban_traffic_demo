"""Finite urban stocks; capacities are persons/jobs, not traffic flow."""
from dataclasses import dataclass
from .terrain import Terrain, Network

@dataclass(frozen=True,slots=True)
class Zone:
    id: str
    x_m: float
    y_m: float
    area_m2: float
    net_area_m2: float
    slope: float
    use: str
    access_node: str|None
    housing_capacity: int
    job_capacity: int
    service_capacity: int
    residents: int=0
    jobs: int=0

@dataclass(frozen=True,slots=True)
class City:
    terrain: Terrain
    network: Network
    zones: tuple[Zone,...]
    population: int
    jobs: int

import math
from dataclasses import replace
from collections import Counter
from .terrain import Rect, overlaps, cell_slope, node_id, validate_terrain


def apportion(total: int, capacities: tuple[int,...], weights: tuple[float,...]) -> tuple[int,...]:
    """Capped water-filling followed by largest remainders; O(Z^2), not O(population)."""
    if isinstance(total,bool) or not isinstance(total,int) or total<0:
        raise ValueError('total must be a nonnegative integer stock')
    if len(capacities)!=len(weights) or not capacities:
        raise ValueError('capacity/weight shape')
    if any(isinstance(c,bool) or not isinstance(c,int) or c<0 for c in capacities):
        raise ValueError('capacities must be nonnegative integer stocks')
    if any(not math.isfinite(w) or w<0 for w in weights):
        raise ValueError('weights must be finite and nonnegative')
    active={i for i,(c,w) in enumerate(zip(capacities,weights)) if c>0 and w>0}
    if total>sum(capacities[i] for i in active):raise ValueError('insufficient eligible capacity')
    expected=[0.]*len(capacities);left=float(total)
    while active and left>0:
        sw=math.fsum(weights[i] for i in sorted(active))
        bound=[i for i in sorted(active) if left*weights[i]/sw>=capacities[i]]
        if not bound:
            for i in sorted(active):expected[i]=left*weights[i]/sw
            break
        for i in bound:expected[i]=float(capacities[i]);left-=capacities[i];active.remove(i)
    out=[min(c,math.floor(x)) for c,x in zip(capacities,expected)]
    extra=total-sum(out)
    order=sorted((i for i in range(len(out)) if out[i]<capacities[i] and weights[i]>0),
                 key=lambda i:(-(expected[i]-out[i]),i))
    if extra<0 or extra>len(order):raise ArithmeticError('apportionment roundoff outside ledger')
    for i in order[:extra]:out[i]+=1
    assert sum(out)==total
    return tuple(out)


def zone_city(terrain: Terrain, network: Network, population: int, jobs: int,
              max_build_slope=.10) -> City:
    """Coarse land-use envelope, not parcels/real-estate equilibrium.

    Any overlap with excluded land removes the WHOLE raster cell, a conservative
    rule. Net area is 65% of the surviving cell (authored road/open-space reserve).
    Housing/job densities per net hectare are fixed priors and never rescaled to
    force a requested population to fit. The largest road component is the urban
    service area; other components remain in the graph and are reported.
    """
    t=terrain;validate_terrain(t)
    if not math.isfinite(max_build_slope) or max_build_slope<=0:raise ValueError('invalid build slope')
    extent=t.n*t.spacing_m; comps=dict(network.components)
    sizes=Counter(comps.values())
    if not sizes:raise ValueError('no road access')
    main=min(sizes,key=lambda c:(-sizes[c],c))
    degree=Counter(v for e in network.links for v in (e.u,e.v))
    eligible={v for v,c in comps.items() if c==main and degree[v]>0}
    centres=((.25*extent,.5*extent),(.75*extent,.42*extent))
    industry=Rect(.70*extent,0.,extent,.21*extent)
    industrial_cells=tuple(Rect(x*t.spacing_m,y*t.spacing_m,(x+1)*t.spacing_m,(y+1)*t.spacing_m)
        for y in range(t.n) for x in range(t.n)
        if industry.xmin<=(x+.5)*t.spacing_m<=industry.xmax and
           industry.ymin<=(y+.5)*t.spacing_m<=industry.ymax)
    # persons, jobs, visitor places per net hectare. Not observed calibration.
    density={'residential':(230,15,15),'mixed':(340,250,75),
             'commercial':(0,550,120),'industrial':(0,180,0),'civic':(0,90,220)}
    raw=[];weights=[]
    for y in range(t.n):
        for x in range(t.n):
            r=Rect(x*t.spacing_m,y*t.spacing_m,(x+1)*t.spacing_m,(y+1)*t.spacing_m)
            px=(x+.5)*t.spacing_m;py=(y+.5)*t.spacing_m;slope=cell_slope(t,x,y)
            access=sorted(node_id(i,j) for i,j in ((x,y),(x+1,y),(x,y+1),(x+1,y+1))
                          if node_id(i,j) in eligible)
            near=min(math.hypot(px-a,py-b) for a,b in centres)
            if any(overlaps(r,w) for w in t.water):use='water'
            elif any(overlaps(r,p) for p in t.protected):use='protected'
            elif any(overlaps(r,w,50.) for w in t.water):use='floodplain'
            elif slope>max_build_slope:use='steep'
            elif not access:use='inaccessible'
            elif industry.xmin<=px<=industry.xmax and industry.ymin<=py<=industry.ymax:use='industrial'
            elif any(overlaps(r,p,150.) for p in industrial_cells):use='buffer'
            elif x==1 and y==t.n//2:use='civic'
            elif near<.085*extent:use='commercial'
            elif near<.20*extent:use='mixed'
            elif (x+2*y)%13==0:use='park'
            else:use='residential'
            net=.65*t.spacing_m**2 if use in density else 0.
            cap=tuple(math.floor(d*net/10000.) for d in density.get(use,(0,0,0)))
            raw.append(Zone(f'z{x}:{y}',px,py,t.spacing_m**2,net,slope,use,
                            access[0] if access and net>0 else None,*cap))
            weights.append((.2+math.exp(-near/max(1.,.3*extent)))/(1+5*slope))
    residents=apportion(population,tuple(z.housing_capacity for z in raw),
                        tuple(w*z.housing_capacity for z,w in zip(raw,weights)))
    employment=apportion(jobs,tuple(z.job_capacity for z in raw),
                        tuple(w*z.job_capacity for z,w in zip(raw,weights)))
    zones=tuple(replace(z,residents=p,jobs=j) for z,p,j in zip(raw,residents,employment))
    return City(t,network,zones,population,jobs)
