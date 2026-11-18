"""No actual field data used: integrity tests for paired observation scorer."""
from __future__ import annotations
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import csv
import json
import math
import subprocess
import sys
import pytest

SCRIPT=Path(__file__).resolve().parents[2]/"tools/research/kcmb_field_metrics.py"
spec=spec_from_file_location("kcmb_field_metrics",SCRIPT)
metrics=module_from_spec(spec)
sys.modules[spec.name]=metrics
spec.loader.exec_module(metrics)


def row(i,observed,simulated,ov,sv,split="holdout"):
    return dict(site_id="siteA",split=split,start_s=str(60*i),
        end_s=str(60*(i+1)),observed_count_veh=str(observed),
        simulated_count_veh=str(simulated),
        observed_mean_speed_mps=str(ov),simulated_mean_speed_mps=str(sv))


def test_known_geh_count_flow_and_speed_errors():
    a=metrics.score_rows([row(0,100,125,10,12),row(1,0,0,0,0),
                          row(2,25,30,8,8)])
    r=a["split_metrics"]["holdout"]
    expected=math.sqrt(2*25**2/225)
    expected2=math.sqrt(2*5**2/55)
    assert r["geh_mean"]==pytest.approx((expected+expected2)/3)
    assert r["count_mae_veh_per_window"]==10.
    assert r["mean_speed_rmse_mps"]==pytest.approx(math.sqrt(2))
    assert r["speed_pair_count"]==2
    assert a["split_metrics"]["calibration"]["status"]=="NOT_MEASURED"
    assert a["field_dataset_provenance"]=="UNVERIFIED_FROM_ROWS"


def test_invalid_units_time_and_duplicates_are_rejected():
    with pytest.raises(ValueError):
        metrics.score_rows([])
    with pytest.raises(ValueError,match="duplicate"):
        x=row(0,1,1,10,10)
        metrics.score_rows([x,x])
    with pytest.raises(ValueError,match="site/split/window"):
        metrics.score_rows([row(0,1,1,10,10,split="unknown")])
    with pytest.raises(ValueError,match="negative"):
        metrics.score_rows([row(0,1,-1,10,10)])
    with pytest.raises(ValueError,match="nonfinite"):
        metrics.score_rows([row(0,1,1,float("nan"),10)])
    with pytest.raises(ValueError,match="site/split/window"):
        bad=row(0,1,1,10,10);bad["end_s"]="0"
        metrics.score_rows([bad])


def test_actual_cli_produces_machine_readable_scoped_receipt(tmp_path):
    csv_path=tmp_path/"paired_synthetic.csv"
    out=tmp_path/"result.json"
    with csv_path.open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=metrics.SCHEMA)
        writer.writeheader()
        writer.writerow(row(0,100,90,10,9))
    process=subprocess.run([sys.executable,str(SCRIPT),"--paired-csv",str(csv_path),
                            "--output",str(out)],capture_output=True,text=True)
    assert process.returncode==0,process.stderr
    r=json.loads(out.read_text())
    assert r["split_metrics"]["holdout"]["records"]==1
    assert r["split_metrics"]["holdout"]["mean_speed_rmse_mps"]==1
    assert r["field_dataset_provenance"]=="UNVERIFIED_FROM_ROWS"


def test_train_holdout_cannot_share_same_detector_time_window():
    # Adversarial C9 regression: same measurements in calibration and holdout
    # must not be treated as statistically independent evidence.
    with pytest.raises(ValueError,match="duplicate|leakage|overlap"):
        metrics.score_rows([row(0,10,11,4,4,split="calibration"),
                            row(0,10,11,4,4,split="holdout")])


def test_overlapping_calibration_and_holdout_windows_are_rejected():
    with pytest.raises(ValueError,match="overlap|leakage"):
        x=row(0,10,11,4,4,split="calibration")
        y=row(0,10,11,4,4,split="holdout")
        y["start_s"]="30"
        y["end_s"]="90"
        metrics.score_rows([x,y])
