"""Measured campaign receipts keep runtime failures and review obligations visible."""
import json
from types import SimpleNamespace

import pytest

import tools.run_v1_local_acceptance as cli
from metroflow.active_suffix.common import BudgetExceeded
from metroflow.v1.release_driver import DriverState
from test_native_engine import make_native, small_fixture
from test_native_whole_driver import fixture as driver_fixture


def report(time):
    calendar=dict(persons=120,vehicles=60,cargo_kg=10,resident_stock=100)
    ledger={u:dict(requested=v if time==86400 else v/3,
                   released=0.,completed=0.,pending=v if time==86400 else v/3,active=0.)
            for u,v in calendar.items() if u!='resident_stock'}
    return dict(calendar=dict(calendar=calendar),execution=dict(time_s=time,ledger=ledger))


def campaign_fixture():
    matrix=dict(cases=[dict(id='case')],population=100,limits=dict(wall_s=7200,peak_rss_bytes=8*1024**3))
    rows=[]
    for label,step,horizon,resume in [('run1',10,86400,False),('run2_resume',10,86400,True),
                                     ('run3',10,86400,False),('refined',5,28800,False)]:
        rows.append(dict(case='case',run_label='case.'+label,status='EXECUTED_FOR_REVIEW',
            step_s=step,horizon_s=horizon,simulated_s=horizon,resume_requested=resume,
            driver_identity='same' if step==10 else 'refined',matrix_sha256='matrix',
            source_sha256='source',patch_sha256='patch',engine_backend='rust_whole',
            candidate_source_sha256='c'*64,native_binary_sha256='d'*64,
            routing_backend='rust',final_checkpoint_sha256='a'*64,wall_s=1.,peak_rss_bytes=100,
            native_route_latency=dict(status='MEASURED_INTERVAL',observed_calls=4),
            report=report(horizon),refinement_prefix=report(28800)))
    return matrix,rows


def test_complete_campaign_requires_separate_refinement_review_not_invented_pass():
    matrix,rows=campaign_fixture()
    result=cli.assess_campaign(rows,matrix,matrix['cases'])
    assert result['status']=='MEASURED_REQUIRES_REVIEW'
    assert result['checkpoint_replay']['case'] is True
    assert result['refinement_assessment']['case']['status']=='REQUIRES_SEPARATE_REVIEW'
    assert result['issues']==[]


def test_checkpoint_digest_streams_without_whole_file_read(tmp_path,monkeypatch):
    import hashlib
    from pathlib import Path
    content=b'checkpoint fixture\0'*(128*1024)
    checkpoint=tmp_path/'large.bin'
    checkpoint.write_bytes(content)
    def forbidden(*args):
        raise AssertionError('whole-checkpoint read is forbidden')
    monkeypatch.setattr(Path,'read_bytes',forbidden)
    assert cli.file_sha256(checkpoint)==hashlib.sha256(content).hexdigest()


@pytest.mark.parametrize('message,kind',[
    ('native shared storage budget exhausted','shared_accounting_guard'),
    ('native capture/validation storage budget exceeded','checkpoint_working_budget_guard'),
    ('native checkpointability storage budget exceeded','checkpoint_working_budget_guard'),
    ('native road storage budget exceeded: phase=entry interval split','phase_working_budget_guard'),
    ('native journey stored/working byte budget','phase_working_budget_guard'),
    ('native service event sink storage budget exceeded: phase=service finish','phase_working_budget_guard'),
    ('whole-calendar native preflight needs more accounting bytes','static_accounting_guard'),
    ('allocation unavailable','allocation_or_other_budget')])
@pytest.mark.parametrize('binding',['retained_capacity_v2','retained_capacity_v3','retained_capacity_v4'])
def test_shared_resource_failures_are_not_reported_as_rss_or_fixed_partition(message,kind,binding):
    assert cli.resource_limit_kind(message,{'resource_binding':binding})==kind


@pytest.mark.parametrize('damage', ['replay','missing_refined','missing_repeat','resume',
                                  'ledger','missing_native_latency','rss','clock','refined_binding'])
def test_campaign_rejects_incomplete_or_inconsistent_evidence(damage):
    matrix,rows=campaign_fixture()
    if damage=='replay': rows[1]['final_checkpoint_sha256']='b'*64
    elif damage=='missing_refined': rows.pop()
    elif damage=='missing_repeat': rows.pop(1)
    elif damage=='resume': rows[1]['resume_requested']=False
    elif damage=='ledger': rows[0]['report']['execution']['ledger']['persons']['pending']=-10
    elif damage=='missing_native_latency': rows[0].pop('native_route_latency')
    elif damage=='rss': rows[0]['peak_rss_bytes']=9*1024**3
    elif damage=='clock': rows[0]['report']['execution']['time_s']=86390
    else: rows[3]['source_sha256']='different source'
    result=cli.assess_campaign(rows,matrix,matrix['cases'])
    assert result['status']=='BLOCKED'
    assert result['issues']


