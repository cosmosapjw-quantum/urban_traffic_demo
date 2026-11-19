"""Readiness strictly from source V03 DAG/matrix and authentic prepared receipts."""
import copy,hashlib,json
from pathlib import Path
import pytest
from metroflow.v1.v03_readiness import assess_v03_readiness

ROOT=Path(__file__).resolve().parents[2]
def auth():
    p=json.loads((ROOT/'docs/v1/PLAN.json').read_bytes())
    raw=(ROOT/'scenarios/v1/release_matrix.json').read_bytes()
    return p,json.loads(raw),hashlib.sha256(raw).hexdigest()

def prepared(name,sha):
    return dict(case=name,status='WHOLE_CALENDAR_PREPARED',engine_backend='rust_whole',
      step_s=10,horizon_s=86400,simulated_s=0,matrix_sha256=sha,
      source_sha256='a'*64,patch_sha256='b'*64,candidate_source_sha256='c'*64,
      native_binary_sha256='d'*64,driver_identity='e'*64,
      calendar=dict(resident_stock=100000,legs=5093765),wall_s=3.,
      peak_rss_bytes=2*1024**3,candidate=dict(source_dirty=False))

def test_exact_21_node_authority_not_a_release_pass():
    p,m,sha=auth();a=assess_v03_readiness(p,m,matrix_sha256=sha)
    assert a['dag']['completed']==19 and a['dag']['total']==21
    assert a['dag']['not_completed']=={'V03':'BLOCKED','RLS01':'PLANNED'}
    assert a['v03']['dependency_nodes_completed']==a['v03']['dependency_nodes_total']==3
    assert a['v03']['calendar_preparation_verified']==0
    assert a['v03']['calendar_preparation_total']==3
    assert a['v03']['completed_full_day_runs']==0
    assert a['v03']['required_full_day_runs']==9
    assert a['v03']['status']=='BLOCKED'
    assert a['v03']['rss_bytes_max']==8*1024**3
    assert a['v03']['population_residents_per_case']==100000

def test_three_real_preparations_do_not_impersonate_nine_full_days():
    p,m,sha=auth();rs=[prepared(c['id'],sha) for c in m['cases']]
    a=assess_v03_readiness(p,m,matrix_sha256=sha,preparation_receipts=rs)
    assert a['v03']['calendar_preparation_verified']==3
    assert a['v03']['completed_full_day_runs']==0
    assert a['dag']['completed']==19
    assert all(x['status']=='PREPARED_SCOPED' for x in a['case_preparation'].values())

def test_wrong_binding_or_resource_fails_without_readiness_credit():
    p,m,sha=auth();r=prepared(m['cases'][0]['id'],sha)
    for field,value in [('matrix_sha256','x'*64),('engine_backend','python_oracle'),
                        ('status','EXECUTED_FOR_REVIEW'),('step_s',5),
                        ('peak_rss_bytes',9*1024**3)]:
        corrupt=dict(r);corrupt[field]=value
        a=assess_v03_readiness(p,m,matrix_sha256=sha,preparation_receipts=[corrupt])
        assert a['v03']['calendar_preparation_verified']==0
    corrupt=copy.deepcopy(r);corrupt['calendar']['resident_stock']=99999
    assert assess_v03_readiness(p,m,matrix_sha256=sha,preparation_receipts=[corrupt])['v03']['calendar_preparation_verified']==0

def test_unknown_or_duplicate_receipt_and_mutated_dag_rejected():
    p,m,sha=auth();r=prepared(m['cases'][0]['id'],sha)
    with pytest.raises(ValueError,match='duplicate'):
        assess_v03_readiness(p,m,matrix_sha256=sha,preparation_receipts=[r,r])
    with pytest.raises(ValueError,match='unknown'):
        assess_v03_readiness(p,m,matrix_sha256=sha,preparation_receipts=[prepared('unknown',sha)])
    p['nodes'][0]['status']='BLOCKED'
    with pytest.raises(ValueError,match='plan|progress|completion'):
        assess_v03_readiness(p,m,matrix_sha256=sha)
