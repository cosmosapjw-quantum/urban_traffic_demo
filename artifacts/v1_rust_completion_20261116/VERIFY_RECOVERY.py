"""Fresh-load one actual failed campaign checkpoint under the same limits."""
import json
import os
from pathlib import Path
import resource
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from tools.run_v1_local_acceptance import (
    atomic_json, candidate_provenance, file_sha256, observed_environment,
    peak_rss_bytes, prepare,
)
from metroflow.v1.native_engine import native_binary_provenance
from metroflow.active_suffix.common import BudgetExceeded


def main():
    receipt_path = Path(sys.argv[1])
    output = Path(sys.argv[2])
    source = json.loads(receipt_path.read_text())
    matrix_path = ROOT / 'scenarios/v1/release_matrix.json'
    assert file_sha256(matrix_path) == source['matrix_sha256']
    matrix = json.loads(matrix_path.read_text())
    case = next(c for c in matrix['cases'] if c['id'] == source['case'])
    limit = matrix['limits']['peak_rss_bytes']
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    os.environ.update(METROFLOW_V1_ENGINE_BACKEND='rust_whole',
        METROFLOW_V1_ROUTING_BACKEND='rust', METROFLOW_V1_NATIVE_THREADS='1',
        METROFLOW_V1_STORAGE_POLICY='bounded_bytes_v1')
    started = time.perf_counter()
    candidate = candidate_provenance()
    binary = native_binary_provenance()
    assert candidate['source_sha256'] == source['candidate_source_sha256']
    assert binary['sha256'] == source['native_binary_sha256']
    driver, _ = prepare(case, matrix, source['step_s'])
    assert driver.identity == source['driver_identity']
    path = receipt_path.parent / source['last_valid']['path']
    state = driver.load(path)
    assert state.time_s == source['simulated_s']
    assert driver.report(state) == source['last_valid_report']
    # Serialize the reloaded state before advancing; capacity differences may
    # change the later resource failure clock without changing physical rows.
    roundtrip = output.with_suffix('.roundtrip.bin')
    driver.save(roundtrip, state)
    assert file_sha256(path) == file_sha256(roundtrip)
    result = dict(status='FRESH_LOAD_AND_ROUNDTRIP_VERIFIED', case=source['case'],
        candidate=candidate, native_binary=binary, environment=observed_environment(),
        source_receipt_sha256=file_sha256(receipt_path),
        script_sha256=file_sha256(Path(__file__)),
        input_checkpoint_sha256=file_sha256(path),
        roundtrip_checkpoint_sha256=file_sha256(roundtrip),
        start_s=state.time_s, loaded_report_identical=True,
        full_day_acceptance='NOT_ESTABLISHED', address_space_limit_bytes=limit)
    try:
        state = driver.advance(state, state.time_s + source['step_s'])
        result['continuation_status'] = 'ADVANCED_ONE_TICK'
    except (BudgetExceeded, ArithmeticError, ValueError, RuntimeError) as error:
        if not hasattr(error, 'checkpoint'):
            raise
        state = error.checkpoint
        result.update(continuation_status=type(error).__name__, reason=str(error))
    result.update(simulated_s=state.time_s, report=driver.report(state),
        debug=driver.debug_state(state), wall_s=time.perf_counter()-started,
        peak_rss_bytes=peak_rss_bytes())
    atomic_json(output, result)
    print(json.dumps({k: result[k] for k in ('status', 'case',
        'continuation_status', 'simulated_s', 'wall_s', 'peak_rss_bytes')}))


if __name__ == '__main__':
    main()
