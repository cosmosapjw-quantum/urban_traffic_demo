"""Independent CLI/manifest tests: actual source bytes, geometry, typed claim gates."""
from __future__ import annotations
from dataclasses import replace
from importlib.util import module_from_spec,spec_from_file_location
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import pytest


ROOT=Path(__file__).resolve().parents[2]
CLI=ROOT/"tools/research/run_chicago_field_observations.py"
MANIFEST=ROOT/"artifacts/kcmb_field_20261119/SOURCE_MANIFEST.json"
OSM=ROOT/"artifacts/osm_control/chicago.osm"
spec=spec_from_file_location("chicago_cli_repro",CLI)
module=module_from_spec(spec)
sys.modules[spec.name]=module
assert spec.loader is not None
spec.loader.exec_module(module)


def test_real_source_hashes_and_repeatable_field_math_without_network():
    data=module.run(root=ROOT,manifest_path=MANIFEST,osm_path=OSM)
    assert data["actual_public_observation_input"]
    assert data["source_valid_counts"]=={"calibration":12,"holdout":12}
    assert data["source_missing_exclusions"]==[]
    assert data["model_prediction_boundary"]=="EQUILIBRIUM_COMPATIBLE_SCALAR_BASELINE_ONLY"
    assert data["empirical_KCMB_runtime_validation"]=="NOT_EXECUTED"
    assert "vehicle" in " ".join(data["not_observed"])
    score=data["speed_only_field_metrics"]
    assert score["flow_geh"] is None
    assert score["equilibrium_baseline_holdout_rmse_mps"]==pytest.approx(.5215466666666664)
    assert score["time_bin_template_holdout_rmse_mps"]==pytest.approx(1.0719642620908587)
    assert score["shared_clock_bins"]==12
    geo=data["map_match"]
    assert geo["status"]=="CANDIDATE_OSM_NAMED_WAY_MATCH_NOT_LANE_CERTIFIED"
    assert geo["osm_oneway_verified"] is False
    assert geo["lane_pocket_geometry_verified"] is False
    assert geo["path_length_m"]==pytest.approx(836.6190502420699,abs=2e-7)
    assert geo["start_offset_m"]<30 and geo["end_offset_m"]<30
    for split,row in data["source_evidence"].items():
        source=ROOT/row["source_file"]
        assert hashlib.sha256(source.read_bytes()).hexdigest()==row["original_json_sha256"]
        assert row["rows"]==12


def test_cli_writes_complete_json_without_synthetic_flow_or_calibrated_kinetics(tmp_path):
    output=tmp_path/"field_result.json"
    process=subprocess.run(
        [sys.executable,str(CLI),"--output",str(output)],
        cwd=ROOT,capture_output=True,text=True,timeout=20,
    )
    assert process.returncode==0,process.stderr
    receipt=json.loads(output.read_text())
    assert receipt["speed_only_field_metrics"]["flow_geh"] is None
    assert receipt["empirical_KCMB_runtime_validation"]=="NOT_EXECUTED"
    assert receipt["source_segment"]["segment_id"]=="1221"
    assert len(receipt["map_match"]["node_path"])>10
    assert receipt["map_match"]["lane_pocket_geometry_verified"] is False
    assert receipt["source_valid_counts"]["holdout"]==12


def test_frozen_raw_source_bit_flip_in_manifest_is_refused_even_if_json_valid(tmp_path):
    manifest=json.loads(MANIFEST.read_text())
    manifest["source_requests"][0]["sha256"]="0"*64
    corrupted=tmp_path/"wrong_hash.json"
    corrupted.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match="SHA256 mismatch"):
        module.run(root=ROOT,manifest_path=corrupted,osm_path=OSM)


def test_missing_split_duplicate_split_and_wrong_dataset_rejected(tmp_path):
    source=json.loads(MANIFEST.read_text())
    for name,change in (
       ("same",lambda m:m["source_requests"][1].update(
           {"split":"calibration"})),
       ("wrongsource",lambda m:m.update({"dataset_id":"other"})),
       ("wrongsite",lambda m:m.update({"street":"imaginary"})),
       ("unsafe",lambda m:m["source_requests"][1].update(
           {"file":"../../somewhere.json"})),
    ):
        x=json.loads(json.dumps(source))
        change(x)
        manifest=tmp_path/(name+".json")
        manifest.write_text(json.dumps(x))
        with pytest.raises((ValueError,FileNotFoundError)):
            module.run(root=ROOT,manifest_path=manifest,osm_path=OSM)


def test_real_observation_has_no_traffic_vehicle_count_and_day_shift_provenance():
    result=module.run(root=ROOT,manifest_path=MANIFEST,osm_path=OSM)
    score=result["speed_only_field_metrics"]
    assert score["calibration_day"]=="2026-04-20"
    assert score["holdout_day"]=="2026-04-27"
    assert score["source_probe_counts_are_vehicle_counts"] is False
    assert score["physical_model_class_parameters_identified"] is False
    assert score["source_uncertainty"]=="single_holdout_day_correlated_bins"
