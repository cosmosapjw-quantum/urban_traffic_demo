"""Real original Valley 100k negative checkpoint decoder admission evidence."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
def test_exact_t25710_replay_exposes_new_decoder_headroom_not_road_physics():
    d=json.loads((ROOT/"artifacts/v03_variance_restart_20261122"/
                  "R6_original_100k_25710_requested_20s.json").read_bytes())
    assert d["case"]=="valley_weekday_s7"
    assert d["cross_native_original_25710_source"] is True
    assert d["status"]=="ERROR"
    assert d["start_time_s"]==25710 and d["requested_duration_s"]==20
    assert d["error"]["phase"]=="RESTORE_PREVIOUS_COMPLETE_STATE"
    assert "native journey source decoder storage budget exceeded" in d["error"]["message"]
    assert d["valid_advanced_duration_s"] is None
    assert d["final_checkpoint_sha256"] is None
    assert d["current_source_dirty"] is False
    assert d["native_process_cap_bytes"]==8*1024**3
    assert d["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
    x=d["trace_sites"]["journey_decode:source old plus one prospective decoder"]
    assert x["calls"]==6881080
    assert x["exceeded"]==1
    assert x["max_required"]==226233264
    assert x["limit_at_max"]==226233207
    assert x["terms_at_max"]["prospective_one_decoder"]==226167728
    assert x["terms_at_max"]["retained_old_journey"]==0
