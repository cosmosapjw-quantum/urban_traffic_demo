"""Actual local Rust migration measurements, never a full traffic certificate."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import resource
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'src')]
from tools.run_v1_acceptance import load_release_city
from tools.run_v1_local_acceptance import observed_environment
from metroflow.v1.activity import compile_activity
from metroflow.v1.factorized_demand import compile_factorized_demand
from metroflow.v1.release_plan import ReleasePlan


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('calendar-python','calendar-rust','routing'),required=True)
    parser.add_argument('--case',default='river_weekday_s17')
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    started=time.perf_counter()
    # Hard process address-space guard supplements native estimates; RSS reported separately.
    resource.setrlimit(resource.RLIMIT_AS,(8*1024**3,8*1024**3))
    matrix=json.loads((ROOT/'scenarios/v1/release_matrix.json').read_text())
    case=next(c for c in matrix['cases'] if c['id']==args.case)
    result=dict(mode=args.mode,case=args.case,environment=observed_environment(),
                simulated_s=0,full_campaign='NOT_RUN',rss_limit_bytes=8*1024**3)
    try:
        city,row=load_release_city(case)
        result.update(city_identity=city.identity,source_archive_sha256=row['source_sha256'])
        if args.mode=='routing':
            from metroflow.v1.lanegroups import compile_lanegroups
            from metroflow.active_suffix.routing import Arc,candidate_paths
            from metroflow.v1.native_routing import NativeRoutingGraph
            contract=compile_lanegroups(city,dt_s=10)
            arcs=tuple(Arc(g.id,g.tail,g.head) for g in contract.groups)
            costs={g.id:g.physics.length_m/g.physics.speed_mps for g in contract.groups}
            nodes=sorted({p.node_id for p in city.portals})
            queries=[(nodes[i%len(nodes)],nodes[(i*37+19)%len(nodes)]) for i in range(256)]
            t=time.perf_counter();native=NativeRoutingGraph(arcs,costs,contract.allowed_turns)
            result['native_construction_s']=time.perf_counter()-t
            t=time.perf_counter();expected=[candidate_paths(arcs,costs,a,b,1,allowed_turns=contract.allowed_turns) for a,b in queries]
            result['python_queries_s']=time.perf_counter()-t
            t=time.perf_counter();actual=native.search_batch(queries,k=1)
            result['native_queries_s']=time.perf_counter()-t
            assert actual==tuple(expected), 'paths/expanded/truncated differ'
            result.update(query_count=len(queries),exact_results_equal=True,
                          speedup_including_native_construction=result['python_queries_s']/(result['native_construction_s']+result['native_queries_s']),
                          scope='same 256 actual-city OD queries; persistent native graph, exact paths/expansion/truncation; not whole runtime speed')
        else:
            homes=tuple(compile_activity(city,b.id) for b in city.face_graph.blocks if b.residents)
            jobs=tuple(compile_activity(city,b.id,'job') for b in city.face_graph.blocks if b.jobs)
            services=tuple(compile_activity(city,b.id,'service',service_stock=b.jobs) for b in city.face_graph.blocks if b.jobs)
            schedule=compile_factorized_demand(homes,jobs,services,day=case['day'],freight_kg=1000,worker_shortfall=matrix['worker_shortfall'])
            expected=ReleasePlan(city,schedule,step_s=10).totals()
            result.update(schedule_identity=schedule.identity,expected=expected,preparation_s=time.perf_counter()-started)
            t=time.perf_counter()
            if args.mode=='calendar-python':
                retained=list(schedule.iter_legs());count=len(retained)
                result['registration_s']=time.perf_counter()-t
                totals=tuple(math.fsum(getattr(l.amounts,k) for l in retained) for k in ('persons','vehicles','cargo_kg'))
            else:
                from metroflow.v1.native_calendar import compile_native_calendar
                retained=compile_native_calendar(schedule,byte_budget=2*1024**3)
                result['registration_s']=time.perf_counter()-t
                count=len(retained);totals=retained.totals()
                result['native_storage_report']=retained.storage_report()
                result['initial_ledger_totals']=retained.initial_ledger_totals()
                result['requested_24h']=retained.requested_totals(0,86400)
            assert count==expected['legs']
            for k,value in zip(('persons','vehicles','cargo_kg'),totals):
                assert abs(value-expected[k])<=1e-9*max(1,abs(value)), (k,value,expected[k])
            result.update(retained_legs=count,totals=totals,count_and_amounts_match=True,
                          scope='entire unchanged calendar retained; Rust additionally owns zero progress arrays; routes/service/physical tick not activated')
        result['status']='PASS_SCOPED'
    except Exception as exc:
        result.update(status='FAILED',error=type(exc).__name__+': '+str(exc))
    result.update(wall_s=time.perf_counter()-started,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
    import _metroflow_rust
    result['native_binary_sha256']=hashlib.sha256(Path(_metroflow_rust.__file__).read_bytes()).hexdigest()
    result['rustc']=subprocess.check_output(['rustc','--version'],text=True).strip()
    paths=list((ROOT/'crates/metroflow-rust/src').glob('v1_*.rs'))+[Path(__file__)]+list((ROOT/'src/metroflow/v1').glob('native_*.py'))
    result['source_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result),flush=True)
    return 0 if result['status']=='PASS_SCOPED' else 2


if __name__=='__main__':raise SystemExit(main())
