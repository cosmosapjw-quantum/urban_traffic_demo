"""Matched actual-city calendar-prefix runtime measurements, not V03 acceptance.

The prefix is an explicit diagnostic input. Omitted calendar legs are recorded
as unactivated and cannot be treated as a full-city conservation certificate.
"""
import argparse
from dataclasses import replace
import hashlib
import itertools
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
from metroflow.v1.joint_release_runtime import JointReleaseRuntime
from metroflow.v1.release_plan import ReleasePlan
from metroflow.v1.release_inventory import InventoryPolicy, build_inventory
from metroflow.v1.release_services import compile_service_plan
from metroflow.active_suffix.common import BudgetExceeded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=('python_oracle', 'rust'), required=True)
    parser.add_argument('--case', default='river_weekday_s17')
    parser.add_argument('--legs', type=int, default=256)
    parser.add_argument('--horizon-s', type=float, default=28800)
    parser.add_argument('--start-s', type=float, default=0,
                        help='optional analytically empty pre-source clock, validated before use')
    parser.add_argument('--record-budget', type=int, default=20000)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if (args.legs < 1 or args.horizon_s <= args.start_s or args.start_s < 0
            or not 1 <= args.record_budget <= 2000000):
        parser.error('positive diagnostic prefix and horizon required')
    started = time.perf_counter()
    resource.setrlimit(resource.RLIMIT_AS, (8*1024**3, 8*1024**3))
    os.environ['METROFLOW_V1_ROUTING_BACKEND'] = 'rust'
    matrix_path = ROOT/'scenarios/v1/release_matrix.json'
    matrix = json.loads(matrix_path.read_text())
    case = next(c for c in matrix['cases'] if c['id'] == args.case)
    result = dict(case=args.case, backend=args.backend, environment=observed_environment(),
                  full_campaign='NOT_RUN', diagnostic_prefix=True, simulated_s=0,
                  step_s=10, horizon_s=args.horizon_s, routing_backend='rust',
                  start_s=args.start_s,
                  record_budget=args.record_budget,
                  matrix_sha256=hashlib.sha256(matrix_path.read_bytes()).hexdigest(),
                  address_space_limit_bytes=8*1024**3)
    model = state = tick_started = None
    try:
        city, source = load_release_city(case)
        homes = tuple(compile_activity(city, b.id) for b in city.face_graph.blocks if b.residents)
        jobs = tuple(compile_activity(city, b.id, 'job') for b in city.face_graph.blocks if b.jobs)
        services = tuple(compile_activity(city, b.id, 'service', service_stock=b.jobs)
                         for b in city.face_graph.blocks if b.jobs)
        schedule = compile_factorized_demand(homes, jobs, services, day=case['day'],
                    freight_kg=1000, worker_shortfall=matrix['worker_shortfall'])
        totals = ReleasePlan(city, schedule, step_s=10).totals()
        legs = tuple(itertools.islice(schedule.iter_legs(), args.legs))
        result.update(city_identity=city.identity, schedule_identity=schedule.identity,
                      source_archive_sha256=source['source_sha256'],
                      activated_legs=len(legs), unactivated_legs=totals['legs']-len(legs),
                      full_calendar_totals=totals)
        policy = dict(matrix['inventory_policy'])
        policy['departures_s'] = tuple(policy['departures_s'])
        inventory = build_inventory(city, InventoryPolicy(**policy))
        plan = compile_service_plan(city, legs, inventory.corridors,
                    depot_block_id=inventory.depot_block_id, step_s=10, max_legs=len(legs))
        cls = JointReleaseRuntime
        if args.backend == 'rust':
            from metroflow.v1.native_journey import NativeJointReleaseRuntime
            cls = NativeJointReleaseRuntime
        model = cls(city, legs, plan, step_s=10, max_legs=len(legs),
                    record_budget=args.record_budget)
        state = model.initial()
        if args.start_s:
            # Before every source, the physical vacuum and zero journey state
            # are invariant; only the absolute clock changes. No occupied
            # trajectory, service departure or intent release may be skipped.
            if (args.start_s % 10 or any(l.departures.fraction(0, args.start_s) for l in legs)
                    or any(b.departures_s[0] < args.start_s for b in model.service.buses)
                    or any(f.departure_s < args.start_s for f in model.service.freight)
                    or any(c.departure_s < args.start_s for c in model.service.cars)
                    or any(p.available_s < args.start_s for p in model.service.passengers)):
                raise ValueError('requested warm start skips nonempty source/history')
            state = replace(state, service=replace(state.service,
                            road=replace(state.service.road, time_s=args.start_s)))
            model.check(state)
            result['initialization'] = 'derived invariant vacuum before every source; absolute clock preserved'
        result['preparation_s'] = time.perf_counter()-started
        tick_started = time.perf_counter()
        state = model.advance(state, args.horizon_s)
        result.update(evolution_s=time.perf_counter()-tick_started,
                      simulated_s=state.time_s, report=model.report(state), status='PASS_SCOPED')
    except Exception as exc:
        state = getattr(exc, 'checkpoint', state)
        result.update(status='BLOCKED_RESOURCE' if isinstance(exc, (BudgetExceeded, MemoryError))
                      else 'FAILED', error=type(exc).__name__+': '+str(exc))
        if tick_started is not None:
            result['evolution_s'] = time.perf_counter()-tick_started
        if state is not None:
            result['last_valid_time_s'] = state.time_s
            result['simulated_s'] = state.time_s
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if model is not None and state is not None:
        road = state.service.road
        result['final_records'] = dict(
            road=sum(len(q.parts) for c in road.cells for q in c.packets)
                 + sum(len(q.parts) for queue in road.pending for q in queue),
            journey=len(state.entering)+len(state.egress)+len(state.internal)
                    + sum(map(len, state.receipts)))
        path = args.out.with_suffix('.checkpoint.json')
        model.save(path, state)
        result['checkpoint_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    result.update(wall_s=time.perf_counter()-started,
                  peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
    import _metroflow_rust
    result['native_binary_sha256'] = hashlib.sha256(Path(_metroflow_rust.__file__).read_bytes()).hexdigest()
    result['rustc'] = subprocess.check_output(['rustc', '--version'], text=True).strip()
    paths = (list((ROOT/'crates/metroflow-rust/src').glob('v1_*.rs'))
             + list((ROOT/'src/metroflow/v1').glob('native_*.py')) + [Path(__file__)])
    result['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in paths}
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k: result.get(k) for k in ('case', 'backend', 'status', 'simulated_s',
                                               'evolution_s', 'peak_rss_bytes', 'error')}), flush=True)
    return 0 if result['status'] == 'PASS_SCOPED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
