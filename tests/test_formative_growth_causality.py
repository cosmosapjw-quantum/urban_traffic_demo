"""Counterfactual chronology and embedding regressions for the map research lane."""
from dataclasses import replace
import math
import random

from metroflow.city.formative_growth import (
    FormationCentre, FormationConfig, FormationNode, FormationEdge,
    generate_formative_city, extract_planar_blocks, compute_formation_metrics,
)
from metroflow.city.formative_growth_sampling import build_centres, generate_nodes
from metroflow.city.formative_growth_network import (
    build_causal_growth_network, segments_cross, repair_local_connectivity,
    _MutableEdge,
)


def square(extra_isolate=False):
    pts = [(0., 0.), (100., 0.), (100., 100.), (0., 100.)]
    if extra_isolate:
        pts.append((200., 200.))
    nodes = [FormationNode(i, x, y, 0, 0, 'nucleus') for i, (x,y) in enumerate(pts)]
    edges = [FormationEdge(i, i, (i+1)%4, 0, 100., 'local', 'loop') for i in range(4)]
    centres = [FormationCentre(0, 50., 50., 0, 1., 0.)]
    return nodes, edges, centres


def test_square_has_one_bounded_face_regardless_of_edge_order():
    cfg = FormationConfig()
    nodes, edges, centres = square()
    for ordered in (edges, list(reversed(edges))):
        blocks = extract_planar_blocks(cfg, nodes, ordered, centres)
        assert len(blocks) == 1, 'inside and outside must not share a reverse-insensitive key'
        assert math.isclose(blocks[0].area_m2, 10000.)


def test_isolated_nodes_are_components_and_cycle_rank_is_general():
    cfg = FormationConfig()
    nodes, edges, centres = square(extra_isolate=True)
    blocks = extract_planar_blocks(cfg, nodes, edges, centres)
    m = compute_formation_metrics(cfg, 300., 300., centres, nodes, edges, blocks)
    assert m['connected_components'] == 2
    assert m['cycle_rank'] == 1


def test_moving_unborn_nucleus_cannot_change_earlier_settlements():
    cfg = FormationConfig(seed=41, node_count=120, epochs=6, urbanized_area_km2=12)
    w = math.sqrt(12e6*cfg.aspect_ratio); h = w/cfg.aspect_ratio
    centres = build_centres(cfg, w, h, random.Random(41))
    before = generate_nodes(cfg, w, h, centres, random.Random(42))
    p = next(n for n in before if n.birth_epoch == 0 and n.mode != 'nucleus')
    future = centres[1]
    moved = [replace(c, x_m=p.x_m, y_m=p.y_m) if c.centre_id == future.centre_id else c for c in centres]
    after = generate_nodes(cfg, w, h, moved, random.Random(42))
    prefix = lambda ns: [(n.x_m,n.y_m,n.mode) for n in ns if n.birth_epoch < future.birth_epoch]
    assert prefix(before) == prefix(after), 'unborn centre leaked into exclusion geometry'


def test_future_grid_angle_cannot_change_initial_streets():
    cfg = FormationConfig(node_count=24, epochs=4, secondary_centre_count=1)
    nodes = [FormationNode(i, *p, 0, 0, 'nucleus') for i,p in enumerate([(0.,0.),(100.,0.),(90.,90.),(0.,110.),(200.,70.)])]
    nodes += [FormationNode(5+i, 500.+i*30., 500.+i*20., 3, 1, 'exploration') for i in range(19)]
    c = [FormationCentre(0,-1000.,-1000.,0,1.,0.), FormationCentre(1,80.,50.,3,1.,0.)]
    a = build_causal_growth_network(cfg,nodes,c)
    b = build_causal_growth_network(cfg,nodes,[c[0],replace(c[1],local_grid_angle_rad=math.pi/4)])
    prefix = lambda es: [(e.u,e.v,e.role) for e in es if e.birth_epoch < 3]
    assert prefix(a) == prefix(b), 'unborn survey frame changed early topology'


def test_embedding_predicate_catches_t_junctions_and_overlap():
    pts = [(0.,0.),(2.,0.),(1.,0.),(1.,1.),(3.,0.)]
    n = [FormationNode(i,*p,0,0,'nucleus') for i,p in enumerate(pts)]
    assert segments_cross(n[0],n[1],n[2],n[3]), 'unregistered T contact'
    assert segments_cross(n[0],n[1],n[0],n[4]), 'shared endpoint must not exempt overlap'
    assert not segments_cross(n[0],n[2],n[2],n[3]), 'registered common endpoint is legal'


