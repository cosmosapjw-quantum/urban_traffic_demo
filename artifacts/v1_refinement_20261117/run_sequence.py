"""Sequential launcher for the fixed refinement design (one simulation at a time).

Design fixed before any run: Valley valley_weekday_s7, t=0..25500 s, full calendar,
1 native thread, bounded_bytes_v1.
  A: dt=10 s, h in {0, 1, 0.5, 0.25} s
  B: h=1 s, dt in {10, 5} s (dt=10 run shared with A)
Before each run, waits until MemAvailable >= 6 GiB. Never kills other processes.
"""
import json, os, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts/v1_refinement_20261117'
PY = '/home/cosmosapjw/urban_traffic_rust_20261116/.venv/bin/python'
CASE, HORIZON = 'valley_weekday_s7', '25500'
RUNS = [('h0_dt10', '0', '10'), ('h1_dt10', '1', '10'), ('h0p5_dt10', '0.5', '10'),
        ('h0p25_dt10', '0.25', '10'), ('h1_dt5', '1', '5')]


def available_bytes():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) * 1024
    return 0


log_path = OUT / 'LAUNCH.json'
log = json.loads(log_path.read_text()) if log_path.exists() else []
done = {r['label'] for r in log if r.get('exit_code') == 0}
only = set(sys.argv[1:])
for label, h, dt in RUNS:
    if label in done or (only and label not in only):
        continue
    waited = 0.0
    while available_bytes() < 6 * 1024**3:
        time.sleep(60); waited += 60
    cmd = [PY, 'tools/probe_v1_refinement.py', 'run', CASE, HORIZON, h, dt,
           f'artifacts/v1_refinement_20261117/runs/valley_{label}', 'artifacts/v1_refinement_20261117/valley_legs.npz']
    entry = dict(label=label, width_s=float(h), step_s=float(dt), command=['PYTHONPATH=native_binding:src'] + cmd,
                 mem_available_at_start_bytes=available_bytes(), waited_for_memory_s=waited,
                 started_utc=datetime.now(timezone.utc).isoformat())
    t0 = time.perf_counter()
    with open(OUT / 'runs' / f'valley_{label}.log', 'w') as f:
        rc = subprocess.call(cmd, cwd=ROOT, env={**{k: v for k, v in os.environ.items() if not k.startswith('METROFLOW')}, 'PYTHONPATH': 'native_binding:src'},
                             stdout=f, stderr=subprocess.STDOUT)
    entry.update(exit_code=rc, wall_s=time.perf_counter() - t0, finished_utc=datetime.now(timezone.utc).isoformat())
    log.append(entry)
    log_path.write_text(json.dumps(log, indent=1))
    print(json.dumps(entry), flush=True)