def test_native_router_observations_include_cache_hits_and_are_nonphysical(tmp_path):
    city,legs,corridors=small_fixture()
    native,_,_=make_native(city,legs,corridors)
    metrics=native.routing_metrics()
    assert metrics['status']=='MEASURED_INTERVAL'
    assert metrics['observed_calls']>0
    assert metrics['pair_cache_hits']>0
    assert metrics['search_calls']+metrics['pair_cache_hits']==metrics['observed_calls']
    assert metrics['min_ns']<=metrics['p99_ns']['lower']<=metrics['p99_ns']['upper']<=metrics['max_ns']
    assert metrics['source']=='native_whole_router.route'
    state=native.advance(native.initial(),120)
    before=tmp_path/'before.bin'
    after=tmp_path/'after.bin'
    native.save(str(before),state)
    assert native.routing_metrics()==metrics
    native.save(str(after),state)
    assert before.read_bytes()==after.read_bytes()


def test_shared_owner_pool_preserves_total_and_rejects_previous_split(tmp_path):
    from _metroflow_rust import NativeWholeEngine
    city,legs,corridors=small_fixture()
    legacy,calendar,payload=make_native(city,legs,corridors)
    total=256*1024**2
    native=NativeWholeEngine(calendar,payload,total,storage_policy='bounded_bytes_v1')
    config=native.storage_config()
    available=total-config['runtime_fixed_reserve_bytes']
    road=config['road_dynamic_allowance_bytes']
    journey=config['journey_dynamic_allowance_bytes']
    assert road==journey==available==config['dynamic_shared_pool_bytes']
    assert config['total_accounting_budget_bytes']==total
    assert native.identity==legacy.identity+':bounded_bytes_v1:retained_capacity_v4'
    old_available=total-config['conservative_static_accounting_bytes']
    old_road=old_available//2
    old_identity=legacy.identity+f':bounded_bytes_v1:{old_road}:{old_available-old_road}'
    assert native.identity!=old_identity
    # Restore the previous quota binding in a small checkpoint header. The
    # physical payload cannot authorize bypassing a changed resource policy.
    checkpoint=tmp_path/'bound.bin'
    native.save(str(checkpoint),native.initial())
    wire=checkpoint.read_bytes()
    size=int.from_bytes(wire[8:16],'little')
    old_binding=old_identity.encode()
    checkpoint.write_bytes(wire[:8]+len(old_binding).to_bytes(8,'little')+old_binding+wire[16+size:])
    with pytest.raises(ValueError,match='binding'):
        native.load(str(checkpoint))
    assert native.snapshot().time_s==0


def test_shared_budget_failure_resets_phase_quotas_for_load_and_replay(tmp_path):
    from dataclasses import replace
    from _metroflow_rust import NativeWholeEngine
    from metroflow.v1.journey import DelayLaw
    from metroflow.v1.schedules import DepartureProfile,DepartureWindow
    city,legs,_=small_fixture()
    internal=replace(legs[0],destination=legs[0].origin,
        intrazonal=DelayLaw(tuple((10000.+i,1/2000) for i in range(2000))),
        departures=DepartureProfile((DepartureWindow(0,200,1.),)))
    _,calendar,payload=make_native(city,(internal,))
    total=70*1024**2
    native=NativeWholeEngine(calendar,payload,total,storage_policy='bounded_bytes_v1')
    initial=tmp_path/'initial.bin'
    native.save(str(initial),native.initial())
    with pytest.raises(MemoryError,match='budget'):
        native.advance(native.initial(),200)
    valid=native.snapshot()
    assert 0<valid.time_s<200
    last=tmp_path/'last.bin'
    native.save(str(last),valid)
    expected=last.read_bytes()
    fresh=NativeWholeEngine(calendar,payload,total,storage_policy='bounded_bytes_v1')
    restored=fresh.load(str(last))
    assert fresh.report(restored)==native.report(valid)
    # A previous narrow phase quota must not leak into a new branch/decode.
    replay=native.advance(native.load(str(initial)),valid.time_s)
    native.save(str(last),replay)
    assert last.read_bytes()==expected


