"""Compare checkpoint checking on identical finite pending-journey states."""
import argparse
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from types import MethodType

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from metroflow.v1.activity import compile_activity  # noqa: E402
from metroflow.v1.demand import Amounts, TripLeg  # noqa: E402
from metroflow.v1.joint_release_runtime import JointReleaseRuntime  # noqa: E402
from metroflow.v1.journey import DelayLaw  # noqa: E402
from metroflow.v1.release_services import compile_service_plan  # noqa: E402
from metroflow.v1.scenarios import scenario_city  # noqa: E402
from metroflow.v1.schedules import DepartureProfile, DepartureWindow  # noqa: E402

BASE = 'b41f807c490dda12e036bcb40d9c13370f04223e'
SOURCE = 'src/metroflow/v1/joint_release_runtime.py'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legs', type=int, default=1500)
    parser.add_argument('--repetitions', type=int, default=5)
    parser.add_argument('--out', type=Path, default=Path(__file__).with_name('RESULT.json'))
    args = parser.parse_args()
    reference = subprocess.check_output(['git', 'show', f'{BASE}:{SOURCE}'], cwd=ROOT)
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / 'reference.py'
        path.write_bytes(reference)
        name = 'metroflow.v1._joint_cost_reference'
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        old_check = module.JointReleaseRuntime.check

    city = scenario_city(1000)
    measure = compile_activity(city, 'block')
    profile = DepartureProfile((DepartureWindow(0, 2),))
    law = DelayLaw(((100., 1.),))
    legs = tuple(TripLeg(f'internal-{i}', f'cohort-{i}', measure, measure,
                        'work', 'car', 'car', Amounts(1.25, 1), profile,
                        intrazonal=law) for i in range(args.legs))
    plan = compile_service_plan(city, legs, max_legs=args.legs)
    model = JointReleaseRuntime(city, legs, plan, max_legs=args.legs)
    state = model.advance(model.initial(), 2)
    assert len(state.internal) == args.legs
    old_times, new_times = [], []
    for _ in range(args.repetitions):
        start = time.perf_counter()
        old_check(model, state)
        old_times.append(time.perf_counter() - start)
        start = time.perf_counter()
        model.check(state)
        new_times.append(time.perf_counter() - start)

    new_final = model.advance(state, 6)
    model.check = MethodType(old_check, model)
    old_final = model.advance(state, 6)
    assert old_final == new_final
    with tempfile.TemporaryDirectory() as temporary:
        old_path, new_path = Path(temporary) / 'old.json', Path(temporary) / 'new.json'
        model.save(old_path, old_final)
        model.check = MethodType(JointReleaseRuntime.check, model)
        model.save(new_path, new_final)
        assert old_path.read_bytes() == new_path.read_bytes()
        assert model.load(new_path) == old_final

    # Preserve total active mass while assigning it to the wrong leg.
    invalid = replace(state, internal=(replace(state.internal[0], tag=legs[1].id),)
                      + state.internal[1:])
    rejected = []
    for check in (old_check, JointReleaseRuntime.check):
        try:
            check(model, invalid)
        except ValueError as exc:
            rejected.append(str(exc))
        else:
            raise AssertionError('mass-preserving tag corruption accepted')
    assert rejected[0] == rejected[1]
    result = dict(
        scope='finite internal-journey checkpoint cost; no full-city/RSS/24h claim',
        python=platform.python_version(), platform=platform.platform(),
        base_commit=BASE, original_source_sha256=hashlib.sha256(reference).hexdigest(),
        new_source_sha256=hashlib.sha256((ROOT / SOURCE).read_bytes()).hexdigest(),
        legs=args.legs, active_stage_records=len(state.internal),
        repetitions=args.repetitions, old_check_s=old_times, new_check_s=new_times,
        old_mean_s=statistics.mean(old_times), new_mean_s=statistics.mean(new_times),
        exact_four_tick_state_equality=True, checkpoint_bytes_equal=True,
        resumed_state_equal=True, mass_preserving_corruption_rejected=rejected,
        progress='19/21 (90.5%)', full_city='NOT_RUN')
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
