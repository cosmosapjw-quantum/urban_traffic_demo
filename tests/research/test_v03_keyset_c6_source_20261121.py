"""Real original Valley 100k exact ordered route-keyset census evidence."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
A=ROOT/"artifacts/v03_persistent_keyset_20261121"
P=A/"C6_REAL_KEYSET_CENSUS_25680.json"
SOURCE=ROOT/"artifacts/v03_event_pages_20261121/C9_CROSS_NATIVE_25680.json"

def load(p): return json.loads(p.read_bytes())

def test_exact_real_100k_source_packet_rows_and_distinct_owner_counts():
    x=load(P);old=load(SOURCE)
    assert x["schema"]=="V03_100K_ORDERED_KEYSET_SOURCE_CENSUS_20261121_V1"
    assert x["historical_checkpoint_sha256"]==old["final_checkpoint_sha256"]
    assert x["historical_checkpoint_bytes"]==old["final_checkpoint_bytes"]
    assert x["source_time_s"]==25680.
    assert x["driver_identity"]==old["current_driver_identity"]
    assert x["matrix_sha256"]==old["original_matrix_sha256"]
    assert x["source_dirty"] is False
    assert x["process_limit_bytes"]==8*1024**3
    assert x["original_full_day_acceptance"]=="BLOCKED_0_OF_9"
    assert x["road_cell_parts"]==x["road_uniform_parts"]==25_644_407
    assert x["road_cell_packets"]==x["road_uniform_packets"]==472_127

def test_repeated_keys_are_independently_backed_not_cloned_arc_credit():
    c=load(P)["keyset_census"]
    assert c["uniform_packet_owners"]==c["distinct_uniform_backings"]==472_127
    assert c["distinct_keysets"]==47_771
    assert c["repeated_key_packets"]==424_356
    assert c["repeated_key_rows"]==23_927_302
    assert c["keyset_len_ge_8_repeat_rows"]==23_377_937
    assert c["total_uniform_rows"]==25_644_407
    assert c["potential_saved_key_payload_bytes"]==191_418_416
    assert c["potential_saved_key_payload_bytes"]==8*c["repeated_key_rows"]
    assert c["max_tag"]==304_391
    assert c["max_offset"]==20
    assert c["repeated_key_rows"]<c["total_uniform_rows"]
