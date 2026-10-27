"""V01 checks explicit predeclared tolerances and never equates audit with release."""
from tools.audit_v1_physics import audit


def test_actual_observable_matrix_and_unresolved_release_blocker():
    r = audit()
    assert len(r['matrix']) == 7
    assert r['fixture_status'] == 'PASS'
    assert r['stability_reference']['status'] == 'PASS'
    assert r['static_braess']['status'] == 'PASS'
    assert r['status'] == 'BLOCKED_OPEN_P1'
    assert r['release_findings'][0]['count_maps'] == 38
    assert r['release_findings'][0]['severity'] == 'P1'
    assert 'microscopic safety' in r['claims_not_proved']
