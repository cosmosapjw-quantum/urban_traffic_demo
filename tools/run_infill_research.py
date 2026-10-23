"""Reproducible optional infill experiment; scientific path is stdlib-only."""
import argparse,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from metroflow.city.formative_growth import FormationConfig,generate_formative_city
from metroflow.city.formative_infill import refine_city

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args(); out=args.output_dir;out.mkdir(parents=True,exist_ok=True)
    results=[]
    for seed,n,area in ((20261023,320,25.),(7,120,12.),(41,120,12.),(97,120,12.),(7,220,20.),(41,220,20.),(97,220,20.)):
        start=time.perf_counter();base=generate_formative_city(FormationConfig(seed=seed,node_count=n,urbanized_area_km2=area))
        result=refine_city(base,max_roads=8,road_budget_m=2000.)
        old,new=base.metrics,result.after.metrics
        row={'seed':seed,'base_nodes':n,'area_km2':area,'seconds':time.perf_counter()-start,
             'before':dict(old),'after':dict(new),'events':[dict(x) for x in result.events],
             'before_fingerprint':base.fingerprint,'after_fingerprint':result.after.fingerprint}
        for k in ('crossing_count',):assert new[k]==0
        assert new['connected_components']==new['primary_components']==1
        assert new['cycle_rank']==new['bounded_face_count']
        assert new['cycle_rank']-old['cycle_rank']==len(result.events)
        added=sum(e.length_m for e in result.after.edges)-sum(e.length_m for e in base.edges)
        assert abs(added-sum(e['new_road_length_m'] for e in result.events))<1e-7
        results.append(row)
        if seed==20261023:
            for name,city in (('map_before',base),('map_after',result.after)):
                (out/(name+'.json')).write_text(json.dumps(city.to_dict(),indent=2,allow_nan=False))
    (out/'map_results.json').write_text(json.dumps(results,indent=2,allow_nan=False))
    print(json.dumps([{'seed':r['seed'],'roads_added':len(r['events']),'cycle_before':r['before']['cycle_rank'],
                      'cycle_after':r['after']['cycle_rank'],'length_added_m':r['after'].get('infill_added_length_m',0),
                      'seconds':r['seconds']} for r in results],indent=2))
if __name__=='__main__':main()
