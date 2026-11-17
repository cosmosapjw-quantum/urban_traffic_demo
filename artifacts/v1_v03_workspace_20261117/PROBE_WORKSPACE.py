"""Diagnostic only: load one blocked campaign checkpoint with its own binding and
advance a few ticks under a budget_trace build, recording each guard's terms and
the counted live Rust heap. Never a campaign candidate; observe mode continues
past an exceeded guard solely to measure the allocation that would follow.

usage: PROBE_WORKSPACE.py RECEIPT.json OUT.json DIAG_SITE TICKS
"""
import json, os, resource, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
receipt_path, output, diag_site, ticks = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], int(sys.argv[4])
sys.path[:0] = [diag_site, str(ROOT), str(ROOT / 'src')]
os.environ.update(METROFLOW_V1_ENGINE_BACKEND='rust_whole', METROFLOW_V1_ROUTING_BACKEND='rust',
    METROFLOW_V1_NATIVE_THREADS='1', METROFLOW_V1_STORAGE_POLICY='bounded_bytes_v1')
os.environ.setdefault('METROFLOW_BUDGET_TRACE', 'observe')
from tools.run_v1_local_acceptance import atomic_json, file_sha256, peak_rss_bytes, prepare, candidate_provenance
from metroflow.v1.native_engine import native_binary_provenance
from metroflow.active_suffix.common import BudgetExceeded
import _metroflow_rust as native

source = json.loads(receipt_path.read_text())
matrix_path = ROOT / 'scenarios/v1/release_matrix.json'
assert file_sha256(matrix_path) == source['matrix_sha256']
matrix = json.loads(matrix_path.read_text())
case = next(c for c in matrix['cases'] if c['id'] == source['case'])
limit = matrix['limits']['peak_rss_bytes']
resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
binary = native_binary_provenance()
assert binary['sha256'] != source['native_binary_sha256'], 'expected diagnostic build'
started = time.perf_counter()
driver, _ = prepare(case, matrix, source['step_s'])
assert driver.identity == source['driver_identity'], 'binding differs; refuse'
construct = native.budget_trace_snapshot(True)
path = receipt_path.parent / source['last_valid']['path']
state = driver.load(path)
assert state.time_s == source['simulated_s']
loaded_report_identical = driver.report(state) == source['last_valid_report']
load = native.budget_trace_snapshot(True)
debug_loaded = driver.debug_state(state)
result = dict(status='DIAGNOSTIC_ONLY', case=source['case'], diagnostic_binary=binary,
    frozen_binary_sha256=source['native_binary_sha256'], candidate=candidate_provenance(),
    input_checkpoint_sha256=file_sha256(path), start_s=state.time_s,
    loaded_report_identical=loaded_report_identical, source_blocker=source.get('reason'),
    construct_trace=construct, load_trace=load, debug_loaded=debug_loaded,
    receipt_last_native_metrics=source.get('last_native_metrics'), ticks=[])
for k in range(ticks):
    t0 = time.perf_counter()
    try:
        state = driver.advance(state, state.time_s + source['step_s'])
        status = 'ADVANCED'
    except (BudgetExceeded, ArithmeticError, ValueError, RuntimeError, MemoryError) as e:
        status = type(e).__name__ + ': ' + str(e)[:400]
    tr = native.budget_trace_snapshot(True)
    result['ticks'].append(dict(status=status, time_s=state.time_s, wall_s=time.perf_counter()-t0,
        peak_rss_bytes=peak_rss_bytes(), trace=tr))
    print(json.dumps(dict(k=k, status=status[:120], t=state.time_s, live=tr.get('live_bytes'),
        peak=tr.get('peak_bytes'), exceeded={s: v['exceeded'] for s, v in tr['sites'].items() if v['exceeded']})), flush=True)
    if status != 'ADVANCED':
        break
result.update(debug_final=driver.debug_state(state), wall_s=time.perf_counter()-started,
    peak_rss_bytes=peak_rss_bytes(), script_sha256=file_sha256(Path(__file__)))
atomic_json(output, result)
