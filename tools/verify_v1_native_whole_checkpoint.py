"""Verify a whole-city native checkpoint against its bound measurement receipt.

Creates a fresh native runtime, checks raw checkpoint byte identity and performs
one continuation attempt. A resource rejection must retain the same valid state.
This diagnostic never promotes a short execution to release acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'src')]
from tools.run_v1_acceptance import load_release_city
from metroflow.v1.activity import compile_activity
from metroflow.v1.factorized_demand import compile_factorized_demand
from metroflow.v1.release_inventory import InventoryPolicy, build_inventory
from metroflow.v1.release_plan import ReleasePlan
from metroflow.v1.native_release_driver import NativeReleaseDriver
from metroflow.active_suffix.common import BudgetExceeded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (8*1024**3, 8*1024**3))
    receipt = json.loads(args.receipt.read_text())
    matrix_path = ROOT/'scenarios/v1/release_matrix.json'
    if hashlib.sha256(matrix_path.read_bytes()).hexdigest() != receipt['matrix_sha256']:
        raise ValueError('matrix identity differs')
    for path, digest in receipt['source_hashes'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest() != digest:
            raise ValueError('source identity differs: '+path)
    checkpoint = args.receipt.with_suffix('.checkpoint.bin')
    if hashlib.sha256(checkpoint.read_bytes()).hexdigest() != receipt['checkpoint_sha256']:
        raise ValueError('checkpoint identity differs')
    matrix = json.loads(matrix_path.read_text())
    case = next(c for c in matrix['cases'] if c['id'] == receipt['case'])
    city, _ = load_release_city(case)
    homes = tuple(compile_activity(city, b.id) for b in city.face_graph.blocks if b.residents)
    jobs = tuple(compile_activity(city, b.id, 'job') for b in city.face_graph.blocks if b.jobs)
    services = tuple(compile_activity(city, b.id, 'service', service_stock=b.jobs)
                     for b in city.face_graph.blocks if b.jobs)
    schedule = compile_factorized_demand(homes, jobs, services, day=case['day'],
        freight_kg=1000, worker_shortfall=matrix['worker_shortfall'])
    policy = dict(matrix['inventory_policy'])
    policy['departures_s'] = tuple(policy['departures_s'])
    driver = NativeReleaseDriver(ReleasePlan(city, schedule, step_s=receipt['step_s']),
        build_inventory(city, InventoryPolicy(**policy)), step_s=receipt['step_s'],
        byte_budget=receipt['native_accounting_budget_bytes'],
        record_budget=receipt['logical_record_budget'])
    state = driver.load(checkpoint)
    report = driver.report(state)
    result = dict(case=receipt['case'], receipt_sha256=hashlib.sha256(args.receipt.read_bytes()).hexdigest(),
        checkpoint_sha256=receipt['checkpoint_sha256'], restored_time_s=state.time_s,
        restored_report=report, full_campaign='NOT_RUN', status='PASS_SCOPED')
    with tempfile.TemporaryDirectory(dir=args.out.parent) as folder:
        rewritten = Path(folder)/'restored.bin'
        driver.save(rewritten, state)
        result['restored_checkpoint_byte_identical'] = (
            hashlib.sha256(rewritten.read_bytes()).hexdigest() == receipt['checkpoint_sha256'])
        if not result['restored_checkpoint_byte_identical']:
            raise AssertionError('native restore changed checkpoint bytes')
        try:
            advanced = driver.advance(state, state.time_s+receipt['step_s'])
            result.update(continuation='ADVANCED', continuation_time_s=advanced.time_s,
                          continuation_report=driver.report(advanced))
        except BudgetExceeded as exc:
            valid = exc.checkpoint
            driver.save(rewritten, valid)
            result.update(continuation='BLOCKED_RESOURCE', continuation_reason=str(exc),
                continuation_time_s=valid.time_s,
                rollback_checkpoint_byte_identical=(hashlib.sha256(rewritten.read_bytes()).hexdigest()
                    == receipt['checkpoint_sha256']))
            if not result['rollback_checkpoint_byte_identical']:
                raise AssertionError('failed next tick changed last valid checkpoint')
        if driver.report(state) != report:
            raise AssertionError('continuation mutated earlier snapshot')
    result['snapshot_unchanged_after_continuation'] = True
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if not k.endswith('report')}), flush=True)


if __name__ == '__main__':
    main()
