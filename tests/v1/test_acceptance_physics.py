"""V01 checks explicit predeclared tolerances and never equates audit with release."""
import json

import tools.audit_v1_physics as physics
from tools.audit_v1_physics import audit, unsupported_registered_access


def test_actual_observable_matrix_and_unresolved_release_blocker():
    r = audit(map_matrix=physics.ROOT/'artifacts/v1/map_audit/MATRIX.json')
    assert len(r['matrix']) == 7
    assert r['fixture_status'] == 'PASS'
    assert r['stability_reference']['status'] == 'PASS'
    assert r['static_braess']['status'] == 'PASS'
    assert r['status'] == 'BLOCKED_OPEN_P1'
    assert r['release_findings'][0]['count_maps'] == 38
    assert r['release_findings'][0]['severity'] == 'P1'
    assert 'microscopic safety' in r['claims_not_proved']


def test_registered_portal_count_cannot_substitute_for_access_evidence():
    assert unsupported_registered_access({'registered_portal_count': 1})
    assert unsupported_registered_access({'registered_unserved_residents': 0,
                                          'registered_access_status': 'NOT_RUN'})
    verified = {'registered_unserved_residents': 0, 'registered_access_status': 'PASS',
                'registered_entry_validation_status': 'PASS',
                'registered_connectivity_status': 'PASS', 'registered_access_cdf': [[60, 1.0]]}
    assert not unsupported_registered_access(verified)
    for missing in verified:
        assert unsupported_registered_access({k: v for k, v in verified.items() if k != missing})


def test_incomplete_map_matrix_stays_blocked(tmp_path, monkeypatch):
    matrix = tmp_path / 'artifacts/v1/map_audit/MATRIX.json'
    matrix.parent.mkdir(parents=True)
    matrix.write_text(json.dumps({'cases': []}))
    monkeypatch.setattr(physics, 'ROOT', tmp_path)
    result = audit(map_matrix=matrix)
    assert result['status'] == 'BLOCKED_OPEN_P1'
    assert result['release_findings'][0]['matrix_incomplete']


def test_design_case_coverage_allows_repeated_physical_maps():
    cases = [dict(case=str(i), family='primary', seed=7, identity='same') for i in range(38)]
    assert not physics.incomplete_map_matrix(cases)
    assert physics.incomplete_map_matrix(cases[:-1] + [cases[0]])
