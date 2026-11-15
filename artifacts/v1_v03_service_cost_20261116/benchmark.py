"""Paired service preparation cost on exact repeated endpoint measures."""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from metroflow.v1 import release_services as services  # noqa: E402
from metroflow.v1.activity import compile_activity  # noqa: E402
from metroflow.v1.demand import Amounts, TripLeg  # noqa: E402
from metroflow.v1.scenarios import scenario_city  # noqa: E402
from metroflow.v1.schedules import DepartureProfile, DepartureWindow  # noqa: E402

BASE = 'b41f807c490dda12e036bcb40d9c13370f04223e'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path(__file__).with_name('RESULT.json'))
    parser.add_argument('--pairs', type=int, default=5)
    parser.add_argument('--legs', type=int, default=1000)
    args = parser.parse_args()
    if args.pairs < 1 or args.legs < 1:
        parser.error('positive pairs and legs required')
    path = 'src/metroflow/v1/release_services.py'
    original_source = subprocess.check_output(
        ['git', 'show', BASE + ':' + path], cwd=ROOT, text=True)
    original_function = original_source[original_source.index('def compile_service_plan('):]
    # Use the unchanged baseline function with current identical record classes,
    # allowing full dataclass equality rather than a lossy projection.
    namespace = dict(vars(services))
    exec(compile(original_function, BASE + ':' + path, 'exec'), namespace)
    baseline = namespace['compile_service_plan']
    current = services.compile_service_plan
    city = scenario_city(1000)
    origin = compile_activity(city, 'block')
    destination = compile_activity(city, 'work', 'job')
    leg = TripLeg('bus', 'cohort', origin, destination, 'work', 'bus',
                  'scheduled_bus', Amounts(25, 1),
                  DepartureProfile((DepartureWindow(0, 2),)))
    legs = tuple(replace(leg, id=f'bus:{i}', cohort_id=f'cohort:{i}')
                 for i in range(args.legs))
    fleet = (services.BusCorridor('fleet', 'block', 'work', 1000, 40),)
    pairs = []
    for index in range(args.pairs):
        results, elapsed = {}, {}
        order = ('baseline', 'cached') if index % 2 == 0 else ('cached', 'baseline')
        for name in order:
            begin = time.perf_counter()
            results[name] = (baseline if name == 'baseline' else current)(
                city, legs, fleet, max_legs=args.legs)
            elapsed[name] = time.perf_counter() - begin
        equal = results['baseline'] == results['cached']
        if not equal:
            raise AssertionError('service plan changed')
        pairs.append(dict(pair=index, order=order, wall_s=elapsed, full_plan_equal=equal))
    baseline_mean = statistics.mean(row['wall_s']['baseline'] for row in pairs)
    cached_mean = statistics.mean(row['wall_s']['cached'] for row in pairs)
    receipt = dict(
        scope='two-block synthetic fixture; exact service preparation only, not full city or RSS',
        baseline_commit=BASE,
        baseline_source_sha256=hashlib.sha256(original_source.encode()).hexdigest(),
        candidate_source_sha256=hashlib.sha256((ROOT / path).read_bytes()).hexdigest(),
        environment=dict(python=platform.python_version(), platform=platform.platform()),
        legs=args.legs, distinct_endpoint_measures=2, access_cache_maxsize=256,
        pairs=pairs, mean_wall_s=dict(baseline=baseline_mean, cached=cached_mean),
        speedup=baseline_mean / cached_mean,
        all_full_plans_equal=all(row['full_plan_equal'] for row in pairs))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(mean_wall_s=receipt['mean_wall_s'],
                          speedup=receipt['speedup'], all_full_plans_equal=True)))


if __name__ == '__main__':
    main()
