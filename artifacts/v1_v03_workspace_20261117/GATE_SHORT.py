"""Short reproduction gate for a frozen candidate (not a campaign receipt).

Runs one case from t=0 to HORIZON in the worker's hourly native calls under the
8 GiB address-space limit and records, per call, each storage guard's peak
required/allowance ratio (METROFLOW_BUDGET_TRACE=record never changes a guard).

usage: GATE_SHORT.py CASE HORIZON_S OUT.json
"""
import json, math, os, resource, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
os.environ.update(METROFLOW_V1_ENGINE_BACKEND='rust_whole', METROFLOW_V1_ROUTING_BACKEND='rust',
    METROFLOW_V1_NATIVE_THREADS='1', METROFLOW_V1_STORAGE_POLICY='bounded_bytes_v1')
os.environ.setdefault('METROFLOW_BUDGET_TRACE', 'record')
if os.environ.get('GATE_DIAG_SITE'):
    sys.path.insert(0, os.environ['GATE_DIAG_SITE'])
from tools.run_v1_local_acceptance import (atomic_json, candidate_provenance, file_sha256,
    observed_environment, peak_rss_bytes, prepare, resource_limit_kind)
from metroflow.v1.native_engine import native_binary_provenance
from metroflow.active_suffix.common import BudgetExceeded
import _metroflow_rust as native

case_id, horizon, out = sys.argv[1], float(sys.argv[2]), Path(sys.argv[3])
matrix_path = ROOT / 'scenarios/v1/release_matrix.json'
matrix = json.loads(matrix_path.read_text())
case = next(c for c in matrix['cases'] if c['id'] == case_id)
limit = matrix['limits']['peak_rss_bytes']
resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
started = time.perf_counter()
result = dict(status='RUNNING', scope='SHORT_GATE_NOT_CAMPAIGN', case=case_id, horizon_s=horizon,
    candidate=candidate_provenance(), native_binary=native_binary_provenance(),
    matrix_sha256=file_sha256(matrix_path), environment=observed_environment(), calls=[])
driver, _ = prepare(case, matrix, 10.0)
result['driver_identity'] = driver.identity
result['native_storage'] = driver.runtime.storage_config()
result['construct_wall_s'] = time.perf_counter() - started
result['construct_trace'] = native.budget_trace_snapshot(True)
state = driver.initial()
def summary(tr):
    return {k: dict(ratio=v['max_ratio'], required=v['max_required'], limit=v['limit_at_max'],
                    exceeded=v['exceeded'], terms=v['terms_at_max'])
            for k, v in tr['sites'].items() if k.split(':')[0] != 'phase_allowance'}
try:
    while state.time_s < horizon:
        target = min(horizon, (math.floor(state.time_s / 3600) + 1) * 3600)
        t0 = time.perf_counter()
        state = driver.advance(state, target)
        raw = native.budget_trace_snapshot(True)
        tr = summary(raw)
        worst = max(tr.items(), key=lambda kv: kv[1]['ratio'])
        result['calls'].append(dict(end_s=state.time_s, wall_s=time.perf_counter() - t0,
            peak_rss_bytes=peak_rss_bytes(), counted_heap_live=raw.get('live_bytes'),
            counted_heap_peak=raw.get('peak_bytes'), worst_site=worst[0], worst_ratio=worst[1]['ratio'], sites=tr))
        print(json.dumps(dict(t=state.time_s, wall=round(time.perf_counter()-started, 1),
            rss=peak_rss_bytes(), heap_peak=raw.get('peak_bytes'), worst=worst[0], ratio=round(worst[1]['ratio'], 4))), flush=True)
    result['status'] = 'GATE_REACHED_HORIZON'
except (BudgetExceeded, ArithmeticError, ValueError, RuntimeError, MemoryError) as e:
    cp = getattr(e, 'checkpoint', None)
    if cp is not None:
        state = cp
    result.update(status='GATE_BLOCKED', reason=str(e)[:600], error_type=type(e).__name__,
        resource_limit_kind=resource_limit_kind(str(e), result['native_storage']),
        failing_call_trace=summary(native.budget_trace_snapshot(True)))
result.update(simulated_s=state.time_s, wall_s=time.perf_counter() - started,
    peak_rss_bytes=peak_rss_bytes(), report=driver.report(state),
    script_sha256=file_sha256(Path(__file__)))
atomic_json(out, result)
print(json.dumps({k: result[k] for k in ('status', 'case', 'simulated_s', 'wall_s', 'peak_rss_bytes')}))
