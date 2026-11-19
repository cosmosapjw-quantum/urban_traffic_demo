#!/usr/bin/env python3
"""Offline reproducible Chicago Speed Only observation result.

This is a *field observed speed baseline and OSM road candidate*, not a KCMB
network simulation, vehicle-flow observation, or real lane FIFO validation.
Every original source JSON is checked byte-for-byte against its frozen hash.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import resource
import time

from metroflow.v1.chicago_observations import (
    parse_observation_days, evaluate_speed_only, match_named_osm_path,
)


def run(*, root: Path, manifest_path: Path, osm_path: Path) -> dict:
    start=time.perf_counter_ns()
    manifest=json.loads(manifest_path.read_bytes())
    if manifest.get("dataset_id")!="4g9f-3jbs" or manifest.get("segment_id")!="1221":
        raise ValueError("unsupported historical field-source dataset/segment identity")
    sources=manifest.get("source_requests")
    if not isinstance(sources,list) or len(sources)!=2:
        raise ValueError("exactly two real source-date records required")
    by_split={}
    evidence={}
    for item in sources:
        if item.get("split") not in ("calibration","holdout"):
            raise ValueError("unrecognized source split")
        split=item["split"]
        if split in by_split:
            raise ValueError("duplicate calibration/holdout source split")
        relative=Path(item["file"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("source data file must be inside the checked-out repository")
        raw_file=(root/relative).resolve()
        if not raw_file.is_relative_to(root.resolve()):
            raise ValueError("source path leaves project root")
        raw=raw_file.read_bytes()
        digest=hashlib.sha256(raw).hexdigest()
        if digest!=item.get("sha256"):
            raise ValueError(f"source raw SHA256 mismatch for {split}")
        rows=json.loads(raw)
        if len(rows)!=item.get("rows"):
            raise ValueError("source row count mismatch")
        by_split[split]=(item["date_local"],rows)
        evidence[split]={
            "date_local":item["date_local"],
            "url":item["url"],
            "original_json_sha256":digest,
            "source_file":str(relative),
            "rows":len(rows),
        }
    if set(by_split)!={"calibration","holdout"}:
        raise ValueError("missing or duplicate data split")
    cal_day,cal_rows=by_split["calibration"]
    hold_day,hold_rows=by_split["holdout"]
    data=parse_observation_days(
        cal_rows,hold_rows,calibration_day=cal_day,
        holdout_day=hold_day,segment_id=manifest["segment_id"]
    )
    obs=asdict(data.segment)
    for expected,actual in (
        ("street",data.segment.street),
        ("direction",data.segment.direction),
        ("from_street",data.segment.from_street),
        ("to_street",data.segment.to_street),
    ):
        if str(manifest[expected])!=actual:
            raise ValueError("source segment identity differs from frozen manifest")
    osm=osm_path.read_bytes()
    match=match_named_osm_path(osm,data.segment,street_token=data.segment.street)
    metrics=evaluate_speed_only(data)
    end=time.perf_counter_ns()
    return {
        "schema":"KCMB_FIELD_SPEED_ONLY_20261119_V1",
        "source":"City of Chicago Traffic Tracker historical CTA-probe speed estimates",
        "actual_public_observation_input":True,
        "data_origin":manifest["official_landing"],
        "source_evidence":evidence,
        "source_segment":obs,
        "calibration_datetime_semantics":"timezone-naive Chicago local calendar clock",
        "observed_speed_unit":"m/s; original values mph converted exactly by factor 0.44704",
        "source_missing_exclusions":[asdict(a) for a in data.excluded_rows],
        "source_valid_counts":{
            "calibration":len(data.calibration),
            "holdout":len(data.holdout),
        },
        "map_match":{
            **asdict(match),
            "source_osm_fixture":str(osm_path.relative_to(root)),
            "osm_fixture_sha256":hashlib.sha256(osm).hexdigest(),
            "status":"CANDIDATE_OSM_NAMED_WAY_MATCH_NOT_LANE_CERTIFIED",
        },
        "speed_only_field_metrics":metrics,
        "model_prediction_boundary":"EQUILIBRIUM_COMPATIBLE_SCALAR_BASELINE_ONLY",
        "not_observed":[
            "traffic vehicle flow / GEH",
            "turn-pocket geometry",
            "road signal phases",
            "individual headways or per-vehicle speed traces",
            "class-specific KCMB transition rates or relaxation time",
        ],
        "empirical_KCMB_runtime_validation":"NOT_EXECUTED",
        "compute":{
            "elapsed_seconds":(end-start)/1e9,
            "max_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "python_version":platform.python_version(),
        },
    }


def main() -> None:
    repo=Path(__file__).resolve().parents[2]
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest",default="artifacts/kcmb_field_20261119/SOURCE_MANIFEST.json")
    ap.add_argument("--osm",default="artifacts/osm_control/chicago.osm")
    ap.add_argument("--output",required=True)
    args=ap.parse_args()
    def path(x):
        f=Path(x)
        return f if f.is_absolute() else repo/f
    result=run(root=repo,manifest_path=path(args.manifest),osm_path=path(args.osm))
    output=path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    score=result["speed_only_field_metrics"]
    geom=result["map_match"]
    print(json.dumps({
        "status":score["status"],
        "real_calibration_rows":result["source_valid_counts"]["calibration"],
        "real_holdout_rows":result["source_valid_counts"]["holdout"],
        "equilibrium_baseline_holdout_rmse_mps":score["equilibrium_baseline_holdout_rmse_mps"],
        "template_holdout_rmse_mps":score["time_bin_template_holdout_rmse_mps"],
        "osm_path_length_m":geom["path_length_m"],
        "osm_start_end_gap_m":[geom["start_offset_m"],geom["end_offset_m"]],
        "actual_KCMB_simulation":"NOT_EXECUTED",
    },sort_keys=True))


if __name__=="__main__":
    main()
