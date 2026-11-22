"""Exact original 100k negative indexed sweep evidence, no invented completed tick."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
A=ROOT/"artifacts/v03_quantile_sweep_20261122"

def test_original_valley_cross_native_narrow_index_improves_real_but_not_enough():
    d=json.loads((A/"R6_original_100k_25710_off_20s.json").read_bytes())
    assert d["case"]=="valley_weekday_s7"
    assert d["start_time_s"]==d["completed_time_s"]==25710
    assert d["requested_duration_s"]==20
    assert d["valid_advanced_duration_s"]==0
    assert d["blocked_target_time_s"]==25720
    assert d["error"]["class"]=="BudgetExceeded"
    assert "phase=indexed sweep preflight" in d["error"]["message"]
    assert "required_bytes=4988500600" in d["error"]["message"]
    assert "budget_bytes=4952574903" in d["error"]["message"]
    assert d["status"]=="BLOCKED_RESOURCE"
    assert d["final_checkpoint_sha256"] is None
    assert d["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert d["previous_mass_ledger"] is not None
    assert d["cross_native_original_25710_source"] is True
    assert d["trace_mode"]=="off"
    assert d["current_source_dirty"] is False
    assert d["native_process_cap_bytes"]==8*1024**3
    assert d["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
    assert d["current_candidate_source_sha256"]=="2558177c593f4959250ec64fb803fbd9e91a9075fdb92c8710353eddd01f6f9d"
    assert d["current_native_binary_sha256"]=="e292032940e0fe89c6a370df196d46044c9f6727f31333f289bf7d6096ad4840"
