"""Original fixed-100k Valley genuine native gate after keyset surgery."""
import json
from pathlib import Path

R=Path(__file__).resolve().parents[2]
ART=R/"artifacts/v03_surgical_residence_20261122"

def test_surgical_keyset_skip_clears_old_guard_but_service_finish_is_new_blocker():
    run=json.loads((ART/"R6_original_100k_25700_10s.json").read_text())
    assert run["case"]=="valley_weekday_s7"
    assert run["status"]=="BLOCKED_RESOURCE"
    assert run["current_source_dirty"] is False
    assert run["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
    assert run["start_time_s"]==run["completed_time_s"]==25700
    assert run["requested_duration_s"]==10 and run["valid_advanced_duration_s"]==0
    assert run["blocked_target_time_s"]==25710
    assert run["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert run["final_checkpoint_sha256"] is None
    assert run["native_process_cap_bytes"]==8*1024**3
    assert "phase=service finish" in run["error"]["message"]
    t=run["trace_sites"]
    assert t["road_work:transfer candidates"]["exceeded"]==0
    assert t["road_post:event candidate materialize after road"]["exceeded"]==0
    assert t["road_post:optional keyset interning estimate"]["exceeded"]==1
    assert "road_post:continuous keyset allocation" not in t
    assert t["service_sinks:service finish"]["exceeded"]==1
    assert t["service_sinks:service finish"]["max_required"]==6899566376
    assert t["service_sinks:service finish"]["limit_at_max"]==5789366871
    counters=run["trace_counters"]
    assert counters["keyset.surgical_deferred_due_to_budget"][1]==1
    assert counters["keyset.surgical_estimated_required_bytes"][1]==5533362416
