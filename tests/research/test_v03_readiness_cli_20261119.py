"""Actual V03 read-only diagnostic CLI must preserve full-day acceptance semantics."""
import json, subprocess,sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/"tools/research/v03_readiness.py"


def test_no_preparation_still_has_correct_node_counts_and_no_full_days(tmp_path):
    path=tmp_path/"readiness.json"
    run=subprocess.run([sys.executable,str(SCRIPT),"--output",str(path)],
       cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert run.returncode==0,run.stderr
    obj=json.loads(path.read_text())
    assert (obj["dag"]["completed"],obj["dag"]["total"])==(19,21)
    assert obj["v03"]["calendar_preparation_verified"]==0
    assert obj["v03"]["completed_full_day_runs"]==0
    assert obj["v03"]["required_full_day_runs"]==9
    assert obj["v03"]["status"]=="BLOCKED"
    assert obj["v03"]["ready_for_release"] is False
    assert len(obj["source_file_sha256"]["release_matrix"])==64
    assert obj["observed_host"]["physical_memory_bytes"]>0
    assert obj["observed_host"]["reference_host_RAM_match"] in (True,False)


def test_nonmatching_receipt_file_causes_explicit_rejection_not_false_green(tmp_path):
    path=tmp_path/"out.json"
    data_dir=tmp_path/"prep"
    data_dir.mkdir()
    fake={"case":"river_weekday_s17","status":"WHOLE_CALENDAR_PREPARED",
          "matrix_sha256":"0"*64,"calendar":{"resident_stock":100000}}
    (data_dir/"river_weekday_s17.prepare.json").write_text(json.dumps(fake))
    run=subprocess.run([sys.executable,str(SCRIPT),"--prep-dir",str(data_dir),
                        "--output",str(path)],cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert run.returncode==0,run.stderr
    obj=json.loads(path.read_text())
    assert obj["v03"]["calendar_preparation_verified"]==0
    assert obj["case_preparation"]["river_weekday_s17"]["status"]=="REJECTED_EVIDENCE"
