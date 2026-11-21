"""Current-native original Valley 100k exact 80s requested, only 40s admitted."""
import json
import math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HORIZON=ROOT/"artifacts/v03_fifo_closure_20261121/C9_ORIGINAL_100K_REQUESTED_80S.json"
OLD=ROOT/"artifacts/v03_persistent_keyset_20261121/C8_KEYSET_CROSS_BINARY_25690.json"
NEW=ROOT/"artifacts/v03_fifo_closure_20261121/C8_ORIGINAL_100K_25710.json"

def read(path):return json.loads(path.read_bytes())

def test_actual_original_100k_80s_horizon_has_only_four_valid_contiguous_ticks():
    h=read(HORIZON);old=read(OLD)
    assert h["status"]=="BLOCKED_RESOURCE_WITH_VALID_PREFIX"
    assert h["start_time_s"]==25650.
    assert h["requested_duration_s"]==80
    assert h["valid_advanced_duration_s"]==40.
    assert h["completed_time_s"]==25690.
    assert h["blocked_target_time_s"]==25700.
    assert h["previous_checkpoint_cross_native"] is True
    assert h["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert h["original_candidate_from_time_zero_verified"] is False
    assert h["native_process_cap_bytes"]==8*1024**3
    assert h["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
    steps=h["completed_step_wall_s"]
    assert [s["completed_time_s"] for s in steps]==[25660.,25670.,25680.,25690.]
    assert all(s["wall_s"]>0 and math.isfinite(s["wall_s"]) for s in steps)
    assert steps[0]["wall_s"]<steps[1]["wall_s"]<steps[2]["wall_s"]<steps[3]["wall_s"]
    assert h["wall_total_including_full_preparation_and_checkpoint_io_s"]>sum(
        s["wall_s"] for s in steps)
    assert h["peak_rss_bytes"]<8*1024**3
    assert h["final_checkpoint_bytes"]==old["final_checkpoint_bytes"]==2_949_231_402
    assert h["final_checkpoint_sha256"]==old["final_checkpoint_sha256"]
    assert h["completed_mass_ledger"]==old["completed_mass_ledger"]

def test_new_original_native_cross_call_arc_identity_did_not_use_experimental_budget():
    h=read(HORIZON);a=read(NEW)
    assert h["current_candidate_source_sha256"]==a["current_candidate_source_sha256"]
    assert h["current_native_binary_sha256"]==a["current_native_binary_sha256"]
    assert h["current_source_dirty"] is False
    assert h["trace_counters"]["arc.default_pointer_verified_credit"][0]==5
    assert h["trace_counters"]["arc.default_pointer_verified_credit"][1]==1_907_272_192
    assert h["trace_counters"]["arc.experimental_paired_credit"]==[5,0,0]
    assert h["error"]["class"]=="BudgetExceeded"
    assert h["error"]["phase"]=="ADVANCE_TO_25700"
    assert "capture/validation" in h["error"]["message"]
    assert "required_bytes=6485573501" in h["error"]["message"]
    assert "budget_bytes=6442450944" in h["error"]["message"]
    assert h["final_checkpoint_sha256"] is not None
