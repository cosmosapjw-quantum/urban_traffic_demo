"""Evidence-locked original 100k Valley resource regression under the unchanged V03 cap."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "artifacts/v03_sweep_live_bounds_20261120/C9_CROSS_BINARY_25700.json"
NEW = ROOT / "artifacts/v03_compact_lineage_20261120/C6_CROSS_BINARY_25700.json"


def read(path):
    return json.loads(path.read_bytes())


def test_current_native_roundtrips_identical_historical_25650_source_bytes():
    before, after = read(OLD), read(NEW)
    assert before["roundtrip_wire_identity"] is True
    assert after["roundtrip_wire_identity"] is True
    assert after["input_checkpoint_sha256"] == before["input_checkpoint_sha256"]
    assert after["old_driver_identity"] == after["current_driver_identity"] == before["old_driver_identity"]
    assert after["matrix_sha256"] == before["matrix_sha256"]
    assert after["current_source_dirty"] is False
    assert after["current_source_sha256"] != before["current_source_sha256"]
    assert after["current_native_binary_sha256"] != before["current_native_binary_sha256"]
    assert after["process_address_space_cap_bytes"] == before["process_address_space_cap_bytes"] == 8 * 1024**3


def test_actual_initial_retained_road_payload_savings_matches_8_bytes_per_row():
    before, after = read(OLD), read(NEW)
    old_bytes = before["trace_sites"]["engine_admission:capture"]["terms_at_max"]["road"]
    new_bytes = after["trace_sites"]["engine_admission:capture"]["terms_at_max"]["road"]
    assert old_bytes == 549766512
    assert new_bytes == 417535712
    assert old_bytes - new_bytes == 132230800
    assert before["trace_counters"]["tick.cell_parts"][2] == 16528850
    assert old_bytes - new_bytes == 8 * before["trace_counters"]["tick.cell_parts"][2]


def test_prior_first_tick_index_guard_cleared_second_tick_transfer_still_blocks():
    before, after = read(OLD), read(NEW)
    prior = before["trace_sites"]["road_work:indexed sweep preflight"]
    now = after["trace_sites"]["road_work:indexed sweep preflight"]
    assert prior["exceeded"] == 1
    assert now["exceeded"] == 0
    assert now["calls"] > prior["calls"]
    assert before["trace_sites"]["road_base:components"]["calls"] == 1
    assert after["trace_sites"]["road_base:components"]["calls"] == 2
    next_guard = after["trace_sites"]["road_work:transfer candidates"]
    assert next_guard["exceeded"] == 1
    assert next_guard["max_required"] == 5206984536
    assert next_guard["limit_at_max"] == 5206973967
    assert next_guard["max_required"] - next_guard["limit_at_max"] == 10569
    assert after["status"] == "BLOCKED_RESOURCE"
    assert "transfer candidates" in after["error"]["message"]
    assert after["completed_time_s"] is None
    assert after["final_checkpoint_sha256"] is None
    assert after["original_V03_full_day_acceptance"] == "BLOCKED_0_OF_9"
