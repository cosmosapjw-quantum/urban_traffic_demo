"""Campaign failures cannot become reused successful execution receipts."""
import json
from types import SimpleNamespace

import tools.run_v1_local_acceptance as cli
from metroflow.active_suffix.common import BudgetExceeded


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
