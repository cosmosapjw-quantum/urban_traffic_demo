"""Bounded, chronology-respecting subdivision of large simple street faces.

A cut is one new straight street between existing junctions.  No intersection is
invented at an unregistered crossing.  Old roads, their dates and hierarchy are
preserved. This is a local construction heuristic, not an urban equilibrium.
"""
from __future__ import annotations

import math
from typing import Sequence

from .formative_growth_model import FormationConfig, FormationNode, FormationEdge
from .formative_growth_network import segments_cross
from .formative_growth_analysis import _bounded_face_walks, _polygon_area


def _inside(x: float, y: float, points: Sequence[tuple[float,float]]) -> bool:
    inside = False
    for (ax,ay),(bx,by) in zip(points, points[1:]+points[:1], strict=True):
        if (ay > y) != (by > y) and x < ax+(y-ay)*(bx-ax)/(by-ay):
            inside = not inside
    return inside


def _boundary_edges(nodes, edges):
    """Strip graph bridges for boundary traversal ONLY, never from the city.

    DFS low-link bridge detection is O(V+E); an explicit stack avoids dependence
    on Python's recursion limit. All originals still veto crossing candidates.
    """
    adj=[[] for _ in nodes]
    for idx,e in enumerate(edges):
        adj[e.u].append((e.v,idx)); adj[e.v].append((e.u,idx))
    discovered={}; low={}; bridges=set(); clock=0
    for root in range(len(nodes)):
        if root in discovered:
            continue
        discovered[root]=low[root]=clock; clock+=1
        stack=[(root,-1,-1,iter(adj[root]))]
        while stack:
            u,parent,parent_edge,children=stack[-1]
            try:
                v,ei=next(children)
            except StopIteration:
                stack.pop()
                if parent>=0:
                    low[parent]=min(low[parent],low[u])
                    if low[u]>discovered[parent]:
                        bridges.add(parent_edge)
                continue
            if ei==parent_edge:
                continue
            if v in discovered:
                low[u]=min(low[u],discovered[v])
            else:
                discovered[v]=low[v]=clock; clock+=1
                stack.append((v,u,ei,iter(adj[v])))
    return [e for i,e in enumerate(edges) if i not in bridges]


def insert_infill_chords(
    cfg: FormationConfig,
    nodes: Sequence[FormationNode],
    edges: Sequence[FormationEdge],
) -> list[FormationEdge]:
    """Add at most ``infill_budget`` large-face cuts at the final epoch.

    Each cut raises E-V+C and the raw bounded-face count by one. Child areas
    sum to the parent area. Bridge walks are removed from boundary enumeration only, with their
    streets preserved as geometric obstacles. Parcel creation and edge-interior junctions are not
    part of this bounded operator.
    """
    out = list(edges)
    for _ in range(cfg.infill_budget):
        degree = [0]*len(nodes)
        existing = set()
        for e in out:
            degree[e.u] += 1; degree[e.v] += 1
            existing.add(e.key)
        faces = []
        for cycle in _bounded_face_walks(nodes, _boundary_edges(nodes, out)):
            if len(set(cycle)) != len(cycle):
                continue
            points = [(nodes[i].x_m,nodes[i].y_m) for i in cycle]
            area = _polygon_area(points)
            if area > cfg.infill_area_threshold_m2:
                faces.append((area,cycle,points))
        faces.sort(key=lambda f:(-f[0],f[1]))
        chosen = None
        for area, cycle, pts in faces:
            candidates = []
            for i,u in enumerate(cycle):
                for j in range(i+2,len(cycle)):
                    if i == 0 and j == len(cycle)-1:
                        continue
                    v=cycle[j]; a,b=nodes[u],nodes[v]
                    if (min(u,v),max(u,v)) in existing or max(degree[u],degree[v]) >= cfg.max_node_degree:
                        continue
                    if not _inside((a.x_m+b.x_m)/2,(a.y_m+b.y_m)/2,pts):
                        continue
                    if any(segments_cross(a,b,nodes[e.u],nodes[e.v]) for e in out):
                        continue
                    a1=_polygon_area(pts[i:j+1]); a2=area-a1
                    if min(a1,a2) < cfg.infill_min_child_area_m2:
                        continue
                    length=math.hypot(a.x_m-b.x_m,a.y_m-b.y_m)
                    cost=max(a1,a2)/area+0.10*length/math.sqrt(area)
                    candidates.append((cost,min(u,v),max(u,v),length))
            if candidates:
                chosen=min(candidates)
                break
        if chosen is None:
            break
        cost,u,v,length=chosen
        out.append(FormationEdge(len(out),u,v,cfg.epochs-1,length,'local','face_infill',cost))
    return out
