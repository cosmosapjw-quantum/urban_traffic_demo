"""Verify source-pinned current-native original 100k continuous 20s chain."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def test_r8_20s_source_locked_matches_r7_binary_identity_and_ledgers():
    root=ROOT/'artifacts/v03_fifo_cohort_20261121'
    a=json.loads((root/'R7_original_100k_10s.json').read_text())
    b=json.loads((root/'R8_original_100k_20s.json').read_text())
    assert a['status']==b['status']=='EXECUTED_CURRENT_SOURCE_CONTINUOUS_HORIZON'
    assert (a['completed_time_s'],b['start_time_s'],b['completed_time_s'])==(25660,25660,25680)
    assert b['requested_duration_s']==b['valid_advanced_duration_s']==20
    assert b['previous_full_checkpoint_sha256']==a['final_checkpoint_sha256']
    assert b['previous_full_checkpoint_bytes']==a['final_checkpoint_bytes']
    assert b['previous_mass_ledger']==a['completed_mass_ledger']
    assert b['current_candidate_source_sha256']==a['current_candidate_source_sha256']
    assert b['current_native_binary_sha256']==a['current_native_binary_sha256']
    assert b['current_driver_identity']==a['current_driver_identity']
    assert b['current_source_dirty'] is False and b['previous_checkpoint_full_wire_roundtrip_exact']
    assert b['native_process_cap_bytes']==8*1024**3
    assert b['original_full_day_acceptance']=='BLOCKED_0_OF_9'
    assert b['error'] is None and b['completed_mass_ledger']
    assert len(b['completed_step_wall_s'])==2
    assert [x['completed_time_s'] for x in b['completed_step_wall_s']]==[25670,25680]
