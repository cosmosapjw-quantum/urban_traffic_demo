"""Current diagnostic native source 100k complete-calendar preparation, no 24h claim."""
import hashlib
import json
from pathlib import Path
from tools.run_v1_local_acceptance import candidate_provenance
from metroflow.v1.native_engine import native_binary_provenance

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_fifo_unique_accounting_20261120"


def test_current_native_original_all_three_city_whole_calendars_not_simulated_days():
    r=json.loads((ART/"C6_SOURCE_PINNED_V03_READINESS.json").read_bytes())
    src="5fab49213d660b069866b3a4c0fa296657237dc1c2645f14e75802bf31c06d32"
    bin="57b7ac3104adce4ba0bf68f09ff9bc62e9996a3255ea65f4e369329e92ec5c31"
    # C6 is a preserved former compiled binary, not current C9.
    assert r["measurement_context"]["live_candidate_source_sha256"]==src
    assert r["measurement_context"]["live_native_binary_sha256"]==bin
    assert src!=candidate_provenance()["source_sha256"]
    assert bin!=native_binary_provenance()["sha256"]
    assert r["v03"]["calendar_preparation_verified"]==3
    assert r["v03"]["completed_full_day_runs"]==0
    assert r["v03"]["required_full_day_runs"]==9
    assert r["v03"]["status"]=="BLOCKED"
    assert r["dag"]["completed"]==19 and r["dag"]["total"]==21
    names={"river_weekday_s17":5093765,"coastal_weekend_s41":2449750,
           "valley_weekday_s7":918450}
    total=0
    for case,legs in names.items():
        receipt_file=ART/"C6_preparation"/(case+".prepare.json")
        item=json.loads(receipt_file.read_bytes())
        assert item["status"]=="WHOLE_CALENDAR_PREPARED"
        assert item["calendar"]["resident_stock"]==100000
        assert item["calendar"]["legs"]==legs
        assert item["candidate_source_sha256"]==src
        assert item["native_binary_sha256"]==bin
        assert item["horizon_s"]==item["simulated_s"]==0
        assert item["peak_rss_bytes"]<8*1024**3
        assert item["wall_s"]<7200
        total+=legs
    assert total==8461965
