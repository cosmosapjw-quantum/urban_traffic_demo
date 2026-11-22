"""Preserve the actual second 100k service-gate failure and its required correction."""
import json
from pathlib import Path

ART=Path(__file__).resolve().parents[2]/"artifacts/v03_surgical_residence_20261122"
def test_concrete_road_owner_only_surgery_still_double_counts_shared_arc_event():
    x=json.loads((ART/"R8_original_100k_25700_10s.json").read_text())
    assert x["case"]=="valley_weekday_s7"
    assert x["status"]=="BLOCKED_RESOURCE"
    assert x["current_source_dirty"] is False
    assert x["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert x["start_time_s"]==x["completed_time_s"]==25700
    assert x["requested_duration_s"]==10 and x["valid_advanced_duration_s"]==0
    assert x["blocked_target_time_s"]==25710
    assert x["final_checkpoint_sha256"] is None
    assert "phase=service finish" in x["error"]["message"]
    assert x["trace_sites"]["road_work:transfer candidates"]["exceeded"]==0
    assert x["trace_sites"]["road_post:event candidate materialize after road"]["exceeded"]==0
    assert x["trace_sites"]["road_post:optional keyset interning estimate"]["exceeded"]==1
    site=x["trace_sites"]["service_sinks:service finish"]
    assert site["exceeded"]==1
    assert site["max_required"]==6021458856
    assert site["limit_at_max"]==5789366871
