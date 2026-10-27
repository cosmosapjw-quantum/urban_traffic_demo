"""Measured P01 comparison in separate processes (no performance projection)."""
import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def run(src, scenario):
    env = dict(os.environ, PYTHONPATH=str(src))
    start = time.perf_counter()
    proc = subprocess.run([sys.executable, '-m', 'metroflow.v1', 'run',
                           '--scenario', scenario, '--days', '1'],
                          cwd='/tmp', env=env, capture_output=True, text=True, timeout=180)
    elapsed = time.perf_counter() - start
    if proc.returncode:
        raise RuntimeError(f'profile child failed {proc.returncode}: {proc.stderr}')
    result = json.loads(proc.stdout)
    if result['status'] != 'PASS':
        raise RuntimeError('profile scenario did not complete')
    row = result['cases'][0]
    return dict(wall_s=elapsed, inner_wall_s=row['wall_s'], peak_rss_kib=row['peak_rss_kib']), row


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--scenario', default='city10k_weekday')
    p.add_argument('--baseline-src', type=Path)
    p.add_argument('--runs', type=int, default=3)
    p.add_argument('--out', type=Path)
    args = p.parse_args()
    if args.runs < 1:
        p.error('runs must be positive')
    samples, baseline_rows, optimized_rows = [], [], []
    # Alternating order reduces but does not remove contention and host drift.
    for i in range(args.runs):
        order = [('optimized', ROOT / 'src')]
        if args.baseline_src is not None:
            order.insert(0, ('baseline', args.baseline_src))
        if i % 2:
            order.reverse()
        for name, src in order:
            metrics, row = run(src, args.scenario)
            samples.append(dict(run=i + 1, version=name, **metrics))
            (baseline_rows if name == 'baseline' else optimized_rows).append(row)
    ignored = {'wall_s', 'peak_rss_kib'}
    def normalized(row):
        return {k:v for k,v in row.items() if k not in ignored}
    identical = (all(normalized(x) == normalized(baseline_rows[0]) for x in baseline_rows + optimized_rows)
                 if baseline_rows else None)
    stats = {}
    for name in (('baseline', 'optimized') if baseline_rows else ('optimized',)):
        values = [s['wall_s'] for s in samples if s['version'] == name]
        stats[name] = dict(mean_wall_s=statistics.mean(values),
                           min_wall_s=min(values), max_wall_s=max(values),
                           stdev_wall_s=statistics.stdev(values) if len(values)>1 else 0,
                           max_rss_kib=max(s['peak_rss_kib'] for s in samples if s['version']==name))
    payload = dict(status=('PROFILE_ONLY' if identical is None else 'PASS' if identical else 'NOT_ACCEPTED'), scenario=args.scenario,
                   python=platform.python_version(), identical_all_report_fields_except_resources=identical,
                   paired_samples=samples, stats=stats,
                   scope='same synthetic 10k city and fixed calendar; no 100k performance claim')
    text = json.dumps(payload, indent=2, allow_nan=False)+'\n'
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(text)
    print(text,end='')
    return 0 if identical is not False else 2


if __name__ == '__main__':
    raise SystemExit(main())
