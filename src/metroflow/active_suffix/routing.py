"""Nonnegative shortest-time potentials on legal directed-link states.

Routing and transport potentials are NOT a thermodynamic potential or a system
optimum. Candidate enumeration is loopless and reports its computation bound.
"""
from dataclasses import dataclass
import heapq
import math

@dataclass(frozen=True, slots=True)
class Arc:
    id: str
    tail: str
    head: str

@dataclass(frozen=True, slots=True)
class SearchResult:
    paths: tuple[tuple[str,...],...]
    expanded: int
    truncated: bool


def _tables(arcs,allowed_turns):
    arcs=tuple(arcs); ids={e.id:e for e in arcs}
    if len(ids)!=len(arcs): raise ValueError('duplicate links')
    bytail={}
    for e in arcs: bytail.setdefault(e.tail,[]).append(e.id)
    succ={e.id:tuple(sorted(j for j in bytail.get(e.head,())
              if ((e.id,j) in allowed_turns if allowed_turns is not None else ids[j].head!=e.tail))) for e in arcs}
    return ids,bytail,succ


def destination_potential(arcs,costs,destination,allowed_turns=None):
    ids,_,succ=_tables(arcs,allowed_turns)
    if any(e not in costs or math.isnan(costs[e]) or costs[e]<0 for e in ids):
        raise ValueError('costs must be nonnegative seconds, +infinity means unavailable')
    pred={e:[] for e in ids}
    for i,js in succ.items():
        for j in js: pred[j].append(i)
    V={e:math.inf for e in ids}; heap=[]
    for e,arc in ids.items():
        if arc.head==destination and math.isfinite(costs[e]):
            V[e]=costs[e]; heapq.heappush(heap,(V[e],e))
    while heap:
        val,j=heapq.heappop(heap)
        if val!=V[j]: continue
        for i in pred[j]:
            alt=costs[i]+val
            if alt<V[i]: V[i]=alt; heapq.heappush(heap,(alt,i))
    return V


def candidate_paths(arcs,costs,origin,destination,k=3,expansion_budget=2000,allowed_turns=None):
    if k<1 or expansion_budget<0: raise ValueError('invalid route search budget')
    ids,bytail,succ=_tables(arcs,allowed_turns)
    V=destination_potential(arcs,costs,destination,allowed_turns)
    heap=[]
    for i in sorted(bytail.get(origin,())):
        if math.isfinite(V[i]): heapq.heappush(heap,(V[i],costs[i],(i,),(origin,ids[i].head)))
    found=[]; expanded=0
    while heap and expanded<expansion_budget and len(found)<k:
        _,cost,path,visited=heapq.heappop(heap); expanded+=1; i=path[-1]
        if ids[i].head==destination:
            found.append(path); continue
        for j in succ[i]:
            if ids[j].head in visited or not math.isfinite(V[j]): continue
            nextcost=cost+costs[j]
            heapq.heappush(heap,(cost+V[j],nextcost,path+(j,),visited+(ids[j].head,)))
    return SearchResult(tuple(found),expanded,bool(heap and expanded>=expansion_budget and len(found)<k))


def braess_reference(demand=4000.,shortcut=False,iterations=1000):
    """Static nonatomic selfish assignment (MSA), NOT dynamic-solver validation.

    Units are deliberately minutes in this isolated classical oracle. The main
    simulator uses metres and seconds. No path is removed to suppress paradoxes.
    """
    if demand<=0 or iterations<1: raise ValueError('invalid assignment experiment')
    arcs=(Arc('oa','O','A'),Arc('ad','A','D'),Arc('ob','O','B'),Arc('bd','B','D'))
    if shortcut: arcs+=(Arc('ab','A','B'),)
    x={e.id:0. for e in arcs}
    def cost(): return {e.id:(x[e.id]/100 if e.id in ('oa','bd') else 0. if e.id=='ab' else 45.) for e in arcs}
    for iteration in range(1,iterations+1):
        C=cost(); path=candidate_paths(arcs,C,'O','D',1).paths[0]; eta=1/iteration
        for e in x: x[e]=(1-eta)*x[e]+eta*(demand if e in path else 0.)
    C=cost(); total=math.fsum(x[e]*C[e] for e in x)
    shortest=min(destination_potential(arcs,C,'D')[e.id] for e in arcs if e.tail=='O')
    return dict(demand=demand,shortcut=shortcut,flow=x,mean_cost_min=total/demand,
                shortest_cost_min=shortest,relative_wardrop_gap=max(0.,(total-demand*shortest)/total))
