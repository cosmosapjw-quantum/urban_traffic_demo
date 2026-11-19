"""Hard original-V03 100k physical checkpoint equivalence, no release substitution."""
from pathlib import Path
import hashlib
import json

import pytest
from metroflow.v1.native_engine import native_binary_provenance
from metroflow.v1.v03_readiness import assess_v03_readiness


ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/"artifacts/kcmb_v03_physics_20261119/prefix/valley_weekday_s7.native_fresh_25300.json"
NEW=ROOT/"artifacts/v03_fifo_interval_sweep_20261119/prefix/valley_weekday_s7.native_sweep_25300.json"
NEW_BINARY=ROOT/"artifacts/v03_fifo_interval_sweep_20261119/prefix/valley_weekday_s7.native_sweep_25300.final.bin"
PREP=ROOT/"artifacts/v03_fifo_interval_sweep_20261119/preparation"


def test_original_whole_native_physics_checkpoint_is_byte_identical_at_25300():
    reference=json.loads(OLD.read_bytes())
    candidate=json.loads(NEW.read_bytes())
    assert reference["status"]=="EXECUTED_FOR_REVIEW"
    assert candidate["status"]=="EXECUTED_FOR_REVIEW"
    assert reference["simulated_s"]==candidate["simulated_s"]==25300
    assert reference["report"]["calendar"]==candidate["report"]["calendar"]
    assert reference["report"]["execution"]["ledger"]==candidate["report"]["execution"]["ledger"]
    assert reference["driver_identity"]==candidate["driver_identity"]
    assert reference["matrix_sha256"]==candidate["matrix_sha256"]
    assert reference["source_sha256"]==candidate["source_sha256"]
    # Original physical source/matrix/driver remain identical, but the
    # intentionally edited Rust kernel has a DISTINCT candidate source hash
    # and distinct compiled native binary identity. Requiring source-hash
    # equality would confuse byte-identical physical states with byte-identical
    # executable source versions.
    assert reference["candidate_source_sha256"]!=candidate["candidate_source_sha256"]
    assert len(candidate["candidate_source_sha256"])==64
    assert candidate["native_binary_sha256"] != reference["native_binary_sha256"]
    assert candidate["native_binary_sha256"]==native_binary_provenance()["sha256"]
    expected="7bcbd4e7eb04d8e0014524fa815a29c56b7873c5f3bb12c37a231caa648f32e1"
    assert candidate["final_checkpoint_sha256"]==reference["final_checkpoint_sha256"]==expected
    assert hashlib.sha256(NEW_BINARY.read_bytes()).hexdigest()==expected
    assert candidate["peak_rss_bytes"]<8*1024**3
    assert candidate["wall_s"]<7200
    assert candidate["report"]["execution"]["ledger"]["vehicles"]["requested"]>0
    assert candidate["report"]["execution"]["ledger"]["vehicles"]["released"]>0


def test_same_new_native_source_all_original_three_city_calendars_prepared():
    matrix_bytes=(ROOT/"scenarios/v1/release_matrix.json").read_bytes()
    matrix=json.loads(matrix_bytes)
    plan=json.loads((ROOT/"docs/v1/PLAN.json").read_bytes())
    rows=[]
    for city in matrix["cases"]:
        file=PREP/(city["id"]+".prepare.json")
        item=json.loads(file.read_bytes())
        assert item["calendar"]["resident_stock"]==100000
        assert item["status"]=="WHOLE_CALENDAR_PREPARED"
        rows.append(item)
    info=assess_v03_readiness(
        plan,matrix,
        matrix_sha256=hashlib.sha256(matrix_bytes).hexdigest(),
        preparation_receipts=rows,
        live_native_binary_sha256=native_binary_provenance()["sha256"],
    )
    assert info["v03"]["calendar_preparation_verified"]==3
    assert info["v03"]["completed_full_day_runs"]==0
    assert info["v03"]["required_full_day_runs"]==9
    assert info["dag"]["completed"]==19
    assert info["dag"]["total"]==21


def test_bounded_sweep_checkpoint_continuation_target_contract():
    from tools.research.continue_original_v03_prefix import bounded_sweep_target_seconds
    assert bounded_sweep_target_seconds(25300.,25600.,86400.)==25600.
    for end in (25300.,25610.,86400.,25555.,float("nan")):
        with pytest.raises(ValueError,match="bounded|prefix|target"):
            bounded_sweep_target_seconds(25300.,end,86400.)


def test_original_25600_congested_prefix_matches_optimized_binary_bit_for_bit():
    import json
    path=ROOT/"artifacts/v03_fifo_interval_sweep_20261119/OLD_VS_SWEEP_25600.json"
    case=json.loads(path.read_bytes())
    assert case["status"]=="BIT_IDENTICAL_CONGESTED_PREFIX"
    assert case["reference_start_time_s"]==25300.
    assert case["reference_end_time_s"]==25600.
    assert case["whole_city_100k_population_preserved"] is True
    assert case["original_full_day_accepted"] is False
    assert case["native_old_sha256"] != case["native_candidate_sha256"]
    assert case["driver_identity"]==json.loads(NEW.read_bytes())["driver_identity"]
    assert case["byte_identical_native_checkpoint"] is True
    assert case["physical_ledger_exact_equal"] is True
    assert case["old_reference_output_checkpoint_sha256"]==case["new_sweep_checkpoint_sha256"]
    assert case["old_reference_checkpoint_bytes"]==case["new_sweep_checkpoint_bytes"]
    assert case["old_original_peak_rss_bytes"]<8*1024**3
    assert case["new_candidate_peak_rss_bytes"]<8*1024**3
