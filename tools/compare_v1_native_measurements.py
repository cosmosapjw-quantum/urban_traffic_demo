"""Compare matched diagnostic reports and complete serialized checkpoints."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def compare_directory(directory):
    p = directory/'matched-prefix-python_oracle.json'
    q = directory/'matched-prefix-rust.json'
    x, y = json.loads(p.read_text()), json.loads(q.read_text())
    for key in ('city_identity', 'schedule_identity', 'source_archive_sha256',
                'activated_legs', 'unactivated_legs', 'step_s', 'horizon_s',
                'start_s', 'record_budget'):
        assert x[key] == y[key], key
    assert x['status'] == y['status'] == 'PASS_SCOPED'
    counts = dict(numeric_leaves=0, exact_other_leaves=0,
                  max_absolute_delta=0., max_relative_delta=0.)
    failures = []

    def compare(a, b, path):
        if (isinstance(a, (float, int)) and not isinstance(a, bool)
                and isinstance(b, (float, int)) and not isinstance(b, bool)):
            counts['numeric_leaves'] += 1
            delta = abs(a-b)
            counts['max_absolute_delta'] = max(counts['max_absolute_delta'], delta)
            counts['max_relative_delta'] = max(counts['max_relative_delta'],
                                                delta/max(1., abs(a), abs(b)))
            if not math.isclose(a, b, rel_tol=2e-10, abs_tol=2e-9):
                failures.append(path)
        elif isinstance(a, dict) and isinstance(b, dict):
            if a.keys() != b.keys():
                failures.append(path+'.keys')
                return
            for key in a:
                compare(a[key], b[key], path+'.'+key)
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                failures.append(path+'.length')
                return
            for i, (l, r) in enumerate(zip(a, b)):
                compare(l, r, path+f'[{i}]')
        else:
            counts['exact_other_leaves'] += 1
            if type(a) is not type(b) or a != b:
                failures.append(path)

    compare(x['report'], y['report'], 'report')
    pc, qc = p.with_suffix('.checkpoint.json'), q.with_suffix('.checkpoint.json')
    compare(json.loads(pc.read_text()), json.loads(qc.read_text()), 'checkpoint')
    cold = directory/'final-prefix-rust.checkpoint.json'
    return dict(status='PASS_SCOPED' if not failures else 'FAILED',
        scope='same actual-city 256-leg prefix, 06:00 invariant pre-source vacuum ->08:00; full report and every serialized checkpoint field',
        counts=counts, failures=failures[:20], relative_tolerance=2e-10, absolute_tolerance=2e-9,
        python_evolution_s=x['evolution_s'], rust_evolution_s=y['evolution_s'],
        speedup=x['evolution_s']/y['evolution_s'],
        oracle_checkpoint_sha256=hashlib.sha256(pc.read_bytes()).hexdigest(),
        native_checkpoint_sha256=hashlib.sha256(qc.read_bytes()).hexdigest(),
        native_zero_start_checkpoint_sha256=hashlib.sha256(cold.read_bytes()).hexdigest(),
        native_vacuum_warm_start_byte_identical=cold.read_bytes() == qc.read_bytes(),
        full_campaign='NOT_RUN')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    result = compare_directory(args.directory)
    (args.directory/'MATCHED_PARITY.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))
    raise SystemExit(0 if result['status'] == 'PASS_SCOPED' else 2)
