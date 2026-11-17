"""Measure one exact bounded calendar prefix on a frozen release city.

This prepares one shared runtime without advancing it. It is not a full-city
run or a smaller replacement for the declared release demand.
"""
import argparse
from dataclasses import asdict
import hashlib
import itertools
import json
import math
from pathlib import Path
import resource
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

from tools.run_v1_acceptance import load_release_city  # noqa: E402
from tools.run_v1_local_acceptance import observed_environment  # noqa: E402
from metroflow.active_suffix.common import BudgetExceeded  # noqa: E402
from metroflow.route_metrics import RouteLatencyMeasurements  # noqa: E402
from metroflow.v1.activity import compile_activity  # noqa: E402
from metroflow.v1.factorized_demand import compile_factorized_demand  # noqa: E402
from metroflow.v1.joint_release_runtime import JointReleaseRuntime  # noqa: E402
from metroflow.v1.release_inventory import InventoryPolicy, build_inventory  # noqa: E402
from metroflow.v1.release_plan import PlanCursor, ReleasePlan  # noqa: E402
from metroflow.v1.release_services import compile_service_plan  # noqa: E402


def source_manifest():
    """Hash the actually imported repository Python sources and this script."""
    paths = {Path(__file__).resolve()}
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            if ((path.is_relative_to(ROOT/'src') or path.is_relative_to(ROOT/'tools'))
                    and path.suffix == '.py'):
                paths.add(path)
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)}


def measure(case, matrix, count, step_s, matrix_path):
    started = time.perf_counter()
    result = dict(schema='metroflow_v03_bounded_preparation_v1', case=case['id'],
        status='PREPARING', requested_prefix_legs=count, simulated_s=0,
        full_campaign='NOT_RUN', environment=observed_environment(), step_s=step_s,
        matrix_sha256=hashlib.sha256(matrix_path.read_bytes()).hexdigest(),
        scope='exact calendar prefix; one shared runtime prepared, zero ticks executed; '
              'remaining calendar amounts retained; no full-city runtime/RSS extrapolation')
    with RouteLatencyMeasurements() as route_latency:
        try:
            city, row = load_release_city(case)
            result.update(city_identity=city.identity, source_sha256=row['source_sha256'],
                          patch_sha256=row['patch_sha256'])
            homes = tuple(compile_activity(city, b.id) for b in city.face_graph.blocks
                          if b.residents)
            jobs = tuple(compile_activity(city, b.id, 'job') for b in city.face_graph.blocks
                         if b.jobs)
            services = tuple(compile_activity(city, b.id, 'service', service_stock=b.jobs)
                             for b in city.face_graph.blocks if b.jobs)
            schedule = compile_factorized_demand(homes, jobs, services, day=case['day'],
                freight_kg=1000, worker_shortfall=matrix['worker_shortfall'])
            plan = ReleasePlan(city, schedule, step_s=step_s)
            result.update(schedule_identity=schedule.identity,
                          calendar_before_preparation=plan.summary(plan.cursor()))
            legs = tuple(itertools.islice(schedule.iter_legs(), count))
            cursor = PlanCursor(schedule.identity, len(legs),
                *(math.fsum(getattr(leg.amounts, unit) for leg in legs)
                  for unit in ('persons', 'vehicles', 'cargo_kg')))
            # This checks the exact original prefix amounts, not only totals.
            result.update(cursor=asdict(cursor), calendar=plan.summary(cursor),
                          prepared_prefix_legs=len(legs),
                          prefix_amounts={unit: getattr(cursor, 'materialized_' + unit)
                                          for unit in ('persons', 'vehicles', 'cargo_kg')},
                          units=dict(persons='person-leg amounts, outward and return counted separately',
                                     vehicles='vehicle-leg amounts', cargo_kg='kg',
                                     resident_stock='persons'))
            policy = dict(matrix['inventory_policy'])
            policy['departures_s'] = tuple(policy['departures_s'])
            inventory = build_inventory(city, InventoryPolicy(**policy))
            service_plan = compile_service_plan(city, legs, inventory.corridors,
                depot_block_id=inventory.depot_block_id, step_s=step_s,
                max_legs=matrix['route_materialization_budget'])
            runtime = JointReleaseRuntime(city, legs, service_plan, step_s=step_s,
                                         max_legs=matrix['route_materialization_budget'])
            state = runtime.initial()
            runtime.check(state)
            result.update(status='BOUNDED_PREFIX_PREPARED', runtime_identity=runtime.identity,
                inventory_identity=inventory.identity,
                fixed_fleet_runs=inventory.physical_run_vehicles,
                registered_car_routes=len(runtime.routes),
                internal_laws=len(runtime.internal_laws),
                service_assignment=service_plan.assignment_report(),
                initial_execution=runtime.report(state))
        except (BudgetExceeded, ValueError, MemoryError) as exc:
            result.update(status='BLOCKED_PREPARATION',
                          failure_status=getattr(exc, 'status', type(exc).__name__),
                          reason=str(exc))
        result['route_latency'] = route_latency.report()
    result.update(wall_s=time.perf_counter()-started,
        peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss *
                       (1 if sys.platform == 'darwin' else 1024),
        source_manifest_sha256=source_manifest())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True)
    parser.add_argument('--legs', type=int, default=256)
    parser.add_argument('--step-s', type=float, default=10)
    parser.add_argument('--matrix', type=Path,
                        default=ROOT/'scenarios/v1/release_matrix.json')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    matrix = json.loads(args.matrix.read_text())
    case = next((c for c in matrix['cases'] if c['id'] == args.case), None)
    if case is None:
        parser.error('select a case from the unchanged release matrix')
    cap = min(20000, matrix['route_materialization_budget'])
    if not (1 <= args.legs <= cap and math.isfinite(args.step_s) and args.step_s > 0):
        parser.error(f'prefix legs must be 1..{cap}; positive finite step required')
    result = measure(case, matrix, args.legs, args.step_s, args.matrix)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps({key: result[key] for key in ('case', 'status', 'simulated_s',
                                                 'wall_s', 'route_latency')}), flush=True)
    return 0 if result['status'] == 'BOUNDED_PREFIX_PREPARED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
