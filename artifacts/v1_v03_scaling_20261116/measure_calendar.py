"""Retain the unchanged full release calendar; this is not traffic execution."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import resource
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from tools.run_v1_acceptance import load_release_city  # noqa: E402
from tools.run_v1_local_acceptance import observed_environment  # noqa: E402
from metroflow.v1.activity import compile_activity  # noqa: E402
from metroflow.v1.factorized_demand import compile_factorized_demand  # noqa: E402
from metroflow.v1.release_plan import ReleasePlan  # noqa: E402


def peak_rss():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', default='river_weekday_s17')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    matrix_path = ROOT / 'scenarios/v1/release_matrix.json'
    matrix = json.loads(matrix_path.read_text())
    case = next(c for c in matrix['cases'] if c['id'] == args.case)
    sources = ['src/metroflow/v1/' + name + '.py' for name in ('factorized_demand', 'demand', 'activity', 'release_plan')]
    sources += ['scenarios/v1/release_matrix.json', 'artifacts/v1_v03_scaling_20261116/measure_calendar.py']
    result = dict(case=args.case, environment=observed_environment(),
                  git_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  source_sha256={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources},
                  scope='entire original calendar retained simultaneously; no routes or road runtime activated',
                  simulated_s=0, full_campaign='NOT_RUN', diagnostic_wall_limit_s=300,
                  diagnostic_rss_limit_bytes=matrix['limits']['peak_rss_bytes'])
    legs = []
    try:
        city, row = load_release_city(case)
        result.update(city_identity=city.identity, source_archive_sha256=row['source_sha256'], patch_sha256=row['patch_sha256'])
        homes = tuple(compile_activity(city, b.id) for b in city.face_graph.blocks if b.residents)
        jobs = tuple(compile_activity(city, b.id, 'job') for b in city.face_graph.blocks if b.jobs)
        services = tuple(compile_activity(city, b.id, 'service', service_stock=b.jobs) for b in city.face_graph.blocks if b.jobs)
        schedule = compile_factorized_demand(homes, jobs, services, day=case['day'], freight_kg=1000,
                                            worker_shortfall=matrix['worker_shortfall'])
        plan = ReleasePlan(city, schedule, step_s=10)
        result.update(schedule_identity=schedule.identity, calendar=plan.totals(), before_materialization_rss_bytes=peak_rss(),
                      preparation_wall_s=time.perf_counter()-started)
        materialize_started = time.perf_counter()
        for leg in schedule.iter_legs():
            legs.append(leg)
            if len(legs) % 8192 == 0:
                if peak_rss() > matrix['limits']['peak_rss_bytes']:
                    raise RuntimeError('diagnostic peak RSS limit exceeded')
                if time.perf_counter()-started > 300:
                    raise RuntimeError('diagnostic wall limit exceeded')
        result['materialization_wall_s'] = time.perf_counter()-materialize_started
        totals = {unit: math.fsum(getattr(leg.amounts, unit) for leg in legs) for unit in ('persons', 'vehicles', 'cargo_kg')}
        result['materialized_amounts'] = totals
        if len(legs) != result['calendar']['legs'] or any(
                abs(value-result['calendar'][unit]) > 1e-9*max(1, abs(value)) for unit, value in totals.items()):
            raise ValueError('full calendar count or amount differs from closed-form totals')
        result.update(status='FULL_CALENDAR_RETAINED_FOR_DIAGNOSIS', count_and_amounts_match=True)
    except (ValueError, RuntimeError, MemoryError) as exc:
        result.update(status='DIAGNOSTIC_BLOCKED', reason=type(exc).__name__+': '+str(exc))
    result.update(retained_legs=len(legs), peak_rss_bytes=peak_rss(), wall_s=time.perf_counter()-started)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(result), flush=True)
    return 0 if result['status'] == 'FULL_CALENDAR_RETAINED_FOR_DIAGNOSIS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
