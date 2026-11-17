"""Assemble RECEIPT.json from the run log, run JSONs, test logs and comparison.

usage: receipt.py  ->  writes RECEIPT.json next to this file
"""
import hashlib
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        for block in iter(lambda: source.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def tests():
    out = {}
    for name in ('tests_rust.log', 'tests_python_regression.log', 'tests_release_timing.log',
                 'tests_related.log', 'red_legacy_counterexample.log'):
        path = HERE / name
        if not path.exists():
            out[name] = 'NOT_RUN'
            continue
        text = path.read_text()
        out[name] = dict(sha256=sha(path), summary=[line for line in text.splitlines()
                                                    if re.search(r'test result|passed|failed|xfailed|error', line)][-4:])
    return out


def main():
    log = json.loads((HERE / 'RUNS_LOG.json').read_text())
    runs = {}
    for record in log:
        label = record['label']
        path = (HERE / 'bitid/legacy_h1_25900.json') if label == 'bitid' else HERE / 'runs' / f'{label}.json'
        entry = dict(command=record['command'], exit_code=record['exit_code'], wall_s=record['wall_s'],
                     started_utc=record['started_utc'], finished_utc=record['finished_utc'],
                     mem_available_at_start_bytes=record['mem_available_at_start_bytes'],
                     waited_for_memory_s=record['waited_for_memory_s'])
        if path.exists():
            data = json.loads(path.read_text())
            entry.update(json_path=str(path.relative_to(ROOT)), json_sha256=sha(path), status=data['status'],
                         simulated_s=data['simulated_s'], peak_rss_bytes=data['peak_rss_bytes'],
                         checkpoint_local_only=data['checkpoint'],
                         native_binary=data['native_binary'], candidate_source_sha256=data['candidate'].get('source_sha256'),
                         driver_identity=data.get('driver_identity'))
        runs[label] = entry
    comparison = json.loads((HERE / 'COMPARISON.json').read_text())
    binary = ROOT / 'native_binding/_metroflow_rust.so'
    receipt = dict(
        schema='metroflow.v1.release_timing.receipt/1',
        branch=git('rev-parse', '--abbrev-ref', 'HEAD'),
        head_commit_at_receipt=git('rev-parse', 'HEAD'),
        base_commit='274a4ffa347e85b1203a57f4a500b61eec7ca4b3',
        launch_commit='4669f72',
        source_files={p: sha(ROOT / p) for p in (
            'crates/metroflow-rust/src/v1_journey.rs', 'crates/metroflow-rust/src/v1_road.rs',
            'crates/metroflow-rust/src/v1_engine.rs', 'src/metroflow/packet_network.py',
            'src/metroflow/v1/joint_release_runtime.py', 'src/metroflow/v1/native_journey.py',
            'src/metroflow/v1/native_road.py', 'src/metroflow/v1/native_engine.py',
            'src/metroflow/v1/native_release_driver.py', 'tools/run_v1_local_acceptance.py',
            'tools/probe_v1_refinement.py', 'tools/probe_v1_event_store.py',
            'tests/v1/test_release_timing.py')},
        native_binary=dict(path='native_binding/_metroflow_rust.so (local only, not committed)',
                           sha256=sha(binary), size_bytes=binary.stat().st_size,
                           build='PYO3_PYTHON=$TASK_PY cargo build --release --offline; cp target/release/lib_metroflow_rust.so native_binding/_metroflow_rust.so'),
        legs_npz=dict(path='artifacts/v1_release_timing_20261117/valley_legs.npz (local only)',
                      sha256=sha(HERE / 'valley_legs.npz'),
                      note='identical sha256 to the npz of artifacts/v1_refinement_20261117 runs'),
        runs=runs,
        tests=tests(),
        test_commands=dict(
            rust='cd crates/metroflow-rust && LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu RUSTFLAGS="-L /usr/lib/x86_64-linux-gnu -l python3.12" PYO3_PYTHON=$TASK_PY CARGO_TARGET_DIR=$PWD/../../target_test cargo test --release --offline',
            python_regression='PYTHONPATH=native_binding:src:tests/v1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 OMP_NUM_THREADS=1 $TASK_PY -m pytest -q -p no:randomly tests/test_entry_projection.py tests/v1/test_entry_projection_native.py tests/v1/test_native*.py tests/test_packet_quotient.py tests/v1/test_transfer_time.py tests/test_v1_journey.py tests/test_v1_birth_contract.py tests/v1/test_local_campaign_cli.py tests/test_v1_plan.py tests/v1/test_v03_counterexamples.py tests/v1/test_mark_block_native.py',
            release_timing='PYTHONPATH=native_binding:src:tests/v1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 OMP_NUM_THREADS=1 $TASK_PY -m pytest -v -p no:randomly tests/v1/test_release_timing.py',
            related='PYTHONPATH=native_binding:src:tests/v1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 OMP_NUM_THREADS=1 $TASK_PY -m pytest -q -p no:randomly tests/v1/test_joint_release_runtime.py tests/v1/test_service_boundary_offers.py tests/v1/test_bus_freight.py tests/v1/test_release_runtime.py tests/v1/test_runtime_resume.py tests/v1/test_release_driver.py',
            baseline='python_regression baseline at 274a4ff: 356 passed, 5 xfailed (coordinator); Rust baseline 76 tests (84 - 8 new)',
            tdd_note='the Rust policy was drafted before its tests; the behavioral counterexample is recorded in red_legacy_counterexample.log (policy assertions applied to legacy timing fail with the one-step lag)'),
        post_hoc_not_decisional=dict(
            lag_order=json.loads((HERE / 'LAG_ORDER.json').read_text())['rows'],
            idle_overhead=json.loads((HERE / 'IDLE_OVERHEAD.json').read_text())['summary']),
        verdict=comparison['verdict'],
        not_run=[
            'ReleaseRuntime / ReleaseDriver (python_oracle and legacy rust campaign backends): policy not implemented; the CLI rejects it there',
            'mark_block_scaled_v1 together with release_interval_v1 (plumbed, not exercised in the city comparison)',
            'River and Coastal cases, horizons beyond 26,000 s, 24 h campaign, repeated runs, dt < 5 s, h != 1 s',
            'road class-resolved birth/exit moments (not exposed by the native API)',
        ],
        scope='diagnostic research unit; V03 BLOCKED, 19/21 and 5/21 unchanged; no PR, merge or push',
    )
    (HERE / 'RECEIPT.json').write_text(json.dumps(receipt, indent=1) + '\n')
    print(json.dumps(receipt['verdict'], indent=1))


if __name__ == '__main__':
    main()
