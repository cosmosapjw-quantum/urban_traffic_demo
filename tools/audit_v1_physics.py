"""Bounded V01 scientific audit, preserving unresolved release blockers.

All tolerances below are fixed before running. Selected microcases exercise the
actual V1 transport/node oracles. OVM eigenmodes are a separate local reference.
"""
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from metroflow.v1.kinetic_oracles import kinetic_oracles  # noqa: E402
from metroflow.v1.junction_oracles import junction_oracles  # noqa: E402
from metroflow.v1.timing_oracles import timing_oracles, timing_fixture  # noqa: E402
from metroflow.v1.routing_oracles import routing_oracles  # noqa: E402
from metroflow.audit_observables import ovm_modes  # noqa: E402

TOLERANCES = {'freeflow_s': 1.0, 'freeflow_refinement_s': 1.0,
              'outlet_age_residual_s': .25, 'mode_residual_per_s': 1e-12,
              'braess_min': .05}


def unsupported_registered_access(case):
    """A portal count alone is not evidence of a usable physical connection."""
    unserved = case.get('registered_unserved_residents')
    return not (
        isinstance(unserved, (int, float)) and not isinstance(unserved, bool)
        and math.isfinite(unserved) and unserved == 0
        and case.get('registered_access_status') == 'PASS'
        and case.get('registered_entry_validation_status') == 'PASS'
        and case.get('registered_connectivity_status') == 'PASS'
        and isinstance(case.get('registered_access_cdf'), list)
        and bool(case['registered_access_cdf'])
    )


def audit():
    kinetics = {r['case']: r for r in kinetic_oracles()}
    nodes = {r['case']: r for r in junction_oracles()}
    timing = {r['case']: r for r in timing_oracles()}
    routing = {r['case']: r for r in routing_oracles()}
    model = timing_fixture(.1, window=0, mass=1, lengths=(100.,))
    admitted = model.advance(model.initial(), .1)
    eta = model.link_eta(admitted, '0').elapsed_s
    final = model.advance(admitted, 15.)
    outlet = [e for e in final.events if e.destination is None]
    mass = math.fsum(e.mass for e in outlet)
    actual = math.fsum(e.mass*(e.start_s+e.end_s)/2 for e in outlet)/mass - admitted.road.time_s
    mode = ovm_modes(1.,2.,.1)
    z = complex(*mode['modes_per_s'][0])
    residual = abs(2*z*z + z - (complex(math.cos(.1),math.sin(.1))-1))
    bridge = ROOT/'artifacts/v1/map_audit/MATRIX.json'
    data = json.loads(bridge.read_text())
    cases = data.get('cases', [])
    unserved = [x for x in cases if unsupported_registered_access(x)]
    matrix_incomplete = len(cases) != 38 or len({x.get('identity') for x in cases}) != 38
    measured = [
        ('freeflow', timing['two_link_210m']['status']=='PASS', 'T04 numerical refinement; 210m analytical travel time'),
        ('collision_reference', kinetics['latent_continuous_reference']['status']=='PASS' and kinetics['gap_closure_counterexample']['status']=='PASS', 'T02 declared mean-gap closure and independent homogeneous latent reference'),
        ('merge', nodes['merge3:1']['status']=='PASS', 'T03 priority 3:1; allocation and actual packet flux'),
        ('turn', nodes['blockedshared']['status']=='PASS' and nodes['independentturn']['status']=='PASS', 'T03 real pooled/independent lane partitions'),
        ('signal', nodes['redboundary']['status']=='PASS', 'T03 half-open signal event boundary'),
        ('closure', nodes['bridgepairedclosure']['status']=='PASS', 'T03 paired directional closure registry, not full day incident'),
        ('cost_error', abs(actual-eta)<=TOLERANCES['outlet_age_residual_s'], 'T04 same frozen physical free-flow link; includes outlet discretization'),
    ]
    matrix=[dict(observable=k,status='PASS' if ok else 'NOT_ACCEPTED',implementation=scope,
                 approximation='conditional fixture/finite time step',unsupported='general safety, global shock and real-city calibration')
            for k,ok,scope in measured]
    braess = routing['static_braess_minutes']
    findings = []
    if unserved or matrix_incomplete:
        findings.append(dict(id='V01-P1-REGISTERED-PORTALS',severity='P1',severity_basis='provisional audit assessment, not formal review classification',status='OPEN',
                             scope='release product / V02 maps',count_maps=len(unserved),
                             matrix_incomplete=matrix_incomplete,
                             reason='registered resident access or physical connectivity not verified',
                             evidence='artifacts/v1/map_audit/MATRIX.json'))
    return dict(status='BLOCKED_OPEN_P1' if findings else 'SCOPED_AUDIT_COMPLETE',
                fixture_status='PASS' if all(x['status']=='PASS' for x in matrix) else 'NOT_ACCEPTED',
                tolerances=TOLERANCES, matrix=matrix,
                cost_error=dict(eta_s=eta,actual_after_admission_s=actual,error_s=actual-eta),
                kinetics=list(kinetics.values()),junctions=list(nodes.values()),timing=list(timing.values()),
                static_braess=braess,
                stability_reference=dict(**mode, characteristic_residual=residual,
                    status='PASS' if mode['largest_real_part_per_s']>0 and residual<TOLERANCES['mode_residual_per_s'] else 'NOT_ACCEPTED',
                    qualification='OVM ring reference; NOT a V1 packet-network instability certificate'),
                release_findings=findings,
                claims_not_proved=['full FIFO','shock convergence','microscopic safety','global V1 stability',
                                   'real-world calibration','full city/day release'],
                ci='DEFERRED_BY_USER')


if __name__ == '__main__':
    result = audit()
    print(json.dumps(result,indent=2,allow_nan=False))
    # Non-zero when release acceptance remains blocked; audited fixture results stay visible.
    raise SystemExit(0 if result['status']=='SCOPED_AUDIT_COMPLETE' and result['fixture_status']=='PASS' else 2)
