"""Reproduce map counterfactual repairs and bounded face infill (stdlib core)."""
from pathlib import Path
from dataclasses import replace
import json, sys, math
from time import perf_counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from metroflow.city.formative_growth import FormationConfig, generate_formative_city
from metroflow.city.formative_growth_analysis import _bounded_face_walks, _polygon_area
from run_formative_growth_research import write_svg, write_png


def largest_face(city):
    return max((_polygon_area([(city.nodes[i].x_m,city.nodes[i].y_m) for i in f])
               for f in _bounded_face_walks(city.nodes,city.edges)), default=0.)


def main(out):
    out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for count,area in ((120,12.),(220,20.),(320,25.)):
        for seed in (7,41,97):
            cfg=FormationConfig(seed=seed,node_count=count,urbanized_area_km2=area)
            a=generate_formative_city(cfg)
            start=perf_counter()
            b=generate_formative_city(replace(cfg,infill_budget=count//20))
            added=len(b.edges)-len(a.edges)
            checks={
                'old_nodes_unchanged':a.nodes==b.nodes,
                'old_streets_unchanged':b.edges[:len(a.edges)]==a.edges,
                'cycle_increment_equals_new_streets':b.metrics['cycle_rank']-a.metrics['cycle_rank']==added,
                'raw_face_increment_equals_new_streets':b.metrics['raw_bounded_face_count']-a.metrics['raw_bounded_face_count']==added,
                'euler_residual_zero':b.metrics['euler_face_residual']==0,
                'no_invalid_contacts':b.metrics['crossing_count']==0,
                'connected':b.metrics['connected_components']==1,
                'largest_face_does_not_grow':largest_face(b)<=largest_face(a)+1e-7,
                'no_backdating':b.metrics['postgrowth_backdated_edge_count']==0,
            }
            rows.append(dict(seed=seed,settlements=count,area_km2=area,infill_streets=added,
                             before_largest_m2=largest_face(a),after_largest_m2=largest_face(b),
                             elapsed_s=perf_counter()-start,checks=checks,
                             metrics=b.metrics,legacy_heuristic_audit=b.audit['status']))
    cfg=FormationConfig(seed=20261023,infill_budget=16)
    city=generate_formative_city(cfg)
    baseline=generate_formative_city(replace(cfg,infill_budget=0))
    for name,c in [('causal_no_infill',baseline),('causal_with_infill',city)]:
        (out/f'{name}.json').write_text(json.dumps(c.to_dict(),indent=2,sort_keys=True,allow_nan=False)+'\n')
        write_svg(c,out/f'{name}.svg')
        try:
            write_png(c,out/f'{name}.png')
        except ImportError:
            pass
    res={'cases':rows,'all_hard_checks_pass':all(all(r['checks'].values()) for r in rows),
         'final_fingerprint':city.fingerprint,'final_metrics':city.metrics,
         'infill_zero_fingerprint':baseline.fingerprint,
         'final_largest_face_m2':largest_face(city),'before_largest_face_m2':largest_face(baseline),
         'limitations':['synthetic authored priors','no terrain or parcels','edge-interior junction creation is not implemented','no external morphology calibration']}
    (out/'MAP_RESULTS.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in res.items() if k!='cases'},indent=2,sort_keys=True))
    return 0 if res['all_hard_checks_pass'] else 2

if __name__=='__main__':
    raise SystemExit(main(Path(sys.argv[1]) if len(sys.argv)>1 else Path('artifacts/next_loop_20261023/map')))
