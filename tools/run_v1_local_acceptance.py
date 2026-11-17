"""V03 exact-calendar preparation and measured local campaign (no CI dispatch)."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import tempfile
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
from metroflow.route_metrics import RouteLatencyMeasurements  # noqa: E402


def atomic_json(path, value):
    """Readers never observe a partly written progress or final receipt."""
    path=Path(path)
    with tempfile.TemporaryDirectory(dir=path.parent) as directory:
        staged=Path(directory)/'receipt.json'
        staged.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
        staged.replace(path)


def peak_rss_bytes():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)


def file_sha256(path):
    """Hash checkpoints with fixed-size scratch space, regardless of file size."""
    digest=hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def resource_limit_kind(message, storage=None):
    """Distinguish accounting admissions from observed process exhaustion."""
    message=message.lower()
    if 'checkpointability' in message or 'capture/validation' in message:
        return 'checkpoint_working_budget_guard'
    if 'shared storage' in message or 'retained storage and concurrent dense' in message:
        return 'shared_accounting_guard'
    if 'native preflight' in message or 'static accounting' in message:
        return 'static_accounting_guard'
    if storage and storage.get('resource_binding') in ('retained_capacity_v2','retained_capacity_v3','retained_capacity_v4','retained_capacity_v5') and 'budget' in message:
        if any(word in message for word in ('journey','road','phase','observation','decode','service event')):
            return 'phase_working_budget_guard'
    if ('storage' in message and 'budget' in message) or (
            'byte budget' in message and ('journey' in message or 'road' in message)):
        return 'owner_quota_guard'
    if 'preflight' in message or 'accounting' in message:
        return 'static_accounting_guard'
    if 'record budget' in message:
        return 'logical_record_guard'
    return 'allocation_or_other_budget'


def candidate_provenance():
    """Commit plus current relevant source contents, including uncommitted work."""
    paths=set((ROOT/'src').rglob('native*.py'))
    paths.update((ROOT/'crates/metroflow-rust/src').glob('v1*.rs'))
    paths.update(path for path in (ROOT/'Cargo.lock',ROOT/'crates/metroflow-rust/Cargo.lock',
        ROOT/'crates/metroflow-rust/Cargo.toml',ROOT/'crates/metroflow-rust/src/lib.rs',
        Path(__file__).resolve()) if path.is_file())
    try:
        digest=hashlib.sha256()
        names=[]
        for path in sorted(paths):
            name=path.relative_to(ROOT).as_posix()
            names.append(name)
            digest.update(name.encode()+b'\0')
            size=path.stat().st_size
            digest.update(str(size).encode()+b'\0')
            with path.open('rb') as source:
                for block in iter(lambda:source.read(1024*1024),b''):
                    digest.update(block)
        result=dict(status='MEASURED',source_sha256=digest.hexdigest(),source_files=names,
                    scope='current native*.py, v1*.rs, crate manifest/lock/lib.rs and acceptance CLI contents')
        try:
            result['git_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,
                stderr=subprocess.DEVNULL,text=True).strip()
            result['source_dirty']=bool(subprocess.check_output(['git','status','--porcelain','--',*names],
                cwd=ROOT,stderr=subprocess.DEVNULL,text=True).strip())
        except (OSError,subprocess.SubprocessError) as exc:
            result['git_status']='NOT_MEASURED: '+type(exc).__name__
        return result
    except OSError as exc:
        return dict(status='NOT_MEASURED',reason=type(exc).__name__+': '+str(exc))


def _ledger_error(report, expected_time, *, population=None):
    """Check conservation, not a dt convergence tolerance."""
    try:
        execution=report['execution']
        if execution['time_s']!=expected_time:
            return 'report clock differs from measured horizon'
        calendar=report['calendar']['calendar']
        if population is not None and calendar['resident_stock']!=population:
            return 'resident stock differs from requested matrix population'
        for unit in ('persons','vehicles','cargo_kg'):
            row=execution['ledger'][unit]
            values=[row[k] for k in ('requested','released','completed','pending','active')]
            if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in values):
                return 'nonfinite or nonnumeric cumulative ledger'
            requested,released,completed,pending,active=values
            tolerance=1e-9*max(1.,abs(requested),abs(released),abs(completed))
            if (min(values)<-tolerance or abs(requested-released-pending)>tolerance
                    or abs(released-completed-active)>tolerance):
                return 'cumulative amount conservation differs'
            if expected_time==86400 and abs(requested-calendar[unit])>1e-9*max(1.,calendar[unit]):
                return 'full-day requested amount differs from complete calendar'
    except (KeyError,TypeError,ValueError):
        return 'missing or malformed full-calendar ledger'
    return None


def assess_campaign(receipts,matrix,cases,*,prepare_only=False):
    """Execution eligibility for separate review; never invent refinement PASS."""
    result=dict(status='PREPARATION_ONLY' if prepare_only else 'MEASURED_REQUIRES_REVIEW',
        receipts=receipts,selected_cases=[c['id'] for c in cases],
        required_matrix_cases=[c['id'] for c in matrix['cases']],
        full_ci_and_integration='DEFERRED_BY_USER',issues=[])
    if any(r.get('status') not in ('WHOLE_CALENDAR_PREPARED','EXECUTED_FOR_REVIEW') for r in receipts):
        result['issues'].append('one or more runs failed or were not executed')
    if prepare_only:
        if len(receipts)!=len(cases) or any(r.get('status')!='WHOLE_CALENDAR_PREPARED' for r in receipts):
            result['issues'].append('preparation coverage is incomplete')
    else:
        for case in cases:
            name=case['id']
            rows=[r for r in receipts if r.get('case')==name]
            full=[r for r in rows if r.get('status')=='EXECUTED_FOR_REVIEW'
                  and r.get('simulated_s')==86400 and r.get('horizon_s')==86400 and r.get('step_s')==10]
            if len(full)!=3:
                result['issues'].append(name+': exactly three complete full-day runs required')
            else:
                identity_fields=('driver_identity','matrix_sha256','source_sha256','patch_sha256',
                                 'engine_backend','routing_backend','candidate_source_sha256')
                if all(r.get('engine_backend')=='rust_whole' for r in full):
                    identity_fields+=('native_binary_sha256',)
                if any(any(k not in r for k in identity_fields) for r in full) or any(
                        len({r[k] for r in full})!=1 for k in identity_fields):
                    result['issues'].append(name+': full-day input/runtime bindings differ or are missing')
                hashes=[r.get('final_checkpoint_sha256') for r in full]
                replay=all(isinstance(h,str) and len(h)==64 for h in hashes) and len(set(hashes))==1
                result.setdefault('checkpoint_replay',{})[name]=replay
                if not replay:
                    result['issues'].append(name+': checkpoint replay differs or lacks hashes')
                if sum(bool(r.get('resume_requested')) for r in full)!=1:
                    result['issues'].append(name+': exactly one saved-checkpoint resumed run required')
            for row in rows:
                if row.get('status')!='EXECUTED_FOR_REVIEW':
                    continue
                hashes=('candidate_source_sha256',)
                if row.get('engine_backend')=='rust_whole':
                    hashes+=('native_binary_sha256',)
                if any(not isinstance(row.get(key),str) or len(row[key])!=64
                       or any(c not in '0123456789abcdef' for c in row[key]) for key in hashes):
                    result['issues'].append(name+': candidate/native binary fingerprint is not measured')
                error=_ledger_error(row.get('report'),row.get('simulated_s'),population=matrix.get('population'))
                if error:
                    result['issues'].append(name+': '+error)
                for field,limit_key in [('wall_s','wall_s'),('peak_rss_bytes','peak_rss_bytes')]:
                    value=row.get(field)
                    if (isinstance(value,bool) or not isinstance(value,(int,float))
                            or not math.isfinite(value) or value>matrix['limits'][limit_key] or value<0):
                        result['issues'].append(name+': missing/invalid/exceeded '+field)
                if row.get('engine_backend')=='rust_whole':
                    route=row.get('native_route_latency',{})
                    if route.get('status')!='MEASURED_INTERVAL' or not route.get('observed_calls',0):
                        result['issues'].append(name+': native OD route latency is not measured')
            coarse=next((r for r in full if 'refinement_prefix' in r),None)
            fine=next((r for r in rows if r.get('status')=='EXECUTED_FOR_REVIEW'
                       and r.get('step_s')==5 and r.get('simulated_s')==28800
                       and 'refinement_prefix' in r),None)
            if coarse is None or fine is None:
                result['issues'].append(name+': coarse/refined matched 8h reports are missing')
                result.setdefault('refinement_assessment',{})[name]=dict(status='BLOCKED_MISSING_EVIDENCE')
                continue
            refinement_bindings=('matrix_sha256','source_sha256','patch_sha256',
                                 'engine_backend','routing_backend','candidate_source_sha256')
            if coarse.get('engine_backend')=='rust_whole':
                refinement_bindings+=('native_binary_sha256',)
            if any(k not in coarse or k not in fine or coarse[k]!=fine[k]
                   for k in refinement_bindings):
                result['issues'].append(name+': coarse/refined input/runtime bindings differ or are missing')
                continue
            errors=[_ledger_error(r['refinement_prefix'],28800,population=matrix.get('population')) for r in (coarse,fine)]
            if any(errors):
                result['issues'].append(name+': invalid refinement prefix: '+str(errors))
                continue
            a=coarse['refinement_prefix']['execution']['ledger']
            b=fine['refinement_prefix']['execution']['ledger']
            result.setdefault('refinement_deltas',{})[name]={u:{k:b[u][k]-a[u][k] for k in a[u]} for u in a}
            result.setdefault('refinement_assessment',{})[name]=dict(
                status='REQUIRES_SEPARATE_REVIEW',coarse_step_s=10,refined_step_s=5,horizon_s=28800,
                reason='No full-city temporal-refinement acceptance threshold is prescribed; conservation tolerances are not convergence tolerances')
    if result['issues']:
        result['status']='BLOCKED'
    return result


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
    policy=dict(matrix['inventory_policy'])
    policy['departures_s']=tuple(policy['departures_s'])
    inventory=build_inventory(city,InventoryPolicy(**policy))
    if os.environ.get('METROFLOW_V1_ENGINE_BACKEND') == 'rust_whole':
        from metroflow.v1.native_release_driver import NativeReleaseDriver
        return NativeReleaseDriver(plan,inventory,step_s=step_s,
            byte_budget=min(6*1024**3,matrix['limits']['peak_rss_bytes']),
            native_threads=int(os.environ.get('METROFLOW_V1_NATIVE_THREADS','1')),
            storage_policy=os.environ.get('METROFLOW_V1_STORAGE_POLICY','bounded_bytes_v1'),
            entry_projection_width_s=float(os.environ.get('METROFLOW_V1_ENTRY_PROJECTION_WIDTH_S','0')),
            road_representation=os.environ.get('METROFLOW_V1_ROAD_REPRESENTATION','rows')),row
    def factory(city,legs,*,step_s):
        return compile_service_plan(city,legs,inventory.corridors,
                     depot_block_id=inventory.depot_block_id,step_s=step_s,
                     max_legs=matrix['route_materialization_budget'])
    driver=ReleaseDriver(plan,factory,max_legs=matrix['route_materialization_budget'],step_s=step_s)
    return driver,row


def worker(args,matrix,case):
    # Frontend flags override the historical environment selectors. Direct
    # worker() callers without flags retain their previous environment contract.
    overrides={key:str(getattr(args,attr)) for attr,key in (
        ('engine_backend','METROFLOW_V1_ENGINE_BACKEND'),
        ('native_threads','METROFLOW_V1_NATIVE_THREADS'),
        ('storage_policy','METROFLOW_V1_STORAGE_POLICY'),
        ('entry_projection_width_s','METROFLOW_V1_ENTRY_PROJECTION_WIDTH_S'),
        ('road_representation','METROFLOW_V1_ROAD_REPRESENTATION')) if hasattr(args,attr)}
    previous={key:os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    try:
        with RouteLatencyMeasurements() as route_latency:
            return _worker(args,matrix,case,route_latency)
    finally:
        for key,value in previous.items():
            if value is None:
                os.environ.pop(key,None)
            else:
                os.environ[key]=value


def _worker(args,matrix,case,route_latency):
    started=time.perf_counter()
    result=dict(case=case['id'],status='PREPARING',simulated_s=0,
                run_label=args.label,resume_requested=bool(getattr(args,'resume',False)),
                routing_backend=os.environ.get('METROFLOW_V1_ROUTING_BACKEND','python_oracle'),
                engine_backend=os.environ.get('METROFLOW_V1_ENGINE_BACKEND','python_oracle'),
                environment=observed_environment(),step_s=args.step_s,horizon_s=args.horizon_s,
                matrix_sha256=hashlib.sha256(args.matrix.read_bytes()).hexdigest())
    result['candidate']=candidate_provenance()
    result['candidate_source_sha256']=result['candidate'].get('source_sha256')
    driver=state=None
    tick_times=[]
    peak_records=0
    native_frontend_s=0.0
    def progress(current=None,checkpoint=None):
        payload=dict(case=case['id'],run_label=args.label,status=result['status'],
            simulated_s=current.time_s if current is not None else result['simulated_s'],
            wall_s=time.perf_counter()-started,peak_rss_bytes=peak_rss_bytes(),
            peak_tracked_records=peak_records,completed_tick_samples=len(tick_times),
            matrix_sha256=result['matrix_sha256'])
        payload['candidate_source_sha256']=result['candidate_source_sha256']
        payload['git_commit']=result['candidate'].get('git_commit')
        if 'native_binary_sha256' in result:
            payload['native_binary_sha256']=result['native_binary_sha256']
        if 'driver_identity' in result:
            payload['driver_identity']=result['driver_identity']
        if checkpoint is not None:
            payload['last_valid_checkpoint']=checkpoint.name
        atomic_json(args.out/(args.label+'.progress.json'),payload)
    progress()
    try:
        if result['engine_backend']=='rust_whole':
            from metroflow.v1.native_engine import native_binary_provenance
            result['native_binary']=native_binary_provenance()
            result['native_binary_sha256']=result['native_binary'].get('sha256')
            # Bound transient construction/state/checkpoint allocations as well
            # as retained native accounting. This does not relax the RSS target.
            old_soft,old_hard=resource.getrlimit(resource.RLIMIT_AS)
            limit=matrix['limits']['peak_rss_bytes']
            if old_soft!=resource.RLIM_INFINITY:
                limit=min(limit,old_soft)
            if old_hard!=resource.RLIM_INFINITY:
                limit=min(limit,old_hard)
            resource.setrlimit(resource.RLIMIT_AS,(limit,old_hard))
            result['address_space_limit_bytes']=limit
        driver,row=prepare(case,matrix,args.step_s)
        if result['engine_backend']=='rust_whole':
            result['native_execution']=driver.runtime.native.execution_config()
            result['environment']['scientific_threads']=driver.runtime.native.native_threads
            result['native_storage']=driver.runtime.storage_config()
            result['native_route_latency']=driver.runtime.routing_metrics()
            result['routing_backend_scope']='routing_backend selects frontend fleet lookup; whole-calendar OD routing is Rust'
        result.update(source_sha256=row['source_sha256'],patch_sha256=row['patch_sha256'],
                      driver_identity=driver.identity)
        if args.prepare_only:
            result.update(status='WHOLE_CALENDAR_PREPARED',calendar=driver.plan.totals())
        else:
            state=driver.initial()
            result['status']='RUNNING'
            checkpoint_suffix='.bin' if driver.engine_backend=='rust_whole' else '.json'
            driver.save(args.out/(args.label+'.last_valid'+checkpoint_suffix),state)
            progress(state,args.out/(args.label+'.last_valid'+checkpoint_suffix))
            def advance_measured(state,end):
                nonlocal peak_records, native_frontend_s
                while state.time_s<end:
                    started_tick=time.perf_counter()
                    if getattr(driver, 'engine_backend', 'python_oracle') in ('rust','rust_whole'):
                        # Keep hourly durable checkpoints; native code records
                        # each physical tick without Python state roundtrips.
                        target=min(end,(math.floor(state.time_s/3600)+1)*3600)
                        expected_ticks=round((target-state.time_s)/args.step_s)
                        state=driver.advance(state,target)
                        elapsed=time.perf_counter()-started_tick
                        metrics=driver.runtime.last_advance_metrics
                        samples=metrics['tick_times_s']
                        if (len(samples)!=expected_ticks or
                                any(not math.isfinite(x) or x<0 for x in samples)):
                            raise ValueError('native tick timing samples differ from completed intervals')
                        tick_times.extend(samples)
                        peak_records=max(peak_records,metrics['peak_records'])
                        native_frontend_s+=max(0.0,elapsed-sum(samples))
                        if abs(state.time_s/3600-round(state.time_s/3600))<1e-8:
                            checkpoint=args.out/(args.label+'.last_valid'+checkpoint_suffix)
                            driver.save(checkpoint,state)
                            progress(state,checkpoint)
                        continue
                    state=driver.advance(state,min(end,state.time_s+args.step_s))
                    tick_times.append(time.perf_counter()-started_tick)
                    joint=state.runtime_state
                    road=joint.service.road
                    records=sum(len(q.parts) for c in road.cells for q in c.packets)
                    records+=sum(len(q.parts) for queue in road.pending for q in queue)
                    records+=len(joint.entering)+len(joint.egress)+len(joint.internal)+sum(map(len,joint.receipts))
                    peak_records=max(peak_records,records)
                    if abs(state.time_s/3600-round(state.time_s/3600))<1e-8:
                        checkpoint=args.out/(args.label+'.last_valid'+checkpoint_suffix)
                        driver.save(checkpoint,state)
                        progress(state,checkpoint)
                return state
            if args.horizon_s>=28800:
                state=advance_measured(state,28800)
                result['refinement_prefix']=driver.report(state)
            if args.resume and args.horizon_s>=43200:
                state=advance_measured(state,43200)
                middle=args.out/(args.label+'.middle'+checkpoint_suffix)
                driver.save(middle,state)
                state=driver.load(middle)
            state=advance_measured(state,args.horizon_s)
            final=args.out/(args.label+'.final'+checkpoint_suffix)
            driver.save(final,state)
            times=sorted(tick_times)
            result['tick_p50_s']=times[int((len(times)-1)*.5)] if times else None
            result['tick_p95_s']=times[int((len(times)-1)*.95)] if times else None
            result['peak_tracked_records']=peak_records
            result['tick_measurement_scope']=('native complete tick; frontend boundary cost separate'
                if getattr(driver,'engine_backend','python_oracle') in ('rust','rust_whole') else 'Python driver.advance wall time')
            result['native_frontend_boundary_s']=native_frontend_s
            result.update(status='EXECUTED_FOR_REVIEW',simulated_s=state.time_s,
                          report=driver.report(state),final_checkpoint_sha256=file_sha256(final))
    except (BudgetExceeded,ValueError,ArithmeticError,MemoryError,RuntimeError,ImportError,OSError) as exc:
        checkpoint=getattr(exc,'checkpoint',None)
        if hasattr(checkpoint,'report'):
            evidence=checkpoint.report()
        elif checkpoint is not None:
            suffix='.bin' if driver.engine_backend=='rust_whole' else '.json'
            path=args.out/(args.label+'.last_valid'+suffix)
            if driver.engine_backend=='rust_whole':
                result['failure_diagnostics']=driver.debug_state(checkpoint)
                result['last_native_metrics']=driver.runtime.last_advance_metrics
            driver.save(path,checkpoint)
            evidence=dict(path=path.name,time_s=checkpoint.time_s)
            state=checkpoint
            result['simulated_s']=checkpoint.time_s
            result['last_valid_report']=driver.report(checkpoint)
        else:
            evidence=None
        status=('BLOCKED_RESOURCE' if isinstance(exc,(BudgetExceeded,MemoryError)) else
                'NUMERICAL_ERROR' if isinstance(exc,ArithmeticError) else
                'ENVIRONMENT_BLOCKER' if isinstance(exc,(ImportError,OSError)) else 'BLOCKED')
        result.update(status=status,reason=type(exc).__name__+': '+str(exc),last_valid=evidence,
                      failure_classification=getattr(exc,'status',status))
        if status=='BLOCKED_RESOURCE':
            result['resource_limit_kind']=resource_limit_kind(str(exc),result.get('native_storage'))
    if driver is not None and result['engine_backend']=='rust_whole':
        # This is the latest validated road proposal even after a failed
        # coupled call; retain its explicit non-checkpointed scope.
        result['entry_projection']=driver.runtime.projection_diagnostics()
    result.update(wall_s=time.perf_counter()-started,
                  route_latency=route_latency.report(),
                  peak_rss_bytes=peak_rss_bytes())
    if result['engine_backend']=='rust_whole' and 'native_route_latency' not in result:
        result['native_route_latency']=dict(status='NOT_MEASURED',observed_calls=0,p99_ns=None,
            source='native_whole_router.route',reason='native engine construction did not complete')
    if result['peak_rss_bytes']>matrix['limits']['peak_rss_bytes']:
        result.update(status='BLOCKED_RESOURCE',reason='measured peak RSS exceeds release limit',
                      resource_limit_kind='measured_peak_rss')
    if result['wall_s']>matrix['limits'].get('wall_s',math.inf):
        result.update(status='BLOCKED_RESOURCE',reason='measured wall time exceeds release limit',
                      resource_limit_kind='wall_deadline')
    progress(state)
    atomic_json(args.out/(args.label+'.json'),result)
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
    parser.add_argument('--engine-backend',choices=('rust_whole','python_oracle','rust'),
        default=os.environ.get('METROFLOW_V1_ENGINE_BACKEND','rust_whole'),
        help='physical runtime (default: rust_whole; python_oracle is the explicit reference, rust the legacy native adapter)')
    parser.add_argument('--native-threads',type=int,
        default=os.environ.get('METROFLOW_V1_NATIVE_THREADS','1'),
        help='whole-native private Rayon workers, 1..256 (default: 1)')
    parser.add_argument('--storage-policy',choices=('bounded_bytes_v1','legacy_records'),
        default=os.environ.get('METROFLOW_V1_STORAGE_POLICY','bounded_bytes_v1'),
        help='whole-native storage guard (default: bounded_bytes_v1; changes checkpoint identity)')
    parser.add_argument('--entry-projection-width-s',type=float,
        default=os.environ.get('METROFLOW_V1_ENTRY_PROJECTION_WIDTH_S','0'),
        help='opt-in support-protected entry-time projection width; 0 is exact (changes checkpoint identity)')
    parser.add_argument('--road-representation',choices=('rows','mark_block_scaled_v1'),
        default=os.environ.get('METROFLOW_V1_ROAD_REPRESENTATION','rows'),
        help='road category storage; mark_block_scaled_v1 shares immutable category blocks with scalar coefficients (named numerical policy; requires a positive projection width; changes checkpoint identity)')
    args=parser.parse_args()
    if args.engine_backend not in ('rust_whole','python_oracle','rust'):
        parser.error('invalid METROFLOW_V1_ENGINE_BACKEND')
    if args.storage_policy not in ('bounded_bytes_v1','legacy_records'):
        parser.error('invalid METROFLOW_V1_STORAGE_POLICY')
    if not 1<=args.native_threads<=256:
        parser.error('--native-threads must be in 1..256')
    if not math.isfinite(args.entry_projection_width_s) or args.entry_projection_width_s < 0:
        parser.error('--entry-projection-width-s must be finite and nonnegative')
    if args.road_representation!='rows' and not args.entry_projection_width_s:
        parser.error('--road-representation mark_block_scaled_v1 requires a positive --entry-projection-width-s')
    if args.entry_projection_width_s and args.engine_backend!='rust_whole':
        parser.error('--entry-projection-width-s currently requires rust_whole campaign backend')
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
        for run_index,(name,step,resume,horizon) in enumerate(runs):
            label=case['id']+'.'+name
            cmd=[sys.executable,str(Path(__file__).resolve()),'--worker','--case',case['id'],
                 '--matrix',str(args.matrix),'--out',str(args.out),'--label',label,
                 '--step-s',str(step),'--horizon-s',str(horizon),
                 '--engine-backend',args.engine_backend,'--native-threads',str(args.native_threads),
                 '--storage-policy',args.storage_policy,
                 '--entry-projection-width-s',str(args.entry_projection_width_s),
                 '--road-representation',args.road_representation]
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
                        or (not args.prepare_only and receipt.get('simulated_s')!=horizon)
                        or receipt.get('matrix_sha256')!=hashlib.sha256(args.matrix.read_bytes()).hexdigest()):
                    receipt=dict(status='ENVIRONMENT_BLOCKER',reason='child exit or receipt binding differs',label=label)
            except subprocess.TimeoutExpired:
                receipt=dict(status='BLOCKED_RESOURCE',reason='wall deadline exceeded',label=label,
                             case=case['id'],resource_limit_kind='wall_deadline')
                suffix='.bin' if args.engine_backend=='rust_whole' else '.json'
                checkpoint=args.out/(label+'.last_valid'+suffix)
                if checkpoint.exists() and checkpoint.stat().st_mtime>=launch_wall:
                    receipt['last_valid_checkpoint']=checkpoint.name
            receipts.append(receipt)
            if receipt['status'] not in ('WHOLE_CALENDAR_PREPARED','EXECUTED_FOR_REVIEW'):
                for skipped,skip_step,skip_resume,skip_horizon in runs[run_index+1:]:
                    receipts.append(dict(case=case['id'],run_label=case['id']+'.'+skipped,
                        step_s=skip_step,horizon_s=skip_horizon,resume_requested=skip_resume,
                        status='NOT_RUN_DEPENDENCY_BLOCKED',blocked_by=label,
                        reason='same frozen candidate already failed; dependent repetitions add no new evidence'))
                break
    result=assess_campaign(receipts,matrix,cases,prepare_only=args.prepare_only)
    atomic_json(args.out/'CAMPAIGN.json',result)
    return 2 if result['status']=='BLOCKED' else 0


if __name__=='__main__':
    raise SystemExit(main())
