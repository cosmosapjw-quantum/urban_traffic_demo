"""Source-bound original full-native receipt smoke; does not claim 24h acceptance."""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[2]
def test_original_valley_100k_cohort_r7_10s_receipt_and_mass():
    p=ROOT/'artifacts/v03_fifo_cohort_20261121/R7_original_100k_10s.json'
    d=json.loads(p.read_text())
    matrix=(ROOT/'scenarios/v1/release_matrix.json').read_bytes()
    assert d['case']=='valley_weekday_s7'
    assert d['status']=='EXECUTED_CURRENT_SOURCE_CONTINUOUS_HORIZON'
    assert d['start_time_s']==25650 and d['completed_time_s']==25660
    assert d['valid_advanced_duration_s']==d['requested_duration_s']==10
    assert d['error'] is None and d['previous_checkpoint_full_wire_roundtrip_exact']
    assert d['current_source_dirty'] is False
    assert d['native_process_cap_bytes']==8*1024**3
    assert hashlib.sha256(matrix).hexdigest()==d['original_matrix_sha256']
    assert d['original_full_day_acceptance']=='BLOCKED_0_OF_9'
    assert d['final_checkpoint_sha256'] and d['final_checkpoint_bytes']>0
    assert len(d['completed_step_wall_s'])==1
    assert 0<d['peak_rss_bytes']<8*1024**3
    assert d['completed_mass_ledger']
    sites=d.get('trace_sites') or {}
    assert 'road_work:packet interval packing' in sites
