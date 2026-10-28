"""V03 exact-calendar preparation and measured local campaign (no CI dispatch)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'src'))
from tools.run_v1_acceptance import load_release_city  # noqa: E402
from metroflow.v1.activity import compile_activity  # noqa: E402
from metroflow.v1.factorized_demand import compile_factorized_demand  # noqa: E402
from metroflow.v1.release_plan import ReleasePlan  # noqa: E402
from metroflow.v1.release_driver import ReleaseDriver  # noqa: E402
from metroflow.v1.release_inventory import InventoryPolicy, build_inventory  # noqa: E402
from metroflow.v1.release_services import compile_service_plan  # noqa: E402
from metroflow.active_suffix.common import BudgetExceeded  # noqa: E402


def observed_environment():
    cpu=platform.processor()
    cpuinfo=Path('/proc/cpuinfo')
    if cpuinfo.exists():
        cpu=next((x.split(':',1)[1].strip() for x in cpuinfo.read_text().splitlines()
                  if x.startswith('model name')), 'unknown')
    meminfo=Path('/proc/meminfo')
    memory=next((int(x.split()[1])*1024 for x in meminfo.read_text().splitlines()
                 if x.startswith('MemTotal:')), None) if meminfo.exists() else None
    return dict(python=platform.python_version(),platform=platform.platform(),cpu=cpu,
                observed_memory_bytes=memory,logical_cpus=os.cpu_count(),scientific_threads=1)


def prepare(case,matrix,step_s):
    city,row=load_release_city(case)
    homes=tuple(compile_activity(city,b.id) for b in city.face_graph.blocks if b.residents)
    jobs=tuple(compile_activity(city,b.id,'job') for b in city.face_graph.blocks if b.jobs)
    services=tuple(compile_activity(city,b.id,'service',service_stock=b.jobs) for b in city.face_graph.blocks if b.jobs)
    schedule=compile_factorized_demand(homes,jobs,services,day=case['day'],freight_kg=1000,
                                      worker_shortfall=matrix['worker_shortfall'])
    plan=ReleasePlan(city,schedule,step_s=step_s)
    def factory(city,legs,*,step_s):
        policy=dict(matrix['inventory_policy'])
        policy['departures_s']=tuple(policy['departures_s'])
        inventory=build_inventory(city,InventoryPolicy(**policy))
        return compile_service_plan(city,legs,inventory.corridors,
                     depot_block_id=inventory.depot_block_id,step_s=step_s,
                     max_legs=matrix['route_materialization_budget'])
    driver=ReleaseDriver(plan,factory,max_legs=matrix['route_materialization_budget'],step_s=step_s)
    return driver,row


def worker(args,matrix,case):
    started=time.perf_counter()
    result=dict(case=case['id'],status='PREPARING',simulated_s=0,
                environment=observed_environment(),step_s=args.step_s,horizon_s=args.horizon_s,
                matrix_sha256=hashlib.sha256(args.matrix.read_bytes()).hexdigest())
    try:
        driver,row=prepare(case,matrix,args.step_s)
        result.update(source_sha256=row['source_sha256'],patch_sha256=row['patch_sha256'],
                      driver_identity=driver.identity)
        if args.prepare_only:
            result.update(status='WHOLE_CALENDAR_PREPARED',calendar=driver.plan.totals())
        else:
            state=driver.initial()
            driver.save(args.out/(args.label+'.last_valid.json'),state)
            tick_times=[]
            peak_records=0
            def advance_measured(state,end):
                nonlocal peak_records
                while state.time_s<end:
                    started_tick=time.perf_counter()
                    state=driver.advance(state,min(end,state.time_s+args.step_s))
                    tick_times.append(time.perf_counter()-started_tick)
                    joint=state.runtime_state
                    road=joint.service.road
                    records=sum(len(q.parts) for c in road.cells for q in c.packets)
                    records+=sum(len(q.parts) for queue in road.pending for q in queue)
                    records+=len(joint.entering)+len(joint.egress)+len(joint.internal)+sum(map(len,joint.receipts))
                    peak_records=max(peak_records,records)
                    if abs(state.time_s/3600-round(state.time_s/3600))<1e-8:
                        driver.save(args.out/(args.label+'.last_valid.json'),state)
                return state
            if args.horizon_s>=28800:
                state=advance_measured(state,28800)
                result['refinement_prefix']=driver.report(state)
            if args.resume and args.horizon_s>=43200:
                state=advance_measured(state,43200)
                middle=args.out/(args.label+'.middle.json')
                driver.save(middle,state)
                state=driver.load(middle)
            state=advance_measured(state,args.horizon_s)
            final=args.out/(args.label+'.final.json')
            driver.save(final,state)
            times=sorted(tick_times)
            result['tick_p50_s']=times[int((len(times)-1)*.5)] if times else None
            result['tick_p95_s']=times[int((len(times)-1)*.95)] if times else None
            result['peak_tracked_records']=peak_records
            result['route_latency_p99']='NOT_MEASURED; total preparation wall included'
            result.update(status='EXECUTED_FOR_REVIEW',simulated_s=state.time_s,
                          report=driver.report(state),final_checkpoint_sha256=hashlib.sha256(final.read_bytes()).hexdigest())
    except BudgetExceeded as exc:
        checkpoint=getattr(exc,'checkpoint',None)
        if hasattr(checkpoint,'report'):
            evidence=checkpoint.report()
        elif checkpoint is not None:
            path=args.out/(args.label+'.last_valid.json')
            driver.save(path,checkpoint)
            evidence=dict(path=path.name,time_s=checkpoint.time_s)
        else:
            evidence=None
        result.update(status='BLOCKED_RESOURCE',reason=str(exc),last_valid=evidence)
    except (ValueError,MemoryError) as exc:
        result.update(status='BLOCKED',reason=type(exc).__name__+': '+str(exc))
    result.update(wall_s=time.perf_counter()-started,
                  peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024))
    if result['peak_rss_bytes']>matrix['limits']['peak_rss_bytes']:
        result.update(status='BLOCKED_RESOURCE',reason='measured peak RSS exceeds release limit')
    (args.out/(args.label+'.json')).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(case=case['id'],status=result['status'],simulated_s=result['simulated_s'])),flush=True)
    return 0 if result['status'] in ('WHOLE_CALENDAR_PREPARED','EXECUTED_FOR_REVIEW') else 2


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix',type=Path,default=ROOT/'scenarios/v1/release_matrix.json')
    parser.add_argument('--case')
    parser.add_argument('--out',type=Path,default=ROOT/'artifacts/v1/local_acceptance')
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--run-local',action='store_true')
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--label',default='preparation')
    parser.add_argument('--step-s',type=float,default=10)
    parser.add_argument('--horizon-s',type=float,default=86400)
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    matrix=json.loads(args.matrix.read_text())
    cases=[c for c in matrix['cases'] if args.case is None or c['id']==args.case]
    if not cases or (not args.prepare_only and not args.run_local):
        parser.error('select --prepare-only or explicitly --run-local, and a valid case')
    args.out.mkdir(parents=True,exist_ok=True)
    if args.worker:
        return worker(args,matrix,cases[0])
    receipts=[]
    for case in cases:
        runs=[('prepare',10,False,0)] if args.prepare_only else [
            ('run1',10,False,86400),('run2_resume',10,True,86400),('run3',10,False,86400),('refined',5,False,28800)]
        for name,step,resume,horizon in runs:
            label=case['id']+'.'+name
            cmd=[sys.executable,str(Path(__file__).resolve()),'--worker','--case',case['id'],
                 '--matrix',str(args.matrix),'--out',str(args.out),'--label',label,
                 '--step-s',str(step),'--horizon-s',str(horizon)]
            cmd+=['--prepare-only'] if args.prepare_only else ['--run-local']
            if resume:
                cmd+=['--resume']
            env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
            path=args.out/(label+'.json')
            path.unlink(missing_ok=True)
            launch_wall=time.time()
            try:
                completed=subprocess.run(cmd,env=env,timeout=matrix['limits']['wall_s'])
                receipt=json.loads(path.read_text()) if path.exists() else dict(status='ENVIRONMENT_BLOCKER',label=label,exit_code=completed.returncode)
                success=receipt['status'] in ('WHOLE_CALENDAR_PREPARED','EXECUTED_FOR_REVIEW')
                if success and (completed.returncode!=0 or receipt.get('case')!=case['id']
                        or receipt.get('step_s')!=step or receipt.get('horizon_s')!=horizon
                        or receipt.get('matrix_sha256')!=hashlib.sha256(args.matrix.read_bytes()).hexdigest()):
                    receipt=dict(status='ENVIRONMENT_BLOCKER',reason='child exit or receipt binding differs',label=label)
            except subprocess.TimeoutExpired:
                receipt=dict(status='BLOCKED_RESOURCE',reason='wall deadline exceeded',label=label)
                checkpoint=args.out/(label+'.last_valid.json')
                if checkpoint.exists() and checkpoint.stat().st_mtime>=launch_wall:
                    receipt['last_valid_checkpoint']=checkpoint.name
            receipts.append(receipt)
            if receipt['status'] not in ('WHOLE_CALENDAR_PREPARED','EXECUTED_FOR_REVIEW'):
                break
    result=dict(status='PREPARATION_ONLY' if args.prepare_only else 'MEASURED_REQUIRES_REVIEW',
                receipts=receipts,full_ci_and_integration='DEFERRED_BY_USER')
    if any(r['status'].startswith(('BLOCKED','ENVIRONMENT')) for r in receipts):
        result['status']='BLOCKED'
    for case in cases:
        full=[r for r in receipts if r.get('case')==case['id'] and r.get('simulated_s')==86400]
        if len(full)==3:
            result.setdefault('checkpoint_replay',{})[case['id']]=len({r['final_checkpoint_sha256'] for r in full})==1
        prefixes=[r for r in receipts if r.get('case')==case['id'] and 'refinement_prefix' in r]
        coarse=next((r for r in prefixes if r['step_s']==10),None)
        fine=next((r for r in prefixes if r['step_s']==5),None)
        if coarse and fine:
            a=coarse['refinement_prefix']['execution']['ledger']
            b=fine['refinement_prefix']['execution']['ledger']
            result.setdefault('refinement_deltas',{})[case['id']]={u:{k:b[u][k]-a[u][k] for k in a[u]} for u in a}
    (args.out/'CAMPAIGN.json').write_text(json.dumps(result,indent=2)+'\n')
    return 2 if result['status']=='BLOCKED' else 0


if __name__=='__main__':
    raise SystemExit(main())
