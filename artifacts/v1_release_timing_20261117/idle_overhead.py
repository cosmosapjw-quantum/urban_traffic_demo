"""POST HOC diagnostic (not part of the pre-registered adoption rule).

Isolates the computational overhead of the release timing code from its
physical effect: from t=0 to 3,600 s the Valley calendar has no departures, so
both timings hold identical (empty) physical states and execute the same road
and service work; only the journey preparation code differs. Runs alternate in
ABBA order in separate processes to reduce drift on the shared host.

usage: idle_overhead.py worker TIMING  |  idle_overhead.py  -> IDLE_OVERHEAD.json
"""
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PY = '/home/cosmosapjw/urban_traffic_rust_20261116/.venv/bin/python'
ORDER = ('legacy', 'release_interval_v1', 'release_interval_v1', 'legacy',
         'legacy', 'release_interval_v1', 'release_interval_v1', 'legacy')


def cpu():
    u = resource.getrusage(resource.RUSAGE_SELF)
    return u.ru_utime + u.ru_stime


def worker(timing):
    os.environ.update(METROFLOW_V1_ENGINE_BACKEND='rust_whole', METROFLOW_V1_ROUTING_BACKEND='rust',
                      METROFLOW_V1_NATIVE_THREADS='1', METROFLOW_V1_STORAGE_POLICY='bounded_bytes_v1',
                      METROFLOW_V1_ENTRY_PROJECTION_WIDTH_S='1', METROFLOW_V1_RELEASE_TIMING=timing)
    sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
    from tools.run_v1_local_acceptance import prepare
    matrix = json.loads((ROOT / 'scenarios/v1/release_matrix.json').read_text())
    case = next(c for c in matrix['cases'] if c['id'] == 'valley_weekday_s7')
    driver, _ = prepare(case, matrix, 10.0)
    state = driver.initial()
    c0, w0 = cpu(), time.perf_counter()
    state = driver.advance(state, 3600.0)
    out = dict(timing=timing, cpu_s=cpu() - c0, wall_s=time.perf_counter() - w0,
               phase=driver.runtime.phase_metrics()['phase_wall_s'],
               ledger=driver.report(state)['execution']['ledger'])
    print(json.dumps(out))


def main():
    rows = []
    for timing in ORDER:
        load = os.getloadavg()
        done = subprocess.run([PY, str(Path(__file__).resolve()), 'worker', timing], cwd=ROOT,
                              env=dict(os.environ, PYTHONPATH='native_binding:src', OMP_NUM_THREADS='1'),
                              capture_output=True, text=True)
        row = json.loads(done.stdout.strip().splitlines()[-1])
        row['loadavg_before'] = load
        rows.append(row)
        print(json.dumps({k: row[k] for k in ('timing', 'cpu_s', 'wall_s')}), flush=True)
    summary = {}
    for timing in ('legacy', 'release_interval_v1'):
        values = [r for r in rows if r['timing'] == timing]
        summary[timing] = dict(cpu_s=[r['cpu_s'] for r in values],
                               journey_prepare_s=[r['phase']['journey_prepare'] for r in values],
                               mean_cpu_s=sum(r['cpu_s'] for r in values) / len(values),
                               mean_journey_prepare_s=sum(r['phase']['journey_prepare'] for r in values) / len(values))
    summary['ratio_mean_cpu'] = summary['release_interval_v1']['mean_cpu_s'] / summary['legacy']['mean_cpu_s']
    summary['ratio_mean_journey_prepare'] = (summary['release_interval_v1']['mean_journey_prepare_s']
                                             / summary['legacy']['mean_journey_prepare_s'])
    out = dict(scope='POST HOC; idle 0-3600 s Valley, dt=10, h=1; identical empty physical states; '
                     'not used by the pre-registered rule', order=ORDER, rows=rows, summary=summary)
    (HERE / 'IDLE_OVERHEAD.json').write_text(json.dumps(out, indent=1) + '\n')
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == 'worker':
        worker(sys.argv[2])
    else:
        main()
