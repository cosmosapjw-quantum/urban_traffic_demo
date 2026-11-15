"""Paired exact constructor comparison against the published parent source.

Run with the repository's supported Python. This measures bounded fixtures;
it is not a 100k-city runtime, RSS or completion receipt.
"""
import argparse
from dataclasses import asdict, replace
import gc
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from metroflow.v1.activity import ActivityPatch, compile_activity  # noqa: E402
from metroflow.v1.demand import Amounts, TripLeg  # noqa: E402
from metroflow.v1.journey import DelayLaw  # noqa: E402
import metroflow.v1.release_runtime as revised  # noqa: E402
from metroflow.v1.scenarios import scenario_city  # noqa: E402
from metroflow.v1.schedules import DepartureProfile, DepartureWindow  # noqa: E402

BASE = 'b41f807c490dda12e036bcb40d9c13370f04223e'
SOURCE = 'src/metroflow/v1/release_runtime.py'


def load_baseline():
    source = subprocess.check_output(['git', 'show', f'{BASE}:{SOURCE}'], cwd=ROOT)
    name = 'metroflow.v1._constructor_baseline'
    module = types.ModuleType(name)
    module.__package__ = 'metroflow.v1'
    sys.modules[name] = module
    exec(compile(source, f'{BASE}:{SOURCE}', 'exec'), module.__dict__)
    return module, hashlib.sha256(source).hexdigest()


def fixture():
    city = scenario_city(1000)
    nodes = {n.id: n for n in city.roadmap.nodes}
    measures = []
    for block, kind in [('block', 'residential'), ('work', 'job')]:
        door = next(p for p in city.portals if p.block_id == block)
        xy = nodes[door.node_id].xyz[:2]
        measures.append(compile_activity(city, block, kind,
                        patches=(ActivityPatch(1000, (xy,)),)))
    leg = TripLeg('out', 'cohort', *measures, 'work', 'car', 'car', Amounts(1.25, 1),
                  DepartureProfile((DepartureWindow(0, 2),)))
    return city, leg


def calendars(leg, internal_count, road_count):
    internal = []
    for i in range(internal_count // 2):
        outward = replace(leg, id=f'out:{i}', cohort_id=f'c:{i}',
                           destination=leg.origin, mode='noncar', vehicle_class=None,
                           amounts=Amounts(persons=3), intrazonal=DelayLaw(((10, 1),)))
        internal.extend((outward, replace(outward, id=f'back:{i}', depends_on=outward.id,
                          purpose='return_home', minimum_dwell_s=10)))
    road = tuple(replace(leg, id=f'road:{i}') for i in range(road_count))
    return {'internal': tuple(internal), 'road': road}


def instrument(module):
    counts = {'candidate_paths': 0, 'activity_access': 0}
    originals = {}
    for name in counts:
        function = getattr(module, name)
        originals[name] = function

        def counted(*args, _name=name, _function=function, **kwargs):
            counts[_name] += 1
            return _function(*args, **kwargs)

        setattr(module, name, counted)
    return counts, originals


def id_reads(module, city, legs):
    class CountedLeg:
        reads = 0

        def __init__(self, value):
            self.value = value

        @property
        def id(self):
            type(self).reads += 1
            return self.value.id

        def __getattr__(self, name):
            return getattr(self.value, name)

    model = module.ReleaseRuntime(city, tuple(CountedLeg(leg) for leg in legs))
    return CountedLeg.reads, model.identity


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--internal-legs', type=int, default=4000)
    parser.add_argument('--road-legs', type=int, default=256)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not (args.repetitions > 0 and 2 <= args.internal_legs <= 20000
            and args.internal_legs % 2 == 0 and 1 <= args.road_legs <= 20000):
        parser.error('positive repetitions, even 2..20000 internal legs, 1..20000 road legs')
    baseline, baseline_sha = load_baseline()
    city, leg = fixture()
    cases = calendars(leg, args.internal_legs, args.road_legs)
    result = dict(status='SCOPED_CONSTRUCTOR_COMPARISON', base_commit=BASE,
                  baseline_source_sha256=baseline_sha, python=sys.version,
                  platform=platform.platform(), cases={},
                  scope='bounded fixtures; no actual-city/full-day/RSS extrapolation',
                  max_legs_unchanged=20000,
                  source_sha256={p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
                                 for p in (SOURCE, 'src/metroflow/route_metrics.py')})
    modules = {'baseline': baseline, 'revised': revised}
    diagnostic = calendars(leg, 100, 1)['internal']
    counts = {k: id_reads(m, city, diagnostic) for k, m in modules.items()}
    assert counts['baseline'][1] == counts['revised'][1]
    result['parent_lookup'] = dict(legs=len(diagnostic), identity_equal=True,
                                  id_reads={k: count[0] for k,count in counts.items()})
    for kind, legs in cases.items():
        measurements = {key: [] for key in modules}
        rows = []
        for repetition in range(args.repetitions):
            models = {}
            calls = {}
            for key in (('baseline', 'revised') if repetition % 2 == 0
                        else ('revised', 'baseline')):
                module = modules[key]
                count, original = instrument(module)
                gc.collect()
                start = time.perf_counter()
                models[key] = module.ReleaseRuntime(city, legs, max_legs=len(legs))
                measurements[key].append(time.perf_counter() - start)
                calls[key] = dict(count)
                for name, function in original.items():
                    setattr(module, name, function)
            a, b = models['baseline'], models['revised']
            assert a.identity == b.identity
            assert a.route_links == b.route_links
            assert a.model.boundaries == b.model.boundaries
            assert a.internal_laws == b.internal_laws
            rows.append(dict(repetition=repetition, identity=a.identity,
                             identity_routes_boundaries_laws_equal=True, calls=calls))
        result['cases'][kind] = dict(legs=len(legs), wall_s=measurements,
            mean_wall_s={k: statistics.mean(v) for k,v in measurements.items()}, runs=rows)
    # Full-state comparison includes actual shared-road completion and returns,
    # while avoiding claiming a large calendar's complete daily execution.
    outward = replace(leg, id='exact-out')
    returning = replace(leg, id='exact-back', origin=leg.destination,
                        destination=leg.origin, depends_on=outward.id,
                        purpose='return_home', minimum_dwell_s=10)
    a = baseline.ReleaseRuntime(city, (outward, returning))
    b = revised.ReleaseRuntime(city, (outward, returning))
    a_state, b_state = a.advance(a.initial(), 120), b.advance(b.initial(), 120)
    assert asdict(a_state) == asdict(b_state)
    assert a.report(a_state) == b.report(b_state)
    result['shared_return_fixture'] = dict(simulated_s=120, full_state_and_report_equal=True,
                                          completed=list(b_state.completed))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v['mean_wall_s'] for k,v in result['cases'].items()}))


if __name__ == '__main__':
    main()
