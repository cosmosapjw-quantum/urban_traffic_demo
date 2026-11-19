"""Actual KCMB time stepping against real speed-proxy holdout, scoped scenarios."""
from __future__ import annotations

from importlib.util import module_from_spec,spec_from_file_location
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest


ROOT=Path(__file__).resolve().parents[2]
CLI=ROOT/"tools/research/run_kcmb_probe_field_scenarios.py"
SPEC=spec_from_file_location("kcmb_probe_scenarios_tested",CLI)
MOD=module_from_spec(SPEC)
sys.modules[SPEC.name]=MOD
assert SPEC.loader is not None
SPEC.loader.exec_module(MOD)


def test_real_observation_conditional_model_is_executed_not_just_equilibrium_formula():
    data=MOD.run_probe_scenarios(ROOT,backends=("python",))
    assert data["actual_chicago_source_input"] is True
    assert data["real_KCMB_runtime_executed"] is True
    assert data["physical_parameter_identifiability"]=="NOT_IDENTIFIED_FROM_CTA_SPEED_ONLY"
    assert data["city_observation_mechanism"]=="UNKNOWN_NOT_CLAIMED_AFFINE"
    assert data["valid_holdout_speed_rows"]==12
    py=data["backend_results"]["python"]
    assert py["steps_executed"]==960
    assert py["warmup_steps"]==240 and py["forecast_steps"]==720
    assert py["all_class_mass_ledger_max_error_veh"] < 1e-8
    assert py["source_veh_by_class"][0] >= 2000.
    assert py["bus_population_assumed_not_observed"] is True
    assert py["conditional_scenario_parameters"]["source_vehicle_equivalents_per_s"] == .3
    assert py["conditional_scenario_parameters"]["vmax_mps"]==pytest.approx(30*.44704)
    assert py["conditional_scenario_parameters"]["p_calibration"] == pytest.approx(17.8333333333333/30)
    assert py["kinetic_bulk_speed_after_warmup_mps"]==pytest.approx(
        data["field_calibration_mean_mps"],abs=1e-10)
    assert py["transport_variance_u_after_warmup"] >0
    assert py["transport_variance_u_after_warmup"] < py["local_stationary_variance_u"]


def test_each_affine_probe_selection_produces_distinct_falsifiable_holdout_curve():
    row=MOD.run_probe_scenarios(ROOT,backends=("python",))["backend_results"]["python"]
    hypotheses=row["selection_hypotheses"]
    assert set(hypotheses)=={"unweighted","speed_upweighted","speed_downweighted"}
    for key in hypotheses:
        h=hypotheses[key]
        assert len(h["predicted_speed_mps_by_clock_slot"])==12
        assert h["holdout_rmse_mps"]>=0
        assert h["holdout_mae_mps"]>=0
        assert 0<min(h["predicted_speed_mps_by_clock_slot"])
        assert max(h["predicted_speed_mps_by_clock_slot"])<30*.44704
    u=hypotheses["unweighted"]
    up=hypotheses["speed_upweighted"]
    down=hypotheses["speed_downweighted"]
    assert down["predicted_speed_mps_by_clock_slot"][0] < u["predicted_speed_mps_by_clock_slot"][0]
    assert u["predicted_speed_mps_by_clock_slot"][0] < up["predicted_speed_mps_by_clock_slot"][0]
    assert u["holdout_rmse_mps"]==pytest.approx(.5215466666666664,abs=2e-9)
    assert up["holdout_rmse_mps"] > u["holdout_rmse_mps"]
    assert down["holdout_rmse_mps"] > u["holdout_rmse_mps"]
    assert row["local_stationary_variance_u"] == pytest.approx(
        row["conditional_scenario_parameters"]["p_calibration"]*
        (1-row["conditional_scenario_parameters"]["p_calibration"])/
        (1+.5*3),abs=1e-12)


def test_python_and_rust_execute_same_physical_scenario_with_numeric_parity():
    report=MOD.run_probe_scenarios(ROOT)
    a=report["backend_results"]["python"]
    b=report["backend_results"]["rust"]
    for key in ("kinetic_bulk_speed_after_warmup_mps",
                "transport_variance_u_after_warmup",
                "local_stationary_variance_u"):
        assert a[key]==pytest.approx(b[key],abs=5e-11)
    assert a["mass_active_end_veh"]==pytest.approx(b["mass_active_end_veh"],abs=1e-8)
    for name in ("unweighted","speed_upweighted","speed_downweighted"):
        aa=a["selection_hypotheses"][name]
        bb=b["selection_hypotheses"][name]
        assert aa["holdout_rmse_mps"]==pytest.approx(bb["holdout_rmse_mps"],abs=5e-10)
        assert aa["predicted_speed_mps_by_clock_slot"]==pytest.approx(
            bb["predicted_speed_mps_by_clock_slot"],abs=5e-10)
    assert report["real_KCMB_runtime_executed"]
    assert report["not_measured"].count("true road vehicle counts")==1


def test_full_cli_produces_json_with_grounded_flags_and_actual_source_sha(tmp_path):
    file=tmp_path/"field_probe_run.json"
    done=subprocess.run([sys.executable,str(CLI),"--backend","python",
                         "--output",str(file)],
        cwd=ROOT,check=False,capture_output=True,text=True,timeout=40)
    assert done.returncode==0,done.stderr
    result=json.loads(file.read_text())
    assert result["actual_chicago_source_input"] is True
    assert result["real_KCMB_runtime_executed"] is True
    assert len(result["field_source_sha256"])==2
    assert all(len(v)==64 for v in result["field_source_sha256"].values())
    assert result["field_holdout_day"]=="2026-04-27"
    assert set(result["backend_results"])=={"python"}
    assert result["city_observation_mechanism"]=="UNKNOWN_NOT_CLAIMED_AFFINE"


def test_invalid_backend_and_nonreplicable_source_are_refused(tmp_path):
    with pytest.raises(ValueError,match="backend"):
        MOD.run_probe_scenarios(ROOT,backends=("invalid",))
    with pytest.raises((ValueError,FileNotFoundError)):
        MOD.run_probe_scenarios(tmp_path,backends=("python",))
