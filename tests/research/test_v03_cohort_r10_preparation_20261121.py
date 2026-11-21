"""Current-source 3-city native source preparation, never V03 release."""
import json
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/'artifacts/v03_fifo_cohort_20261121'
def test_r10_three_cities_current_native_prepared_after_prior_source_rejected():
    old=json.loads((ART/'R9_prior_prep_source_drift_readiness.json').read_text())
    new=json.loads((ART/'R10_current_candidate_readiness.json').read_text())
    assert old['v03']['calendar_preparation_verified']==0
    assert (new['dag']['completed'],new['dag']['total'])==(19,21)
    assert new['v03']['dependency_nodes_completed']==new['v03']['dependency_nodes_total']==3
    assert new['v03']['calendar_preparation_verified']==new['v03']['calendar_preparation_total']==3
    assert new['v03']['completed_full_day_runs']==0
    assert new['v03']['required_full_day_runs']==9
    assert new['v03']['status']=='BLOCKED' and not new['v03']['ready_for_release']
    assert all(v['status']=='PREPARED_SCOPED' for v in new['case_preparation'].values())
    sha=new['measurement_context']['live_candidate_source_sha256']
    native=new['measurement_context']['live_native_binary_sha256']
    assert sha=='1e8bd64f670fc11c909d843a07ba815fd11bc0dd2332be9af222d69374ebcb96'
    assert native=='87ba37d8d5b749fc64d6588e17c33b912b73fe2d9627803ca7f6024241ebfe81'
    matrix_sha=hashlib.sha256((ROOT/'scenarios/v1/release_matrix.json').read_bytes()).hexdigest()
    legs=0
    for case in ('river_weekday_s17','coastal_weekend_s41','valley_weekday_s7'):
        row=json.loads((ART/'R10_preparation'/(case+'.prepare.json')).read_text())
        assert row['status']=='WHOLE_CALENDAR_PREPARED'
        assert row['simulated_s']==row['horizon_s']==0
        assert row['step_s']==10
        assert row['calendar']['resident_stock']==100000
        assert row['candidate_source_sha256']==sha
        assert row['native_binary_sha256']==native
        assert row['matrix_sha256']==matrix_sha
        assert row['candidate']['source_dirty'] is False
        assert row['wall_s']<=7200 and row['peak_rss_bytes']<8*1024**3
        legs += row['calendar']['legs']
    assert legs==8461965
