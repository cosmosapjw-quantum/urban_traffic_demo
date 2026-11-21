"""Exact original source V03 100k packet and transfer failure receipts."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/'artifacts/v03_live_header_age_20261122'

def test_r8_two_real_original_100k_attempts_are_negative_and_source_pinned():
    old=json.loads((ART/'R7_cross_native_100k_10s.json').read_text())
    new=json.loads((ART/'R8_cross_native_100k_10s.json').read_text())
    for x in (old,new):
        assert x['case']=='valley_weekday_s7'
        assert x['status']=='BLOCKED_RESOURCE'
        assert x['start_time_s']==x['completed_time_s']==25700
        assert x['requested_duration_s']==10 and x['valid_advanced_duration_s']==0
        assert x['blocked_target_time_s']==25710
        assert x['previous_checkpoint_full_wire_roundtrip_exact'] is True
        assert x['cross_native_original_25700_source'] is True
        assert x['native_process_cap_bytes']==8*1024**3
        assert x['current_source_dirty'] is False
        assert x['original_full_day_acceptance']=='BLOCKED_0_OF_9'
        assert x['final_checkpoint_sha256'] is None
        assert x['error']['class']=='BudgetExceeded'
        assert x['original_matrix_sha256']==hashlib.sha256(
            (ROOT/'scenarios/v1/release_matrix.json').read_bytes()).hexdigest()
        assert x['completed_step_wall_s']==[]
        assert x['trace_sites']['road_work:packet interval packing']['exceeded']==0
    assert old['current_candidate_source_sha256'] != new['current_candidate_source_sha256']
    assert old['current_native_binary_sha256'] != new['current_native_binary_sha256']
    assert 'required_bytes=5025228376' in old['error']['message']
    assert 'required_bytes=5025224784' in new['error']['message']
    assert new['trace_sites']['road_work:transfer header reservation']['exceeded']==0
    assert new['trace_sites']['road_work:transfer candidates']['exceeded']==1
