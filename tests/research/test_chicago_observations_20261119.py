"""Independent tests for actual Chicago speed observations and model admissibility."""
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
import json
import math
import statistics

import pytest

from metroflow.v1.chicago_observations import (
    ChicagoSegment,
    parse_observation_days,
    evaluate_speed_only,
    match_named_osm_path,
)


ROOT=Path(__file__).resolve().parents[2]
SOURCES=ROOT/"artifacts/kcmb_field_20261119/raw"


def actual_rows():
    return tuple(json.loads((SOURCES/(day+".json")).read_bytes()) for day in ("2026-04-20","2026-04-27"))


def test_true_field_rows_with_identical_site_and_clock_have_no_split_leakage():
    train,hold=actual_rows()
    out=parse_observation_days(train,hold)
    assert len(out.calibration)==12 and len(out.holdout)==12
    assert out.segment.segment_id=="1221"
    assert out.segment.direction=="NB"
    assert out.segment.street=="Halsted"
    assert out.segment.from_street=="Harrison"
    assert out.segment.to_street=="Madison"
    assert out.segment.length_m==pytest.approx(.52*1609.344,abs=1e-9)
    assert tuple(x.slot for x in out.calibration)==tuple(range(42,54))
    assert tuple(x.slot for x in out.holdout)==tuple(range(42,54))
    assert tuple(x.day for x in out.calibration)==("2026-04-20",)*12
    assert tuple(x.day for x in out.holdout)==("2026-04-27",)*12
    assert out.excluded_rows==()


def test_speed_only_equilibrium_compatible_calibration_and_genuine_day_holdout():
    obs=parse_observation_days(*actual_rows())
    metrics=evaluate_speed_only(obs)
    assert metrics["status"]=="REAL_FIELD_SPEED_ONLY_SCORED"
    assert metrics["observable"]=="CTA_GPS_ESTIMATED_SEGMENT_SPEED"
    assert metrics["calibration_day"]=="2026-04-20"
    assert metrics["holdout_day"]=="2026-04-27"
    assert metrics["shared_clock_bins"]==12
    assert metrics["calibration_speed_mean_mps"]==pytest.approx((214/12)*.44704)
    assert metrics["holdout_speed_mean_mps"]==pytest.approx((219/12)*.44704)
    assert metrics["equilibrium_baseline_holdout_rmse_mps"]==pytest.approx(.5215466666666669)
    assert metrics["equilibrium_baseline_holdout_mae_mps"]==pytest.approx(.3725333333333336)
    assert metrics["time_bin_template_holdout_rmse_mps"]==pytest.approx(1.071964262090859)
    assert metrics["calibration_holdout_speed_w1_mps"]==pytest.approx(.33528)
    assert metrics["flow_geh"] is None
    assert metrics["physical_model_class_parameters_identified"] is False
    assert metrics["source_uncertainty"]=="single_holdout_day_correlated_bins"
    assert "vehicle" not in metrics["observable"].lower()


def test_invalid_speed_sentinel_is_recorded_as_missing_not_negative_physics():
    train,hold=actual_rows()
    hold[3]["speed"]="-1"
    obs=parse_observation_days(train,hold)
    assert len(obs.holdout)==11
    assert len(obs.excluded_rows)==1
    assert obs.excluded_rows[0].reason=="NO_SPEED_ESTIMATE"
    assert obs.excluded_rows[0].split=="holdout"
    metrics=evaluate_speed_only(obs)
    assert metrics["shared_clock_bins"]==11
    assert metrics["flow_geh"] is None


def test_probe_count_not_vehicle_flow_and_zero_probe_exclusion():
    train,hold=actual_rows()
    hold[0]["bus_count"]="0"
    hold[0]["message_count"]="0"
    obs=parse_observation_days(train,hold)
    assert obs.excluded_rows[0].reason=="NO_PROBE_SUPPORT"
    assert all(x.speed_mps>=0 for x in obs.calibration+obs.holdout)
    metrics=evaluate_speed_only(obs)
    assert metrics["shared_clock_bins"]==11
    assert "observed_count_veh" not in metrics
    assert metrics["flow_geh"] is None


def test_duplicates_bad_time_wrong_site_direction_and_cross_day_leakage_are_rejected():
    train,hold=actual_rows()
    with pytest.raises(ValueError,match="duplicate|slot"):
        parse_observation_days(train+[train[0].copy()],hold)
    with pytest.raises(ValueError,match="overlap|date|split"):
        parse_observation_days(train,hold,holdout_day="2026-04-20")
    hold[0]["segment_id"]="9999"
    with pytest.raises(ValueError,match="segment|identity"):
        parse_observation_days(train,hold)
    hold[0]["segment_id"]="1221"
    hold[0]["direction"]="SB"
    with pytest.raises(ValueError,match="direction|identity"):
        parse_observation_days(train,hold)
    hold[0]["direction"]="NB"
    hold[0]["time"]="2026-04-27T09:01:00.000"
    with pytest.raises(ValueError,match="window|clock"):
        parse_observation_days(train,hold)


def test_timezone_naive_sample_rejected_if_changed_into_an_unproven_utc_offset():
    train,hold=actual_rows()
    hold[0]["time"]="2026-04-27T07:01:22-05:00"
    with pytest.raises(ValueError,match="timezone|offset"):
        parse_observation_days(train,hold)


def test_negative_other_than_minus_one_is_bad_source_not_missing_signal():
    train,hold=actual_rows()
    train[0]["speed"]="-2"
    with pytest.raises(ValueError,match="negative|speed"):
        parse_observation_days(train,hold)


def test_actual_historical_segment_geo_matches_connected_named_osm_candidate():
    actual=parse_observation_days(*actual_rows())
    osm=(ROOT/"artifacts/osm_control/chicago.osm").read_bytes()
    match=match_named_osm_path(osm,actual.segment,street_token="Halsted")
    assert match.start_offset_m < 30.
    assert match.end_offset_m < 30.
    assert abs(match.relative_length_error)<.1
    assert match.path_length_m==pytest.approx(836.86,abs=20)
    assert len(match.node_path)>=2
    assert match.osm_oneway_verified is False
    assert match.lane_pocket_geometry_verified is False


def test_geographic_candidate_refuses_disconnected_or_wrong_name_or_endpoints():
    observation=parse_observation_days(*actual_rows())
    osm=(ROOT/"artifacts/osm_control/chicago.osm").read_bytes()
    with pytest.raises(ValueError,match="street|path|match"):
        match_named_osm_path(osm,observation.segment,street_token="ImaginaryNeverRoad")
    bad=replace(observation.segment,end_lat=42.7)
    with pytest.raises(ValueError,match="distance|endpoint|match"):
        match_named_osm_path(osm,bad,street_token="Halsted")
    with pytest.raises(ValueError,match="length|match"):
        match_named_osm_path(osm,replace(observation.segment,length_m=10000.),street_token="Halsted")
    with pytest.raises(ValueError,match="direction"):
        match_named_osm_path(osm,replace(observation.segment,direction="SB"),street_token="Halsted")


def test_kinetic_speed_equilibrium_parameter_nonidentifiability_is_constructive():
    mu=(214/12)*.44704
    for u in (mu,mu*1.2,mu*2.):
        for k in (.01,1.,10.):
            a=k*mu/u
            nu=k*(1-mu/u)
            for tau in (.1,10.):
                equilibrium=u*a/(a+nu)
                assert equilibrium==pytest.approx(mu,abs=1e-12)
