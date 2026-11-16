"""Replay a bounded occupied interval from a pinned whole-native checkpoint.

Reports stage/queue lifecycle diagnostics and fixed-input serial/parallel timing.
Never changes the record limit or continues the release DAG/campaign.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'src')]
from tools.run_v1_acceptance import load_release_city
from tools.run_v1_local_acceptance import observed_environment
from metroflow.v1.activity import compile_activity
from metroflow.v1.factorized_demand import compile_factorized_demand
from metroflow.v1.release_inventory import InventoryPolicy, build_inventory
from metroflow.v1.release_plan import ReleasePlan
from metroflow.v1.native_release_driver import NativeReleaseDriver
from metroflow.active_suffix.common import BudgetExceeded


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024**2), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--receipt', type=Path, required=True)
    p.add_argument('--end-s', type=float, required=True)
    p.add_argument('--threads', type=int, default=1)
    p.add_argument('--repeat', type=int, default=3)
    p.add_argument('--trace', action='store_true')
    p.add_argument('--baseline-api', action='store_true', help='explicit pre-debug API, serial only')
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    source = json.loads(args.receipt.read_text())
    start = source['simulated_s']
    if (not 1 <= args.threads <= 256 or not 1 <= args.repeat <= 10
            or not math.isfinite(args.end_s) or not start <= args.end_s <= start+600
            or (args.end_s-start) % source['step_s']
            or (args.baseline_api and args.threads != 1)):
        p.error('bounded <=600s aligned replay, 1..256 workers, 1..10 repeats required')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    resource.setrlimit(resource.RLIMIT_AS, (8*1024**3, 8*1024**3))
    os.environ['METROFLOW_V1_ROUTING_BACKEND'] = 'rust'
    import _metroflow_rust
    matrix_path = ROOT/'scenarios/v1/release_matrix.json'
    if digest(matrix_path) != source['matrix_sha256']:
        raise ValueError('source matrix binding differs')
    checkpoint = args.receipt.with_suffix('.checkpoint.bin')
    if digest(checkpoint) != source['checkpoint_sha256']:
        raise ValueError('source checkpoint bytes differ')
    result = dict(status='RUNNING', case=source['case'], start_s=start, end_s=args.end_s,
        native_threads=args.threads, repeat=args.repeat, trace=args.trace,
        baseline_api=args.baseline_api, full_campaign='NOT_RUN', dag_progress='19/21',
        environment=observed_environment(), source_receipt_sha256=digest(args.receipt),
        source_checkpoint_sha256=source['checkpoint_sha256'],
        native_binary_sha256=digest(_metroflow_rust.__file__),
        baseline_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        record_budget=source['logical_record_budget'], source_hashes={})
    result['environment']['scientific_threads'] = args.threads
    files = [ROOT/'Cargo.lock', ROOT/'crates/metroflow-rust/Cargo.toml', Path(__file__)]
    files += sorted((ROOT/'crates/metroflow-rust/src').glob('v1_*.rs'))
    files += sorted((ROOT/'src/metroflow/v1').glob('native*.py'))
    for path in files:
        result['source_hashes'][str(path.relative_to(ROOT))] = digest(path)
    args.out.write_text(json.dumps(result, indent=2)+'\n')
    matrix = json.loads(matrix_path.read_text())
    case = next(c for c in matrix['cases'] if c['id'] == source['case'])
    city, _ = load_release_city(case)
    homes = tuple(compile_activity(city, b.id) for b in city.face_graph.blocks if b.residents)
    jobs = tuple(compile_activity(city, b.id, 'job') for b in city.face_graph.blocks if b.jobs)
    services = tuple(compile_activity(city, b.id, 'service', service_stock=b.jobs)
                     for b in city.face_graph.blocks if b.jobs)
    schedule = compile_factorized_demand(homes, jobs, services, day=case['day'], freight_kg=1000,
                                        worker_shortfall=matrix['worker_shortfall'])
    policy = dict(matrix['inventory_policy'])
    policy['departures_s'] = tuple(policy['departures_s'])
    options = {} if args.baseline_api else dict(native_threads=args.threads)
    driver = NativeReleaseDriver(ReleasePlan(city, schedule, step_s=source['step_s']),
        build_inventory(city, InventoryPolicy(**policy)), step_s=source['step_s'],
        byte_budget=source['native_accounting_budget_bytes'],
        record_budget=source['logical_record_budget'], **options)
    seed = driver.load(checkpoint)
    if seed.time_s != start:
        raise AssertionError('source receipt/checkpoint clocks differ')
    seed_report = driver.report(seed)
    result['runs'] = []
    if not args.baseline_api:
        result['execution_config'] = driver.runtime.native.execution_config()
        result['seed_debug'] = driver.runtime.debug_state(seed.runtime_state)
    with tempfile.TemporaryDirectory(dir=args.out.parent) as folder:
        final_path = Path(folder)/'result.bin'
        for iteration in range(args.repeat):
            state = seed
            run = dict(iteration=iteration, status='PASS_SCOPED', advance_wall_s=0., ticks=[])
            trace = []
            if args.trace and not args.baseline_api:
                trace.append(driver.runtime.debug_state(state.runtime_state))
            while state.time_s < args.end_s:
                end = min(args.end_s, state.time_s+source['step_s']) if args.trace else args.end_s
                began = time.perf_counter()
                try:
                    state = driver.advance(state, end)
                except BudgetExceeded as exc:
                    state = exc.checkpoint
                    run.update(status='BLOCKED_RESOURCE', reason=str(exc))
                run['advance_wall_s'] += time.perf_counter()-began
                run['ticks'].extend(driver.runtime.last_advance_metrics['tick_times_s'])
                if args.trace and not args.baseline_api:
                    trace.append(driver.runtime.debug_state(state.runtime_state))
                if run['status'] != 'PASS_SCOPED':
                    break
            run.update(simulated_s=state.time_s, report=driver.report(state))
            run['last_advance_metrics'] = driver.runtime.last_advance_metrics
            if not args.baseline_api:
                run['debug'] = driver.runtime.debug_state(state.runtime_state)
            if args.trace:
                run['trace'] = trace
            driver.save(final_path, state)
            run['checkpoint_sha256'] = digest(final_path)
            driver.save(final_path, seed)
            run['seed_byte_unchanged'] = digest(final_path) == source['checkpoint_sha256']
            if not run['seed_byte_unchanged'] or driver.report(seed) != seed_report:
                raise AssertionError('replay changed original immutable snapshot')
            result['runs'].append(run)
            args.out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    hashes = {run['checkpoint_sha256'] for run in result['runs']}
    if len(hashes) != 1:
        raise AssertionError('repeated fixed-input checkpoints differ')
    result.update(status=result['runs'][0]['status'], repeated_byte_identity=True,
        median_advance_wall_s=statistics.median(run['advance_wall_s'] for run in result['runs']),
        peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k:result[k] for k in ('status','native_threads','median_advance_wall_s',
          'peak_rss_bytes','repeated_byte_identity')}), flush=True)
    return 0 if result['status'] == 'PASS_SCOPED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
