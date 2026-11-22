"""Positive original 100,000 Valley 25,720 physical prefix and exact next blocker."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
E=ROOT/"artifacts/v03_age_loss_checkpoint_20261122"

def test_original_100k_25720_physically_completed_and_checkpoint_saved():
    d=json.loads((E/"R6_original_100k_25710_off_requested_20s.json").read_bytes())
    assert d["case"]=="valley_weekday_s7"
    assert d["status"]=="BLOCKED_RESOURCE_WITH_VALID_PREFIX"
    assert d["requested_duration_s"]==20
    assert d["valid_advanced_duration_s"]==10
    assert d["start_time_s"]==25710
    assert d["completed_time_s"]==25720
    assert d["blocked_target_time_s"]==25730
    assert d["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert d["completed_mass_ledger"]["vehicles"]["active"]>0
    assert d["completed_mass_ledger"]["persons"]["active"]>0
    assert len(d["completed_step_wall_s"])==1
    assert d["completed_step_wall_s"][0]["completed_time_s"]==25720
    assert abs(d["completed_step_wall_s"][0]["wall_s"]-66.120884895)<1e-8
    assert d["native_process_cap_bytes"]==8*1024**3
    assert d["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
    assert d["trace_mode"]=="off"
    assert d["current_source_dirty"] is False
    assert d["current_candidate_source_sha256"]=="b764149c9607d0b092ae74efd6f580abd678638ebc88586a580b89f47038dd66"
    assert d["current_native_binary_sha256"]=="062fd78f13d9eae7d3abc6b74a118f79498d26b273ef0ce421010cede3ab2af3"
    assert d["final_checkpoint_sha256"]=="447570b8721b17fa19edf159bc4c474cfd6ad41dc936ab0b0114d902e36f0bf9"
    assert d["final_checkpoint_bytes"]==4677350066
    assert "phase=tick preflight" in d["error"]["message"]
    assert "required_bytes=5170800112" in d["error"]["message"]
    assert "budget_bytes=4833535103" in d["error"]["message"]


def test_prior_25720_original_ten_second_validity_not_full_day():
    d=json.loads((E/"R6_original_100k_25710_off_requested_20s.json").read_bytes())
    assert d["completed_time_s"]<86400
    assert d["valid_advanced_duration_s"]<d["requested_duration_s"]
    assert d["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
