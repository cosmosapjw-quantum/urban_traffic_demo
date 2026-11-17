"""Guarded actual-city whole-calendar activation; scoped evidence, not acceptance.

The worker uses every FactorizedSchedule leg. A short horizon or preparation
receipt does not certify the three-city repeated one-day release campaign.
"""
import argparse
import hashlib
import json
import os
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
from metroflow.v1.release_inventory import InventoryPolicy, build_inventory
from metroflow.v1.native_release_driver import NativeReleaseDriver
from metroflow.active_suffix.common import BudgetExceeded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', default='valley_weekday_s7')
    parser.add_argument('--horizon-s', type=float, default=10)
    parser.add_argument('--byte-budget', type=int, default=6*1024**3)
    parser.add_argument('--record-budget', type=int, default=20000)
    parser.add_argument('--wall-s', type=int, default=300)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if (args.horizon_s < 0 or args.horizon_s > 86400 or args.horizon_s % 10
            or not 1 <= args.byte_budget <= 6*1024**3
            or not 1 <= args.record_budget <= 2000000 or not 1 <= args.wall_s <= 7200):
        parser.error('aligned 0..86400 s horizon, <=6 GiB accounting and positive budgets required')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if not args.worker:
        command = [sys.executable, str(Path(__file__).resolve()), '--worker', '--case', args.case,
            '--horizon-s', str(args.horizon_s), '--byte-budget', str(args.byte_budget),
            '--record-budget', str(args.record_budget), '--out', str(args.out)]
        env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                   MKL_NUM_THREADS='1', METROFLOW_V1_ROUTING_BACKEND='rust')
        # A fresh progress receipt prevents a stale success after a killed worker.
        args.out.write_text(json.dumps(dict(status='STARTING', case=args.case,
            full_campaign='NOT_RUN', simulated_s=0))+'\n')
        started = time.perf_counter()
        try:
            completed = subprocess.run(command, env=env, timeout=args.wall_s)
            receipt = json.loads(args.out.read_text())
            if completed.returncode and not receipt['status'].startswith(('BLOCKED', 'FAILED')):
                receipt.update(status='ENVIRONMENT_BLOCKER', exit_code=completed.returncode)
        except subprocess.TimeoutExpired:
            receipt = json.loads(args.out.read_text())
            receipt.update(status='BLOCKED_RESOURCE', reason='external wall deadline exceeded',
                           deadline_s=args.wall_s)
        receipt['supervisor_wall_s'] = time.perf_counter()-started
        args.out.write_text(json.dumps(receipt, indent=2, allow_nan=False)+'\n')
        print(json.dumps(receipt, allow_nan=False), flush=True)
        return 0 if receipt['status'] == 'PASS_SCOPED' else 2

    resource.setrlimit(resource.RLIMIT_AS, (8*1024**3, 8*1024**3))
    started = time.perf_counter()
    matrix_path = ROOT/'scenarios/v1/release_matrix.json'
    matrix = json.loads(matrix_path.read_text())
    case = next(c for c in matrix['cases'] if c['id'] == args.case)
    result = dict(case=args.case, backend='rust_whole', environment=observed_environment(),
        full_campaign='NOT_RUN', diagnostic_prefix=False, simulated_s=0,
        step_s=10, horizon_s=args.horizon_s, native_accounting_budget_bytes=args.byte_budget,
        logical_record_budget=args.record_budget, address_space_limit_bytes=8*1024**3,
        matrix_sha256=hashlib.sha256(matrix_path.read_bytes()).hexdigest(),
        baseline_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_hashes={})
    for folder, pattern in [('crates/metroflow-rust/src', '*.rs'), ('src/metroflow/v1', 'native*.py')]:
        for source in sorted((ROOT/folder).glob(pattern)):
            result['source_hashes'][str(source.relative_to(ROOT))] = hashlib.sha256(source.read_bytes()).hexdigest()
    from metroflow.v1.native_engine import native_binary_provenance
    result["native_binary"] = native_binary_provenance()
    if result["native_binary"]["status"] != "MEASURED":
        raise RuntimeError(result["native_binary"]["reason"])
    result['native_binary_sha256'] = result["native_binary"]["sha256"]
    model = state = None

    def progress(phase):
        result.update(phase=phase, wall_s=time.perf_counter()-started,
            peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
        args.out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')

    try:
        result['status'] = 'RUNNING'
        progress('city')
        city, source = load_release_city(case)
        homes = tuple(compile_activity(city, b.id) for b in city.face_graph.blocks if b.residents)
        jobs = tuple(compile_activity(city, b.id, 'job') for b in city.face_graph.blocks if b.jobs)
        services = tuple(compile_activity(city, b.id, 'service', service_stock=b.jobs)
                         for b in city.face_graph.blocks if b.jobs)
        schedule = compile_factorized_demand(homes, jobs, services, day=case['day'],
            freight_kg=1000, worker_shortfall=matrix['worker_shortfall'])
        plan = ReleasePlan(city, schedule, step_s=10)
        policy = dict(matrix['inventory_policy'])
        policy['departures_s'] = tuple(policy['departures_s'])
        inventory = build_inventory(city, InventoryPolicy(**policy))
        result.update(city_identity=city.identity, schedule_identity=schedule.identity,
            source_archive_sha256=source['source_sha256'], full_calendar_totals=plan.totals(),
            inventory_identity=inventory.identity)
        progress('native_full_construction')
        construct = time.perf_counter()
        model = NativeReleaseDriver(plan, inventory, step_s=10, byte_budget=args.byte_budget,
                                    record_budget=args.record_budget)
        result['native_construction_s'] = time.perf_counter()-construct
        state = model.initial()
        result['initial_report'] = model.report(state)
        result['activated_legs'] = model.cursor.offset
        result['unactivated_legs'] = plan.totals()['legs']-model.cursor.offset
        progress('native_evolution')
        evolve = time.perf_counter()
        state = model.advance(state, args.horizon_s)
        result.update(status='PASS_SCOPED', simulated_s=state.time_s,
            evolution_s=time.perf_counter()-evolve, report=model.report(state),
            advance_metrics=model.runtime.last_advance_metrics)
    except Exception as exc:
        state = getattr(exc, 'checkpoint', state)
        result.update(status='BLOCKED_RESOURCE' if isinstance(exc, (BudgetExceeded, MemoryError))
                      or 'BLOCKED_RESOURCE' in str(exc) else 'FAILED',
            reason=type(exc).__name__+': '+str(exc))
        if state is not None:
            result.update(simulated_s=state.time_s, last_valid_time_s=state.time_s)
    if model is not None and state is not None:
        checkpoint = args.out.with_suffix('.checkpoint.bin')
        saved = time.perf_counter()
        model.save(checkpoint, state)
        restored = model.load(checkpoint)
        if model.report(restored) != model.report(state):
            raise AssertionError('native binary restart report differs')
        result.update(checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
            checkpoint_bytes=checkpoint.stat().st_size, checkpoint_roundtrip_s=time.perf_counter()-saved,
            checkpoint_report_equal=True)
    progress('finished')
    return 0 if result['status'] == 'PASS_SCOPED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
