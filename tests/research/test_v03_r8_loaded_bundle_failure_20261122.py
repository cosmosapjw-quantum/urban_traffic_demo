"""Preserve original 100k 25,710 cross-native decoder succeeded then load admission failed."""
import json
from pathlib import Path
A=Path(__file__).resolve().parents[2]/"artifacts/v03_variance_restart_20261122"
def test_legacy_load_3max_not_a_real_finalized_physical_tick():
    x=json.loads((A/"R8_original_100k_25710_requested_20s.json").read_bytes())
    assert x["case"]=="valley_weekday_s7"
    assert x["status"]=="ERROR"
    assert x["requested_duration_s"]==20
    assert x["current_source_dirty"] is False
    assert x["cross_native_original_25710_source"] is True
    assert x["start_time_s"]==25710
    assert x["valid_advanced_duration_s"] is None
    assert x["final_checkpoint_sha256"] is None
    assert x["error"]["phase"]=="RESTORE_PREVIOUS_COMPLETE_STATE"
    assert "native capture/validation storage budget exceeded" in x["error"]["message"]
    assert x["native_process_cap_bytes"]==8*1024**3
    assert x["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
    a=x["trace_sites"]["journey_decode:source old plus one prospective decoder"]
    assert a["exceeded"]==0
    assert a["calls"]==8794570
    b=x["trace_sites"]["engine_admission:capture/validation"]
    assert b["exceeded"]==1
    assert b["max_required"]==7367599605
    assert b["limit_at_max"]==6442450944