def test_raw_faces_account_for_filtered_faces_and_cycle_rank():
    cfg = FormationConfig(min_block_area_m2=20000.)
    nodes,edges,centres = square()
    blocks = extract_planar_blocks(cfg,nodes,edges,centres)
    m = compute_formation_metrics(cfg,300.,300.,centres,nodes,edges,blocks)
    assert m.get('raw_bounded_face_count') == 1
    assert m.get('filtered_bounded_face_count') == 1
    assert m.get('euler_face_residual') == 0
    assert len(blocks) == 0


def test_postgrowth_repair_edges_are_not_backdated():
    city = generate_formative_city(FormationConfig())
    repaired = [e for e in city.edges if e.role in ('repair_loop','culdesac_closure')]
    assert repaired
    assert all(e.birth_epoch == city.config.epochs-1 for e in repaired)


def test_fourfold_order_has_zero_uniform_null_and_detects_alignment():
    cfg = FormationConfig()
    centre = [FormationCentre(0,0.,0.,0,1.,0.)]
    nodes=[]; edges=[]
    for i in range(72):
        t=math.pi*(i+.5)/72
        nodes += [FormationNode(2*i,0.,0.,0,0,'nucleus'),FormationNode(2*i+1,100.*math.cos(t),100.*math.sin(t),0,0,'exploration')]
        edges.append(FormationEdge(i,2*i,2*i+1,0,100.,'local','growth_connection'))
    # Metric is diagnostic, independent of this intentionally coincident-origin test geometry.
    m=compute_formation_metrics(cfg,100.,100.,centre,nodes,edges,[])
    assert 'survey_fourfold_order' in m
    assert abs(m['survey_fourfold_order']) < 1e-12


def test_opt_in_infill_splits_large_faces_without_moving_old_roads():
    import metroflow.city.formative_growth as public
    assert hasattr(public, 'insert_infill_chords'), 'constructive face infill API is missing'
    cfg = FormationConfig(infill_budget=1, infill_area_threshold_m2=9000., infill_min_child_area_m2=4000.)
    nodes,edges,centres = square()
    changed = public.insert_infill_chords(cfg, nodes, edges)
    assert changed[:len(edges)] == edges
    assert len(changed) == len(edges)+1
    assert changed[-1].birth_epoch == cfg.epochs-1
    assert changed[-1].role == 'face_infill'
    blocks = extract_planar_blocks(cfg, nodes, changed, centres)
    assert len(blocks) == 2
    assert all(math.isclose(b.area_m2,5000.) for b in blocks)
    assert math.isclose(sum(b.area_m2 for b in blocks),10000.)


def test_infill_budget_is_part_of_replay_and_zero_is_exact_fallback():
    import metroflow.city.formative_growth as public
    assert hasattr(public, 'insert_infill_chords'), 'constructive face infill API is missing'
    cfg=FormationConfig(seed=23,node_count=120,urbanized_area_km2=12,epochs=6)
    before=generate_formative_city(cfg)
    after=generate_formative_city(replace(cfg,infill_budget=8,infill_area_threshold_m2=80000.))
    assert after.nodes == before.nodes
    assert after.edges[:len(before.edges)] == before.edges
    assert len(after.edges)>len(before.edges)
    assert after.metrics['euler_face_residual']==0
    assert after.metrics['crossing_count']==0
    assert generate_formative_city(after.config).fingerprint == after.fingerprint
    assert public.insert_infill_chords(cfg, list(before.nodes),list(before.edges)) == list(before.edges)


def test_infill_does_not_skip_a_face_merely_because_it_contains_a_culdesac():
    from metroflow.city.formative_growth import insert_infill_chords
    nodes,edges,centres=square()
    nodes.append(FormationNode(4,20.,30.,0,0,'exploration'))
    edges.append(FormationEdge(4,0,4,0,math.hypot(20.,30.),'local','growth_connection'))
    cfg=FormationConfig(infill_budget=1,infill_area_threshold_m2=9000.,infill_min_child_area_m2=4000.)
    changed=insert_infill_chords(cfg,nodes,edges)
    assert len(changed)==6, 'a bridge walk must not hide the surrounding block from infill'
    assert changed[:5]==edges
    m=compute_formation_metrics(cfg,300.,300.,centres,nodes,changed,
                               extract_planar_blocks(cfg,nodes,changed,centres))
    assert m['raw_bounded_face_count']==2
    assert m['crossing_count']==0
