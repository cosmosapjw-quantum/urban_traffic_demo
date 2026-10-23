import math
from dataclasses import replace
import pytest
from metroflow.city.formative_growth import FormationConfig, generate_formative_city
from metroflow.city.formative_growth_model import FormationNode, FormationEdge, FormationCentre, FormationMap
from metroflow.city.formative_growth_analysis import extract_planar_blocks, compute_formation_metrics, audit_formation_map
from metroflow.city.formative_infill import refine_city


def square():
    nodes=tuple(FormationNode(i,x,y,0,0,'nucleus') for i,(x,y) in enumerate(((0,0),(400,0),(400,400),(0,400))))
    edges=tuple(FormationEdge(i,u,v,0,400.,'primary','initial_backbone') for i,(u,v) in enumerate(((0,1),(1,2),(2,3),(3,0))))
    centres=(FormationCentre(0,200,200,0,1.,0.),)
    cfg=FormationConfig(node_count=24,urbanized_area_km2=1.,min_block_area_m2=100.,max_block_area_fraction=.9)
    blocks=extract_planar_blocks(cfg,nodes,edges,centres)
    return FormationMap(cfg,1000.,1000.,centres,nodes,edges,tuple(blocks),{}, {})


def test_public_infill_subdivides_one_face_and_preserves_geometry():
    base=square(); result=refine_city(base,max_roads=1,road_budget_m=400.)
    assert len(result.events)==1
    assert len(result.after.nodes)==6
    assert len(result.after.edges)==7
    assert len(result.after.blocks)==2
    assert sum(b.area_m2 for b in result.after.blocks)==pytest.approx(160000.)
    assert sum(e.length_m for e in result.after.edges)==pytest.approx(2000.)
    assert result.before is base and len(base.edges)==4
    assert all(e.birth_epoch==base.config.epochs for e in result.after.edges if e.edge_id>=4)


def test_budget_is_hard_no_unaffordable_road():
    result=refine_city(square(),max_roads=1,road_budget_m=399.)
    assert result.events==()
    assert result.after.fingerprint==result.before.fingerprint


def test_replay_and_real_generated_map_are_connected_planar():
    base=generate_formative_city(FormationConfig(seed=41,node_count=120,urbanized_area_km2=12.))
    a=refine_city(base,max_roads=3,road_budget_m=1200.)
    b=refine_city(base,max_roads=3,road_budget_m=1200.)
    assert len(a.events)>0
    assert a.after.fingerprint==b.after.fingerprint
    assert a.after.metrics['connected_components']==1
    assert a.after.metrics['crossing_count']==0
    assert a.after.metrics['primary_components']==1
    assert a.after.metrics['bounded_face_count']==len(a.after.edges)-len(a.after.nodes)+1
    assert sum(ev['new_road_length_m'] for ev in a.events)<=1200.+1e-9


def test_invalid_budget_is_not_silently_accepted():
    with pytest.raises(ValueError):
        refine_city(square(),road_budget_m=-1.)


def test_accessibility_prior_prefers_populated_core_over_distant_equal_face():
    base=square()
    # Two equal cells joined by a bridge; only the western cell has a centre.
    shifted=((3000,0),(3400,0),(3400,400),(3000,400))
    nodes=list(base.nodes)+[FormationNode(i+4,x,y,0,0,'test') for i,(x,y) in enumerate(shifted)]
    edges=list(base.edges)+[FormationEdge(i+4,u+4,v+4,0,400.,'local','test') for i,(u,v) in enumerate(((0,1),(1,2),(2,3),(3,0)))]+[FormationEdge(8,1,4,0,2600.,'primary','test')]
    # Reverse edge-id tie preference: far face IDs are smaller, so a spatial prior is required.
    edges=[replace(e,edge_id=(20-e.edge_id)) for e in edges]
    city=replace(base,nodes=tuple(nodes),edges=tuple(edges),width_m=4000.)
    r=refine_city(city,max_roads=1,road_budget_m=500.)
    assert r.events
    ids=r.events[0]['junction_node_ids']
    assert all(r.after.nodes[i].x_m<1000 for i in ids)
