#!/usr/bin/env python3
"""Standalone, field-observation comparator. No real observations are bundled.

Input rows must ALREADY be aligned in site, direction, time window, and vehicle
definition. This tool scores paired samples only; it cannot verify spatial
map-matching, observational representativeness, or model calibration.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import json
import math
from pathlib import Path


SCHEMA=(
    "site_id","split","start_s","end_s",
    "observed_count_veh","simulated_count_veh",
    "observed_mean_speed_mps","simulated_mean_speed_mps",
)


def _float(row,name):
    try:
        value=float(row[name])
    except (KeyError,TypeError,ValueError) as exc:
        raise ValueError(f"missing/invalid field: {name}") from exc
    if not math.isfinite(value):
        raise ValueError(f"nonfinite field: {name}")
    return value


def score_rows(rows):
    buckets=defaultdict(list)
    intervals_by_site=defaultdict(list)
    identities=set()
    for r in rows:
        if not isinstance(r,dict) or any(key not in r for key in SCHEMA):
            raise ValueError("all paired observation columns required")
        site=str(r["site_id"]).strip()
        split=str(r["split"]).strip()
        start,end=_float(r,"start_s"),_float(r,"end_s")
        if not site or split not in ("calibration","holdout") or not 0<=start<end:
            raise ValueError("site/split/window contract")
        # A site/time observation belongs to one split only: do not leak
        # identical detector windows into calibration and held-out evaluation.
        identity=(site,start,end)
        if identity in identities:
            raise ValueError("duplicate site/time row")
        identities.add(identity)
        intervals_by_site[site].append((start,end,split))
        observed,simulated=_float(r,"observed_count_veh"),_float(r,"simulated_count_veh")
        ov,sv=_float(r,"observed_mean_speed_mps"),_float(r,"simulated_mean_speed_mps")
        if any(x<0 for x in (observed,simulated,ov,sv)):
            raise ValueError("negative counts/speeds")
        # Both vehicle COUNT values refer to the same time window.
        geh=math.sqrt(2*(simulated-observed)**2/(simulated+observed)) if simulated+observed else 0.
        speed_sq=(sv-ov)**2 if observed>0 and simulated>0 else None
        buckets[split].append((geh,abs(simulated-observed),speed_sq))
    if not identities:
        raise ValueError("empty paired observation set")
    # One detector/direction must not contribute overlapping observations to
    # either split (especially not to both calibration and held-out metrics).
    for site, intervals in intervals_by_site.items():
        ordered=sorted(intervals)
        if any(right[0]<left[1] for left,right in zip(ordered,ordered[1:])):
            raise ValueError(f"overlapping detector windows/leakage: {site}")
    def aggregate(bucket):
        if not bucket:
            return {"status":"NOT_MEASURED","records":0}
        n=len(bucket)
        return {"status":"COMPUTED_FROM_SUPPLIED_PAIRS",
                "records":n,
                "geh_mean":math.fsum(item[0] for item in bucket)/n,
                "geh_p95":sorted(item[0] for item in bucket)[math.ceil(.95*n)-1],
                "count_mae_veh_per_window":math.fsum(item[1] for item in bucket)/n,
                "mean_speed_rmse_mps":(math.sqrt(math.fsum(item[2] for item in bucket if item[2] is not None)/sum(item[2] is not None for item in bucket)) if any(item[2] is not None for item in bucket) else None),
                "speed_pair_count":sum(item[2] is not None for item in bucket)}
    return {"split_metrics":{k:aggregate(buckets[k]) for k in ("calibration","holdout")},
            "scoring_semantics":"paired site/time/count and speed; not route times, micro headway or empirical proof",
            "field_dataset_provenance":"UNVERIFIED_FROM_ROWS"}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paired-csv",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    with open(args.paired_csv,newline="",encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    result=score_rows(rows)
    # Tool cannot know whether caller supplied actual field data. Provenance
    # must be established from external source manifest, never auto-inferred.
    result["provided_source_path"]=args.paired_csv
    Path(args.output).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result))


if __name__=="__main__":
    main()
