"""Constructor-grounded decomposition of calendar demand support (read-only).

Builds each case's whole-native engine exactly as the acceptance CLI does and
reads NativeWholeEngine.support_census(): every calendar leg classified by the
constructor's own support branch, with record counts and exact persons,
vehicles and cargo sums. Nothing is advanced; no physics or report changes.

usage: census_v1_demand_support.py OUT_DIR [CASE ...]
"""
import hashlib, json, os, resource, sys, time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.update(METROFLOW_V1_ENGINE_BACKEND='rust_whole', METROFLOW_V1_ROUTING_BACKEND='rust',
                  METROFLOW_V1_NATIVE_THREADS='1', METROFLOW_V1_STORAGE_POLICY='bounded_bytes_v1')
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from tools.run_v1_local_acceptance import atomic_json, candidate_provenance, observed_environment, prepare, peak_rss_bytes
from metroflow.v1.native_engine import native_binary_provenance

# Cause groups: physical-model scope vs input/map/implementation coverage.
GROUP = {
    'road_car_routed': ('SUPPORTED_ROAD', None),
    'internal_intrazonal_delay': ('SUPPORTED_INTERNAL', None),
    'internal_colocated_car': ('SUPPORTED_INTERNAL', None),
    'bus_service_assigned': ('SUPPORTED_SERVICE', None),
    'freight_service_assigned': ('SUPPORTED_SERVICE', None),
    'noncar_interzonal_no_transport_model': ('UNSUPPORTED', 'model_scope: no interzonal walk/bike/non-car transport model'),
    'car_no_road_access_origin': ('UNSUPPORTED', 'map/access: origin activity has no car road access node'),
    'car_no_road_access_destination': ('UNSUPPORTED', 'map/access: destination activity has no car road access node'),
    'car_no_road_access_both': ('UNSUPPORTED', 'map/access: neither endpoint has a car road access node'),
    'car_no_road_route': ('UNSUPPORTED', 'graph connectivity: legal-turn router found no path'),
    'car_endpoint_activity_null': ('UNSUPPORTED', 'input: endpoint activity is null'),
    'bus_endpoint_activity_null': ('UNSUPPORTED', 'input: endpoint activity is null'),
    'bus_no_service_access_origin': ('UNSUPPORTED', 'map/access: origin block has no service stop'),
    'bus_no_service_access_destination': ('UNSUPPORTED', 'map/access: destination block has no service stop'),
    'bus_no_service_access_both': ('UNSUPPORTED', 'map/access: no service stop at either block'),
    'bus_no_corridor_between_blocks': ('UNSUPPORTED', 'service model: no declared corridor between the block pair'),
    'bus_no_departure_after_ready': ('UNSUPPORTED', 'service schedule: no corridor departure after passenger ready time'),
    'freight_destination_activity_null': ('UNSUPPORTED', 'input: destination activity is null'),
    'freight_chained_leg_not_service_assigned': ('UNSUPPORTED', 'implementation: chained non-bus legs are never service-assigned'),
    'freight_no_depot': ('UNSUPPORTED', 'input: no depot'),
    'freight_no_service_access_destination': ('UNSUPPORTED', 'map/access: destination has no service node'),
    'freight_same_block_as_depot': ('UNSUPPORTED', 'service model: depot and destination in same block (no road leg)'),
    'freight_no_road_route': ('UNSUPPORTED', 'graph connectivity: no depot route'),
    'other_mode_or_endpoint': ('UNSUPPORTED', 'model_scope: mode/endpoint combination not handled'),
}

def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    matrix = json.loads((ROOT / 'scenarios/v1/release_matrix.json').read_text())
    limit = matrix['limits']['peak_rss_bytes']
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    cases = [c for c in matrix['cases'] if len(sys.argv) < 3 or c['id'] in sys.argv[2:]]
    summary = {}
    for case in cases:
        t0 = time.perf_counter()
        driver, _ = prepare(case, matrix, 10.0)
        rows = driver.runtime.native.support_census()
        report = driver.report(driver.initial())
        totals = defaultdict(lambda: dict(records=0, persons=0.0, vehicles=0.0, cargo_kg=0.0))
        for r in rows:
            g, cause = GROUP.get(r['reason'], ('UNCLASSIFIED', r['reason']))
            r['group'], r['cause'] = g, cause
            for key in (g, 'ALL'):
                t = totals[key]
                t['records'] += r['records']
                for k in ('persons', 'vehicles', 'cargo_kg'):
                    t[k] += r[k]
        construction = report['execution']['construction']
        assert totals['ALL']['records'] == construction['legs'], 'census does not cover every leg'
        assert totals['UNSUPPORTED']['records'] == construction['unsupported_legs'], 'unsupported count differs from engine'
        res = dict(case=case['id'], rows=rows, group_totals=dict(totals), construction=construction,
                   calendar=report['calendar'], wall_s=time.perf_counter() - t0)
        atomic_json(out / f"{case['id']}.json", res)
        summary[case['id']] = dict(group_totals=dict(totals), wall_s=res['wall_s'])
        print(json.dumps({case['id']: {k: v['records'] for k, v in totals.items()}}), flush=True)
        del driver
    atomic_json(out / 'SUMMARY.json', dict(status='CENSUS_COMPLETE', scope='constructor support branch; read-only',
        candidate=candidate_provenance(), native_binary=native_binary_provenance(),
        environment=observed_environment(), peak_rss_bytes=peak_rss_bytes(), cases=summary))

if __name__ == '__main__':
    main()
