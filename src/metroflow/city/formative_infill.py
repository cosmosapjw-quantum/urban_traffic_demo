"""Budgeted planar infill. Coordinates/lengths m, area m^2; stdlib only.

This is an optional post-growth epoch, not an alteration of past street history.
Only simple bounded faces are eligible. The immutable before graph and retirement
ledger, not a birth-year filter of the final graph, define the earlier snapshot.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
import math
from types import MappingProxyType
from typing import Mapping
from metroflow.city.formative_growth_model import FormationMap, FormationNode, FormationEdge
from metroflow.city.formative_growth_analysis import (
    _face_walks, _polygon_area, extract_planar_blocks,
    compute_formation_metrics, audit_formation_map,
)
from metroflow.city.formative_growth_network import segments_cross

@dataclass(frozen=True, slots=True)
class InfillResult:
    before: FormationMap
    after: FormationMap
    events: tuple[Mapping[str, object], ...]


def _inside(x, y, points):
    """Even-odd point-in-simple-polygon test; chord samples avoid the boundary."""
    result = False
    for (ax, ay), (bx, by) in zip(points, points[1:] + points[:1]):
        if (ay > y) != (by > y) and x < ax + (y-ay)*(bx-ax)/(by-ay):
            result = not result
    return result


def _candidates(nodes, edges, centres, remaining, minimum, child_min, segment_min, road_max, radius):
    walks, _ = _face_walks(nodes, edges)
    faces=[]
    for walk in walks:
        if len(set(walk)) != len(walk):
            continue  # A bridge-bearing boundary is not silently made simple.
        pts=[(nodes[i].x_m,nodes[i].y_m) for i in walk]
        area=_polygon_area(pts)
        if area>=minimum:
            faces.append((area, walk, pts))
    def activity(x,y):
        return sum(c.attraction*math.exp(-((x-c.x_m)**2+(y-c.y_m)**2)/(2*radius**2)) for c in centres)
    faces.sort(key=lambda x:(-x[0]*activity(sum(p[0] for p in x[2])/len(x[2]),sum(p[1] for p in x[2])/len(x[2])),x[1]))
    lookup={e.key:e for e in edges}
    for area, walk, pts in faces[:24]:
        count=len(walk)
        for i in range(count):
            e1=lookup[tuple(sorted((walk[i],walk[(i+1)%count])))]
            if e1.length_m<2*segment_min:
                continue
            p=tuple((a+b)/2 for a,b in zip(pts[i],pts[(i+1)%count]))
            for j in range(i+2,count):
                if i==0 and j==count-1:
                    continue
                e2=lookup[tuple(sorted((walk[j],walk[(j+1)%count])))]
                if e2.length_m<2*segment_min:
                    continue
                q=tuple((a+b)/2 for a,b in zip(pts[j],pts[(j+1)%count]))
                length=math.dist(p,q)
                if not 2*segment_min<=length<=min(remaining,road_max)+1e-9:
                    continue
                if not all(_inside((1-t)*p[0]+t*q[0],(1-t)*p[1]+t*q[1],pts) for t in (.01,.25,.5,.75,.99)):
                    continue
                n1=FormationNode(len(nodes),*p,0,0,'junction')
                n2=FormationNode(len(nodes)+1,*q,0,0,'junction')
                if any(segments_cross(n1,n2,nodes[e.u],nodes[e.v])
                       for e in edges if e.edge_id not in (e1.edge_id,e2.edge_id)):
                    continue
                area1=_polygon_area([p]+pts[i+1:j+1]+[q])
                area2=_polygon_area([q]+pts[j+1:]+pts[:i+1]+[p])
                if min(area1,area2)<max(child_min,.15*area):
                    continue
                if abs(area1+area2-area)>max(1e-6,1e-10*area):
                    raise ArithmeticError('daughter areas do not partition parent face')
                centre=min(centres,key=lambda c:math.hypot((p[0]+q[0])/2-c.x_m,(p[1]+q[1])/2-c.y_m))
                theta=math.atan2(q[1]-p[1],q[0]-p[0])
                alignment=(1+math.cos(4*(theta-centre.local_grid_angle_rad)))/2
                balance=4*area1*area2/(area*area)
                score=area*balance*(.25+.75*alignment)*activity((p[0]+q[0])/2,(p[1]+q[1])/2)/(1+length/math.sqrt(area))
                yield score,e1,e2,p,q,length,area,area1,area2,centre.centre_id


def refine_city(city: FormationMap, *, max_roads=8, road_budget_m=2000.0,
                min_face_area_m2=60000.0, min_child_area_m2=10000.0,
                min_segment_m=40.0, max_road_m=900.0, development_radius_m=1100.0) -> InfillResult:
    """Insert affordable interior chords, splitting both existing boundary roads.

    Hard budget is additional centreline length, not money or demolition cost.
    Each operation: retire 2 edges, add 2 vertices and 5 edges (delta cycle=1).
    Existing primary/secondary roads retain their classification in both children.
    """
    if not isinstance(max_roads,int) or isinstance(max_roads,bool) or max_roads<0:
        raise ValueError('max_roads must be a nonnegative integer')
    vals=(road_budget_m,min_face_area_m2,min_child_area_m2,min_segment_m,max_road_m,development_radius_m)
    if not all(math.isfinite(x) and x>=0 for x in vals) or min(vals[1:])<=0:
        raise ValueError('finite nonnegative budget and positive geometry thresholds required')
    if max_roads==0 or road_budget_m==0:
        return InfillResult(city,city,())
    if city.config.epochs>=12:
        raise ValueError('no additional epoch available in FormationConfig contract')
    nodes=list(city.nodes); edges=list(city.edges); events=[]
    remaining=road_budget_m; epoch=city.config.epochs
    next_id=max((e.edge_id for e in edges),default=-1)+1
    for sequence in range(max_roads):
        candidates=list(_candidates(nodes,edges,city.centres,remaining,min_face_area_m2,
                                    min_child_area_m2,min_segment_m,max_road_m,development_radius_m))
        if not candidates:
            break
        best=max(candidates,key=lambda c:(c[0],-c[1].edge_id,-c[2].edge_id))
        score,e1,e2,p,q,length,area,area1,area2,centre_id=best
        old_v,old_e=len(nodes),len(edges)
        idx1,idx2=len(nodes),len(nodes)+1
        nodes.extend((FormationNode(idx1,*p,epoch,centre_id,'infill_junction'),
                      FormationNode(idx2,*q,epoch,centre_id,'infill_junction')))
        edges=[e for e in edges if e.edge_id not in (e1.edge_id,e2.edge_id)]
        children=[]
        for old,idx in ((e1,idx1),(e2,idx2)):
            for a,b in ((old.u,idx),(idx,old.v)):
                new=FormationEdge(next_id,a,b,epoch,
                    math.hypot(nodes[a].x_m-nodes[b].x_m,nodes[a].y_m-nodes[b].y_m),
                    old.hierarchy,'infill_subdivision',old.score)
                edges.append(new); children.append(next_id); next_id+=1
        chord_id=next_id
        edges.append(FormationEdge(next_id,idx1,idx2,epoch,length,'local','infill_chord',score));next_id+=1
        remaining-=length
        assert len(nodes)-old_v==2 and len(edges)-old_e==3
        events.append(MappingProxyType(dict(sequence=sequence,epoch=epoch,
            retired_edge_ids=(e1.edge_id,e2.edge_id),retired_edge_births=(e1.birth_epoch,e2.birth_epoch),
            subdivision_edge_ids=tuple(children),junction_node_ids=(idx1,idx2),chord_edge_id=chord_id,
            new_road_length_m=length,parent_area_m2=area,child_areas_m2=(area1,area2),
            remaining_budget_m=max(0.,remaining),delta_vertices=2,delta_edges=3,delta_cycle_rank=1)))
    if not events:
        return InfillResult(city,city,())
    cfg=replace(city.config,node_count=max(24,len(nodes)),epochs=epoch+1)
    blocks=extract_planar_blocks(cfg,nodes,edges,city.centres)
    metrics=compute_formation_metrics(cfg,city.width_m,city.height_m,city.centres,nodes,edges,blocks)
    # A toy with <24 vertices is permitted as an externally supplied frozen graph.
    metrics.update(infill_roads=len(events),infill_added_length_m=road_budget_m-remaining)
    audit=audit_formation_map(cfg,city.width_m,city.height_m,city.centres,nodes,edges,blocks,metrics)
    if metrics['crossing_count'] or metrics['connected_components']!=1:
        raise ArithmeticError('infill broke surface embedding/connectivity')
    after=FormationMap(cfg,city.width_m,city.height_m,city.centres,tuple(nodes),tuple(edges),
                       tuple(blocks),MappingProxyType(metrics),MappingProxyType(audit))
    return InfillResult(city,after,tuple(events))
