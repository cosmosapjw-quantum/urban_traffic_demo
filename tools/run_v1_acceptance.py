"""V03 map-bound preflight. Full local transport campaign remains blocked.

This entry point never substitutes the two-zone C02 fixture for a release map.
"""
import argparse
import hashlib
import json
import lzma
import platform
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from metroflow.v1.city import load_city, CityContractError  # noqa: E402
from metroflow.v1.activity import compile_activity  # noqa: E402
from metroflow.v1.factorized_demand import compile_factorized_demand  # noqa: E402
from metroflow.v1.demand import compile_daily_demand  # noqa: E402


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_release_city(case, root=ROOT):
    evidence = root / 'artifacts/v1_portal_resolution_20261027'
    row = json.loads((evidence / f"{case['map_index']:02d}.audit.json").read_text())
    if (row['case'], row['seed']) != (case['map_case'], case['seed']):
        raise ValueError('release case differs from frozen map case/seed')
    patch = evidence / row['patch']
    if sha(patch) != row['patch_sha256']:
        raise ValueError('construction patch SHA differs')
    payload = json.loads(lzma.decompress(patch.read_bytes()))
    source = root / 'artifacts/v1/map_audit' / payload['base_source']
    if sha(source) != payload['base_sha256']:
        raise ValueError('frozen source SHA differs')
    data = json.loads(lzma.decompress(source.read_bytes()))
    if data['identity'] != payload['parent_identity']:
        raise ValueError('source city identity differs')
    data.update(portals=payload['portals'], identity=payload['identity'])
    city = load_city(data)
    if city.identity != row['identity'] or city.requested_population != 100000:
        raise ValueError('release identity or 100k population differs')
    return city, row


def preflight(case, root=ROOT):
    city, row = load_release_city(case, root)
    homes = tuple(compile_activity(city, b.id) for b in city.face_graph.blocks if b.residents)
    jobs = tuple(compile_activity(city, b.id, 'job') for b in city.face_graph.blocks if b.jobs)
    # Explicit synthetic service capacity prior, separate measure from jobs.
    services = tuple(compile_activity(city, b.id, 'service', service_stock=b.jobs)
                     for b in city.face_graph.blocks if b.jobs)
    result = dict(case=case['id'], city_identity=city.identity, residents=city.requested_population,
                  source_sha256=row['source_sha256'], patch_sha256=row['patch_sha256'],
                  homes=len(homes), job_zones=len(jobs), service_zones=len(services),
                  service_prior='service opportunities equal declared job stock; separate measure',
                  executed_simulated_s=0, runtime_rss_measurement='NOT_RUN')
    try:
        schedule = compile_daily_demand(homes, jobs, services, day=case['day'],
                                        freight_kg=1000, max_cohorts=case['max_cohorts'])
        result.update(demand_status='COMPILED', demand_identity=schedule.identity,
                      cohorts=len(schedule.cohorts), legs=len(schedule.legs))
    except CityContractError as exc:
        result.update(demand_status=exc.status, demand_reason=exc.reason)
    try:
        lazy = compile_factorized_demand(homes, jobs, services, day=case['day'], freight_kg=1000,
                    worker_shortfall=case.get('worker_shortfall', 'reject'),
                    max_factors=case['max_cohorts'])
        result.update(factorized_status='COMPILED', factorized_identity=lazy.identity,
                      requested_workers=lazy.requested_workers, allocated_workers=lazy.allocated_workers,
                      unassigned_workers=lazy.unassigned_workers,
                      marginal_factors=len(homes)+len(jobs)+len(services)+len(lazy.modes),
                      worker_policy=lazy.worker_shortfall,
                      representation='exact independent OD; lazy generation; no dense Cartesian materialization')
    except CityContractError as exc:
        result.update(factorized_status=exc.status, factorized_reason=exc.reason)
    result.update(status='BLOCKED_IMPLEMENTATION_DEPENDENCY',
                  blocker='whole-calendar activation/checkpoint driver and release-wide fixed fleet/depot inputs remain; bounded joint runtime is available',
                  local_campaign='BLOCKED_LOCAL_EXECUTION',
                  next_action='Connect ReleasePlan cursor to one JointReleaseRuntime and explicit fleet/depot inventory; then execute local three-repeat campaign')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--matrix', type=Path, default=ROOT/'scenarios/v1/release_matrix.json')
    p.add_argument('--repeat', type=int, default=3)
    p.add_argument('--case')
    p.add_argument('--preflight-only', action='store_true')
    p.add_argument('--out', type=Path, default=ROOT/'artifacts/v1/local_acceptance')
    args = p.parse_args()
    if args.repeat != 3:
        p.error('release campaign requires exactly three measured repeats')
    matrix = json.loads(args.matrix.read_text())
    cases = [dict(c, worker_shortfall=matrix.get('worker_shortfall', 'reject')) for c in matrix['cases'] if args.case is None or c['id'] == args.case]
    if not cases:
        p.error('unknown release case')
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in cases:
        row = preflight(case)
        rows.append(row)
        (args.out/(case['id']+'.preflight.json')).write_text(json.dumps(row,indent=2)+'\n')
        print(json.dumps(row), flush=True)
    report = dict(status='BLOCKED', preflight_only=args.preflight_only,
                  environment=dict(python=platform.python_version(), platform=platform.platform()),
                  repeat=args.repeat, completed_runs=0, cases=rows)
    (args.out/'RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n')
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
