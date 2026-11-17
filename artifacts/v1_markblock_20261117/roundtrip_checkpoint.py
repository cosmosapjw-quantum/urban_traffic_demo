"""Load a mark-block Valley checkpoint into a fresh driver, save it again and
advance one 10 s step from both the original-run checkpoint and the reload.

usage: roundtrip_checkpoint.py CHECKPOINT OUT_JSON
"""
import json, os, resource, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
os.environ.update(METROFLOW_V1_ENGINE_BACKEND='rust_whole', METROFLOW_V1_ROUTING_BACKEND='rust',
    METROFLOW_V1_NATIVE_THREADS='1', METROFLOW_V1_STORAGE_POLICY='bounded_bytes_v1',
    METROFLOW_V1_ENTRY_PROJECTION_WIDTH_S='1', METROFLOW_V1_ROAD_REPRESENTATION='mark_block_scaled_v1')
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from tools.run_v1_local_acceptance import prepare, file_sha256, peak_rss_bytes
src, out = Path(sys.argv[1]), Path(sys.argv[2])
matrix = json.loads((ROOT / 'scenarios/v1/release_matrix.json').read_text())
case = next(c for c in matrix['cases'] if c['id'] == 'valley_weekday_s7')
limit = matrix['limits']['peak_rss_bytes']
resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
t0 = time.perf_counter()
driver, _ = prepare(case, matrix, 10.0)
t1 = time.perf_counter()
state = driver.load(src)
t2 = time.perf_counter()
again = out.with_suffix('.resaved.bin')
driver.save(again, state)
t3 = time.perf_counter()
same = file_sha256(src) == file_sha256(again)
try:
    nxt = driver.advance(state, state.time_s + 10.0)
    advance = dict(status='ADVANCED', time_s=nxt.time_s, ledger=driver.report(nxt)['execution']['ledger'])
except Exception as e:  # the blocked last-valid state is expected to refuse again
    advance = dict(status='REFUSED', error=type(e).__name__ + ': ' + str(e)[:400])
t4 = time.perf_counter()
res = dict(source=str(src), source_sha256=file_sha256(src), resaved_sha256=file_sha256(again),
           byte_identical_resave=same, time_s=state.time_s, next_step=advance,
           construct_s=t1 - t0, load_s=t2 - t1, save_s=t3 - t2, advance_s=t4 - t3,
           peak_rss_bytes=peak_rss_bytes(), report_at_load=driver.report(state)['execution']['ledger'])
again.unlink()
json.dump(res, open(out, 'w'), indent=1)
print(json.dumps({k: res[k] for k in ('byte_identical_resave', 'time_s', 'next_step', 'load_s', 'peak_rss_bytes')}))
