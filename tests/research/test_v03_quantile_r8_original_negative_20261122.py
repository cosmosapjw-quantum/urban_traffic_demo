"""Real original 100k Valley R8 physical resource guard advancement evidence."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_quantile_sweep_20261122"

def test_r8_original_100k_passed_indexed_and_then_blocked_cell_packet():
    old=json.loads((ART/"R6_original_100k_25710_off_20s.json").read_bytes())
    new=json.loads((ART/"R8_original_100k_25710_off_20s.json").read_bytes())
    assert (old["case"],new["case"])==("valley_weekday_s7",)*2
    assert old["error"]["phase"]==new["error"]["phase"]=="ADVANCE_TO_25720"
    assert "phase=indexed sweep preflight" in old["error"]["message"]
    assert "phase=cell packet reservation" in new["error"]["message"]
    assert "required_bytes=4998771080" in new["error"]["message"]
    assert "budget_bytes=4952574903" in new["error"]["message"]
    assert new["status"]=="BLOCKED_RESOURCE"
    assert new["requested_duration_s"]==20
    assert new["valid_advanced_duration_s"]==0
    assert new["start_time_s"]==new["completed_time_s"]==25710
    assert new["blocked_target_time_s"]==25720
    assert new["final_checkpoint_sha256"] is None
    assert new["previous_checkpoint_full_wire_roundtrip_exact"] is True
    assert new["previous_mass_ledger"] is not None
    assert new["native_process_cap_bytes"]==8*1024**3
    assert new["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
    assert new["current_source_dirty"] is False
    assert new["trace_mode"]=="off"
    assert new["current_candidate_source_sha256"]=="98468784c448b457e3a95616222d703f48e2b67be957a8391fff3eedbe435830"
    assert new["current_native_binary_sha256"]=="18200af89a683428849b84bea831b8214c23756b412e1ec14223f831c8ecf182"
