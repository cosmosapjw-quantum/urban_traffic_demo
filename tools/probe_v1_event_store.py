"""Bounded same-input prefix for comparing two native builds (diagnostic).

Runs one release case from t=0 to HORIZON in the worker's hourly native calls
under the 8 GiB address-space limit, saves the end checkpoint, and records the
report, wall, RSS and the guard/allocation trace in record mode (which never
changes a guard decision). The native build is chosen by PYTHONPATH.

usage: probe_v1_event_store.py CASE HORIZON_S WIDTH_S OUT_PREFIX
"""
import json, math, os, resource, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
case_id, horizon, width, prefix = sys.argv[1], float(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
os.environ.update(METROFLOW_V1_ENGINE_BACKEND='rust_whole', METROFLOW_V1_ROUTING_BACKEND='rust',
    METROFLOW_V1_NATIVE_THREADS='1', METROFLOW_V1_STORAGE_POLICY='bounded_bytes_v1',
    METROFLOW_V1_ENTRY_PROJECTION_WIDTH_S=width, METROFLOW_BUDGET_TRACE='record',
    METROFLOW_V1_ROAD_REPRESENTATION=os.environ.get('METROFLOW_V1_ROAD_REPRESENTATION', 'rows'))
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from tools.run_v1_local_acceptance import (atomic_json, candidate_provenance, file_sha256,
    observed_environment, peak_rss_bytes, prepare, resource_limit_kind)
from metroflow.v1.native_engine import native_binary_provenance
from metroflow.active_suffix.common import BudgetExceeded
import _metroflow_rust as native

matrix = json.loads((ROOT / 'scenarios/v1/release_matrix.json').read_text())
case = next(c for c in matrix['cases'] if c['id'] == case_id)
limit = matrix['limits']['peak_rss_bytes']
resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
prefix.parent.mkdir(parents=True, exist_ok=True)
t0 = time.perf_counter()
result = dict(status='RUNNING', scope='DIAGNOSTIC_PREFIX_NOT_CAMPAIGN', case=case_id, horizon_s=horizon,
    entry_projection_width_s=float(width), candidate=candidate_provenance(),
    native_binary=native_binary_provenance(), environment=observed_environment(), calls=[])
driver, _ = prepare(case, matrix, 10.0)
result.update(driver_identity=driver.identity, native_storage=driver.runtime.storage_config(),
              construct_wall_s=time.perf_counter() - t0)
native.budget_trace_snapshot(True)
state = driver.initial()
def keep(tr):
    sites = {k: dict(ratio=v['max_ratio'], required=v['max_required'], limit=v['limit_at_max'], terms=v['terms_at_max'])
             for k, v in tr['sites'].items()
             if k.split(':')[0] in ('road_work', 'road_actual', 'service_sinks', 'journey_commit', 'engine_admission')}
    return dict(sites=sites, counters=tr.get('counters', {}))
try:
    while state.time_s < horizon:
        target = min(horizon, (math.floor(state.time_s / 3600) + 1) * 3600)
        c0 = time.perf_counter()
        state = driver.advance(state, target)
        tr = keep(native.budget_trace_snapshot(True))
        result['calls'].append(dict(end_s=state.time_s, wall_s=time.perf_counter() - c0,
                                    peak_rss_bytes=peak_rss_bytes(), **tr))
        print(json.dumps(dict(t=state.time_s, wall=round(time.perf_counter() - t0, 1), rss=peak_rss_bytes())), flush=True)
    result['status'] = 'REACHED_HORIZON'
except (BudgetExceeded, ArithmeticError, ValueError, RuntimeError, MemoryError) as e:
    cp = getattr(e, 'checkpoint', None)
    if cp is not None:
        state = cp
    result.update(status='BLOCKED', reason=str(e)[:600],
                  resource_limit_kind=resource_limit_kind(str(e), result['native_storage']),
                  failing_call=keep(native.budget_trace_snapshot(True)))
checkpoint = prefix.with_suffix('.last_valid.bin')
driver.save(checkpoint, state)
result.update(simulated_s=state.time_s, wall_s=time.perf_counter() - t0, peak_rss_bytes=peak_rss_bytes(),
              report=driver.report(state), debug=driver.debug_state(state),
              checkpoint=dict(path=str(checkpoint), bytes=checkpoint.stat().st_size, sha256=file_sha256(checkpoint)),
              script_sha256=file_sha256(Path(__file__)))
atomic_json(prefix.with_suffix('.json'), result)
print(json.dumps({k: result[k] for k in ('status', 'simulated_s', 'wall_s', 'peak_rss_bytes')}))