def test_binary_provenance_ignores_wrapper_and_rejects_ambiguity(tmp_path,monkeypatch):
    import hashlib
    import importlib.machinery
    import metroflow.v1.native_engine as frontend
    wrapper=tmp_path/'__init__.py';wrapper.write_text('wrapper, not native binary')
    binary=tmp_path/('_metroflow_rust'+importlib.machinery.EXTENSION_SUFFIXES[0])
    binary.write_bytes(b'actual binary fixture')
    modules={'_metroflow_rust':SimpleNamespace(__file__=str(wrapper)),
             '_metroflow_rust._metroflow_rust':SimpleNamespace(__file__=str(binary))}
    monkeypatch.setattr(frontend,'sys',SimpleNamespace(modules=modules))
    measured=frontend.native_binary_provenance()
    assert measured['sha256']==hashlib.sha256(binary.read_bytes()).hexdigest()
    assert measured['path']==str(binary.resolve()) and measured['size_bytes']==binary.stat().st_size
    other=tmp_path/('other'+importlib.machinery.EXTENSION_SUFFIXES[0]);other.write_bytes(b'other')
    modules['_metroflow_rust.other']=SimpleNamespace(__file__=str(other))
    assert frontend.native_binary_provenance()['status']=='NOT_MEASURED'
    modules.pop('_metroflow_rust.other');modules.pop('_metroflow_rust._metroflow_rust')
    assert frontend.native_binary_provenance()['status']=='NOT_MEASURED'


def test_nonresource_native_failure_retains_driver_checkpoint(monkeypatch):
    driver,_=driver_fixture(step_s=600)
    initial=driver.initial()
    later=driver.advance(initial,600)
    error=ValueError('synthetic numeric failure')
    error.checkpoint=later.runtime_state
    def fail(*args): raise error
    monkeypatch.setattr(driver.runtime,'advance',fail)
    with pytest.raises(ValueError) as caught:
        driver.advance(initial,1200)
    assert isinstance(caught.value.checkpoint,DriverState)
    assert caught.value.checkpoint.time_s==600


@pytest.mark.parametrize('failure_type',['value','resource','arithmetic'])
def test_worker_failure_progress_reports_actual_last_valid_time(tmp_path,monkeypatch,failure_type):
    driver,_=driver_fixture(step_s=600)
    state=driver.advance(driver.initial(),600)
    error={'value':ValueError('invalid fixture state'),
           'resource':BudgetExceeded('native journey storage byte budget'),
           'arithmetic':ArithmeticError('packet event resolution exhausted')}[failure_type]
    error.checkpoint=state
    def fail(*args): raise error
    monkeypatch.setattr(driver,'advance',fail)
    monkeypatch.setattr(cli,'prepare',lambda *args:(driver,dict(source_sha256='fixture',patch_sha256='fixture')))
    monkeypatch.setenv('METROFLOW_V1_ENGINE_BACKEND','rust_whole')
    matrix=tmp_path/'matrix.json';matrix.write_text('{}')
    args=SimpleNamespace(step_s=600,horizon_s=3600,matrix=matrix,out=tmp_path,label='failure',
                         prepare_only=False,resume=False)
    assert cli.worker(args,dict(limits=dict(peak_rss_bytes=2**40)),dict(id='fixture'))==2
    result=json.loads((tmp_path/'failure.json').read_text())
    progress=json.loads((tmp_path/'failure.progress.json').read_text())
    assert result['simulated_s']==result['last_valid']['time_s']==progress['simulated_s']==600
    assert driver.load(tmp_path/'failure.last_valid.bin').time_s==600
    assert result['last_valid_report']['execution']['time_s']==600
    if failure_type=='resource': assert result['resource_limit_kind']=='owner_quota_guard'
    if failure_type=='arithmetic':
        assert result['status']==result['failure_classification']==progress['status']=='NUMERICAL_ERROR'
        assert result['reason']=='ArithmeticError: packet event resolution exhausted'
        assert 'resource_limit_kind' not in result
    assert result['native_route_latency']['source']=='native_whole_router.route'


def test_failed_first_run_skips_same_candidate_dependent_repeats(tmp_path,monkeypatch):
    matrix=tmp_path/'matrix.json'
    matrix.write_text(json.dumps(dict(cases=[dict(id='case')],limits=dict(wall_s=1,peak_rss_bytes=100))))
    calls=[]
    def failed(cmd,**kwargs):
        calls.append(cmd)
        (tmp_path/'case.run1.json').write_text(json.dumps(dict(case='case',status='BLOCKED_RESOURCE')))
        return SimpleNamespace(returncode=2)
    monkeypatch.setattr(cli.subprocess,'run',failed)
    monkeypatch.setattr(cli.sys,'argv',['runner','--run-local','--matrix',str(matrix),'--out',str(tmp_path)])
    assert cli.main()==2
    rows=json.loads((tmp_path/'CAMPAIGN.json').read_text())['receipts']
    assert len(calls)==1 and len(rows)==4
    assert all(r['status']=='NOT_RUN_DEPENDENCY_BLOCKED' for r in rows[1:])
