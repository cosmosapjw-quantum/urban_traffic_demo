"""Sequential city runs for the release timing comparison (pre-registered in LAUNCH.json).

One run at a time; before each run wait until MemAvailable >= 6 GiB (poll 30 s),
never touching other processes. Appends one record per run to RUNS_LOG.json.

usage: run_sequence.py STAGE [STAGE ...]
  legs      compile the Valley legs table (separate process) for the decomposition
  bitid     legacy bit-identity prefix: probe_v1_event_store.py valley_weekday_s7 25900 1
  legacy_dt10 interval_dt10 legacy_dt5 interval_dt5   city comparison runs (horizon 26,000 s)
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PY = '/home/cosmosapjw/urban_traffic_rust_20261116/.venv/bin/python'
LEGS = 'artifacts/v1_release_timing_20261117/valley_legs.npz'
NEED = 6 * 1024**3
HORIZON = '26000'
RUNS = {
    'legacy_dt10': ('legacy', '10'),
    'interval_dt10': ('release_interval_v1', '10'),
    'legacy_dt5': ('legacy', '5'),
    'interval_dt5': ('release_interval_v1', '5'),
}


def available():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) * 1024
    return 0


def command(stage):
    if stage == 'legs':
        return [PY, 'tools/probe_v1_refinement.py', 'legs', 'valley_weekday_s7', LEGS]
    if stage == 'bitid':
        return [PY, 'tools/probe_v1_event_store.py', 'valley_weekday_s7', '25900', '1',
                'artifacts/v1_release_timing_20261117/bitid/legacy_h1_25900']
    timing, step = RUNS[stage]
    return [PY, 'tools/probe_v1_refinement.py', 'run', 'valley_weekday_s7', HORIZON, '1', step,
            f'artifacts/v1_release_timing_20261117/runs/{stage}', LEGS, timing]


def main(stages):
    log_path = OUT / 'RUNS_LOG.json'
    log = json.loads(log_path.read_text()) if log_path.exists() else []
    for stage in stages:
        cmd = command(stage)
        waited = 0.0
        while available() < NEED:
            time.sleep(30)
            waited += 30
        record = dict(label=stage, command=['PYTHONPATH=native_binding:src'] + cmd,
                      mem_available_at_start_bytes=available(), waited_for_memory_s=waited,
                      started_utc=datetime.now(timezone.utc).isoformat())
        (OUT / 'runs').mkdir(exist_ok=True)
        (OUT / 'bitid').mkdir(exist_ok=True)
        env = dict(os.environ, PYTHONPATH='native_binding:src', OMP_NUM_THREADS='1',
                   OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
        env.pop('METROFLOW_V1_RELEASE_TIMING', None)
        t0 = time.perf_counter()
        with open(OUT / f'{stage}.log', 'w') as out:
            done = subprocess.run(cmd, cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT)
        record.update(exit_code=done.returncode, wall_s=time.perf_counter() - t0,
                      finished_utc=datetime.now(timezone.utc).isoformat())
        log.append(record)
        log_path.write_text(json.dumps(log, indent=1) + '\n')
        print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main(sys.argv[1:])
