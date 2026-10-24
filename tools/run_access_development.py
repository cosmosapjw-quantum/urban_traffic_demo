"""Bounded slow development on existing road grammars; standard-library core."""
from pathlib import Path
from dataclasses import asdict
import argparse,json,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from metroflow.restored_city import generate,STYLES
from metroflow.restored_zoning import attach_zones
from metroflow.restored_geometry import crossing_audit,components
from metroflow.environment.terrain import Rect
from metroflow.sight_frontage import SightRule
from metroflow.access_development import Plot,Jobs,Development,develop


def run(style,out):
    started=time.perf_counter();city=generate(style);stock,_=attach_zones(city)
    zones=sorted((z for z in stock.zones if z.housing_capacity-z.residents>=95),key=lambda z:(-z.residents,z.id))[:8]
    plots=tuple(Plot(z.id,Rect(z.x_m-40,z.y_m-40,z.x_m+40,z.y_m+40),95) for z in zones)
    # Opportunity anchors are an explicit frozen scenario input, not filled job slots.
    anchors={}
    for z in stock.zones:
        if z.access_node and z.jobs:anchors[z.access_node]=anchors.get(z.access_node,0)+z.jobs
    jobs=tuple(Jobs(k,v) for k,v in sorted(anchors.items(),key=lambda x:(-x[1],x[0]))[:3])
    state=Development(city,plots);history=[asdict(state)];receipts=[]
    rule=SightRule(approach_step_m=5.)
    base_length=sum(s.length_m for s in city.sections)
    cycle=lambda c:len(c.sections)-len(c.nodes)+len(set(components(c).values()))
    for epoch in range(3):
        state,receipt=develop(state,120,jobs,budget_m=450.,max_roads=2,admission_rule=rule)
        assert state.offered==sum(p.residents for p in state.plots)+state.pending
        assert abs(sum(s.length_m for s in state.city.sections)-base_length-state.built_m)<1e-7
        assert cycle(state.city)==cycle(city)
        assert not crossing_audit(state.city)['illegal']
        history.append(asdict(state));receipts.append(receipt)
    result=dict(style=style,epochs=receipts,offered=state.offered,placed=sum(p.residents for p in state.plots),
                pending=state.pending,built_m=state.built_m,plots_open=sum(p.access_node is not None for p in state.plots),
                illegal_crossings=0,cycle_rank=cycle(city),seconds=time.perf_counter()-started,
                background_stock_for_site_selection=stock.population,
                scenario='360-person incremental ledger on 8 authored vacant 80m-square subplots, capacity95 each <= parent zone vacancies; background residents fixed, not resimulated',
                history=history)
    out.mkdir(parents=True,exist_ok=True)
    (out/f'map_{style}.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps({k:v for k,v in result.items() if k not in ('history','epochs')},indent=2))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--style',choices=STYLES,default='organic')
    p.add_argument('--out',type=Path,default=Path('artifacts/access_fifo_20261025'))
    a=p.parse_args();run(a.style,a.out)
