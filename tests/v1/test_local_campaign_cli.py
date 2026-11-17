"""Campaign failures cannot become reused successful execution receipts."""
import json
import hashlib
from types import SimpleNamespace

import tools.run_v1_local_acceptance as cli
from metroflow.active_suffix.common import BudgetExceeded
from metroflow.v1.scenarios import scenario_city


def test_preparation_failure_preserves_cursor_and_never_reports_execution(tmp_path,monkeypatch):
    error=BudgetExceeded('calendar budget')
    error.checkpoint=SimpleNamespace(report=lambda:dict(cursor={'offset':0},remaining_legs=50000))
    def fail(*args):
        raise error
    monkeypatch.setattr(cli,'prepare',fail)
    matrix=tmp_path/'matrix.json'
    matrix.write_text('{}')
    args=SimpleNamespace(step_s=10,horizon_s=0,matrix=matrix,out=tmp_path,label='case.prepare',prepare_only=True)
    assert cli.worker(args,{'limits':{'peak_rss_bytes':2**40}},dict(id='case'))==2
    result=json.loads((tmp_path/'case.prepare.json').read_text())
    assert result['status']=='BLOCKED_RESOURCE'
    assert result['simulated_s']==0
    assert result['last_valid']['cursor']['offset']==0
    assert result['last_valid']['remaining_legs']==50000
    assert result.get('route_latency',{}).get('status')=='NOT_MEASURED'
    assert result['route_latency']['observed_calls']==0
    assert result['route_latency']['p99_ns'] is None


def test_crashed_child_cannot_reuse_stale_success(tmp_path,monkeypatch):
    matrix=tmp_path/'matrix.json'
    matrix.write_text(json.dumps(dict(cases=[dict(id='case')],limits=dict(wall_s=1))))
    stale=tmp_path/'case.run1.json'
    stale.write_text(json.dumps(dict(status='EXECUTED_FOR_REVIEW',simulated_s=86400)))
    def crashed(cmd,**kwargs):
        assert not stale.exists()
        # Even a new success-shaped file cannot override a failed child exit.
        stale.write_text(json.dumps(dict(status='EXECUTED_FOR_REVIEW',case='case',simulated_s=86400)))
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(cli.subprocess,'run',crashed)
    monkeypatch.setattr(cli.sys,'argv',['runner','--run-local','--matrix',str(matrix),'--out',str(tmp_path)])
    assert cli.main()==2
    receipt=json.loads((tmp_path/'CAMPAIGN.json').read_text())
    assert receipt['status']=='BLOCKED'
    assert receipt['receipts'][0]['status']=='ENVIRONMENT_BLOCKER'


def test_failed_native_worker_receipt_keeps_latest_projection_diagnostics(tmp_path,monkeypatch):
    from metroflow.v1 import native_engine

    diagnostics=dict(input_parts=0,output_parts=0,cohorts=0,local_w1_bound_veh_s=0.,
                     checkpointed=False,scope='latest validated proposed road transition')
    runtime=SimpleNamespace(
        native=SimpleNamespace(execution_config=lambda:{},native_threads=1),
        storage_config=lambda:{},routing_metrics=lambda:{},
        projection_diagnostics=lambda:dict(diagnostics),last_advance_metrics={})
    checkpoint=SimpleNamespace(time_s=10.)
    def fail_after_projection(state,end):
        diagnostics.update(input_parts=7,output_parts=2,cohorts=1,local_w1_bound_veh_s=.125)
        error=BudgetExceeded('entry projection record budget')
        error.checkpoint=checkpoint
        raise error
    driver=SimpleNamespace(
        identity='projected-fixture',engine_backend='rust_whole',runtime=runtime,
        initial=lambda:SimpleNamespace(time_s=0.),advance=fail_after_projection,
        save=lambda path,state:path.write_text(str(state.time_s)),
        report=lambda state:dict(time_s=state.time_s),debug_state=lambda state:{})
    monkeypatch.setattr(cli,'prepare',lambda *args:(driver,dict(source_sha256='fixture',patch_sha256='fixture')))
    monkeypatch.setattr(native_engine,'native_binary_provenance',lambda:dict(status='TEST_DOUBLE'))
    monkeypatch.setattr(cli.resource,'setrlimit',lambda *args:None)
    matrix=tmp_path/'matrix.json'
    matrix.write_text('{}')
    args=SimpleNamespace(step_s=10,horizon_s=20,matrix=matrix,out=tmp_path,
                         label='projected.failure',prepare_only=False,resume=False,
                         engine_backend='rust_whole')

    assert cli.worker(args,{'limits':{'peak_rss_bytes':2**40}},dict(id='case'))==2
    result=json.loads((tmp_path/'projected.failure.json').read_text())
    assert result['status']=='BLOCKED_RESOURCE'
    assert result['simulated_s']==10.
    assert result['last_valid']['time_s']==10.
    assert result['entry_projection']==diagnostics
    assert (tmp_path/result['last_valid']['path']).read_text()=='10.0'


def test_small_preparation_receipt_includes_measured_route_bounds(tmp_path,monkeypatch):
    city=scenario_city(1000)
    monkeypatch.setattr(cli,'load_release_city',lambda case:(city,dict(source_sha256='fixture',patch_sha256='fixture')))
    config=dict(worker_shortfall='unassigned_home',inventory_policy=dict(departures_s=[21600,32400]),
                route_materialization_budget=100,limits=dict(peak_rss_bytes=2**40))
    matrix=tmp_path/'matrix.json'
    matrix.write_text(json.dumps(config))
    args=SimpleNamespace(step_s=10,horizon_s=0,matrix=matrix,out=tmp_path,label='small.prepare',prepare_only=True)
    assert cli.worker(args,config,dict(id='small',day='weekday'))==0
    result=json.loads((tmp_path/'small.prepare.json').read_text())
    report=result['route_latency']
    assert result['status']=='WHOLE_CALENDAR_PREPARED'
    assert result['simulated_s']==0
    assert result['matrix_sha256']==hashlib.sha256(matrix.read_bytes()).hexdigest()
    assert report['status']=='MEASURED_INTERVAL'
    assert report['observed_calls']>0
    assert report['failed_calls']==0
    assert report['p99_ns']['lower']<=report['p99_ns']['upper']
    assert 'route_latency_p99' not in result
