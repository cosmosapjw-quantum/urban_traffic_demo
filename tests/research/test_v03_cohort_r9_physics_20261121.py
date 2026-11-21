"""Original 100k physical 40s request must preserve partial-prefix blocker."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[2]
def test_r9_current_native_40s_requested_has_only_valid_20s_and_precise_pack_block():
    root=ROOT/'artifacts/v03_fifo_cohort_20261121'
    prev=json.loads((root/'R8_original_100k_20s.json').read_text())
    row=json.loads((root/'R9_original_100k_requested_40s.json').read_text())
    assert row['status']=='BLOCKED_RESOURCE_WITH_VALID_PREFIX'
    assert row['start_time_s']==prev['completed_time_s']==25680
    assert row['requested_duration_s']==40
    assert row['valid_advanced_duration_s']==20
    assert row['completed_time_s']==25700
    assert row['blocked_target_time_s']==25710
    assert row['previous_full_checkpoint_sha256']==prev['final_checkpoint_sha256']
    assert row['previous_mass_ledger']==prev['completed_mass_ledger']
    assert row['current_candidate_source_sha256']==prev['current_candidate_source_sha256']
    assert row['current_native_binary_sha256']==prev['current_native_binary_sha256']
    assert row['previous_checkpoint_full_wire_roundtrip_exact'] is True
    assert row['error']['class']=='BudgetExceeded'
    assert 'phase=packet interval packing' in row['error']['message']
    assert 'required_bytes=4974672624' in row['error']['message']
    assert 'budget_bytes=4974665823' in row['error']['message']
    assert row['final_checkpoint_sha256']=='ac7a209c6adfd594c791d1ac4b5b33c6e013ae73b7b594e42121115c89bd8369'
    assert [x['completed_time_s'] for x in row['completed_step_wall_s']]==[25690,25700]
    assert row['original_full_day_acceptance']=='BLOCKED_0_OF_9'
    z=row['trace_sites']['road_work:packet interval packing']['terms_at_max']
    assert z['completed_source_combine_scratch_replaced']==0
    assert z['incoming_descriptors_frozen']==1 and z['interval_transient']==0
    assert z['incoming_rows']>0
def test_r9_old_city_preps_rejected_on_new_source():
    r=json.loads((ROOT/'artifacts/v03_fifo_cohort_20261121/R9_prior_prep_source_drift_readiness.json').read_text())
    assert (r['dag']['completed'],r['dag']['total'])==(19,21)
    assert r['v03']['calendar_preparation_verified']==0
    assert r['v03']['completed_full_day_runs']==0
    assert all(row['reason']=='CURRENT_SOURCE_CONTENT_HASH_DIFFERS' for row in r['case_preparation'].values())
