#!/usr/bin/env python3
"""Map a native event-incidence moment observation to conditional age bounds.

No original vehicle population or completed-journey law is inferred here.
Arithmetic intervals enclose operations on stored f64 rows, not historical
solver error. The birth support [0, snapshot time] is an explicit source
assumption for the original nonnegative-clock calendar. A stronger source-proven
lower birth clock may be supplied explicitly; it is never inferred from a mean.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
from fractions import Fraction as F
import json
import hashlib
from pathlib import Path
from metroflow.v1.age_moment_envelope import AgeMomentBlock, stop_loss_envelope


def number(x: F) -> dict:
    return {"exact":str(x), "approx":float(x)}


def observe(raw: dict, thresholds=(0,60,300,600,1800,3600), *, birth_min_s=0) -> dict:
    if raw is None or raw.get("status")=="OBSERVER_ERROR":
        return {"status":"NOT_OBSERVED", "native":raw}
    if raw.get("schema")!="V03_SERVICE_EVENT_INCIDENCE_MOMENTS_V1":
        raise ValueError("unsupported native moment schema")
    t,m,a=map(F,(raw["time_s"],raw["mass"],raw["age_time_mass"]))
    birth_min=F(birth_min_s)
    if not 0<=birth_min<t:
        raise ValueError("declared birth lower bound must be in [0,snapshot time)")
    max_age=t-birth_min
    ml,mh=map(F,raw["mass_interval"])
    al,ah=map(F,raw["age_time_mass_interval"])
    if t<=0 or not 0<ml<=m<=mh or not al<=a<=ah:
        raise ValueError("nonpositive mass/clock or inconsistent arithmetic interval")
    # Intersect with the explicitly assumed physical support. This is not
    # permission to infer the support from the observed mean.
    al,ah=max(F(0),al),min(ah,mh*max_age)
    if ah<al:
        raise ValueError("stored moment enclosure contradicts declared birth support")
    try:
        point=AgeMomentBlock(m,a,F(0),max_age)
    except ValueError:
        point=None
    bounds=[]
    for value in thresholds:
        u=F(value)
        if not 0<=u<=t:
            raise ValueError("native observation threshold outside [0,t]")
        # Every feasible (M,A) inside the reported rectangle is covered.
        lower=max(F(0),al-mh*u)
        upper=ah*max(F(0),max_age-u)/max_age
        if lower>upper:
            raise ArithmeticError("inconsistent interval moment bounds")
        item={"threshold_s":number(u),
              "conditional_K_lower_vehicle_s":number(lower),
              "conditional_K_upper_vehicle_s":number(upper),
              "incidence_tail_upper_at_u_plus_300s":number(
                  min(F(1),upper/(F(300)*ml)))}
        q=u+F(300)
        sharp_mean_tail=(F(0) if q>max_age else min(F(1),ah/(q*ml)))
        item["incidence_tail_threshold_s"]=number(q)
        item["incidence_tail_upper_with_source_support"]=number(sharp_mean_tail)
        item["tail_method"]="source support plus positive-age Markov bound; stored interval inputs"
        if point is not None:
            exact=stop_loss_envelope((point,),u)
            item["stored_point_moment_envelope"]={
                "lower":number(exact.lower),"upper":number(exact.upper)}
        bounds.append(item)
    return {
        "status":"NUMERICALLY_CHECKED_CONDITIONAL_MOMENT_ENVELOPE",
        "observation":"service event-incidence age at common snapshot time",
        "not_unique_vehicle_or_final_journey_distribution":True,
        "source_support_assumption":"original birth clock in [declared birth_min,snapshot time]; conditional exact-model claim",
        "declared_birth_min_s":number(birth_min),
        "conditional_age_support_s":[number(F(0)),number(max_age)],
        "arithmetic_scope":raw["scope"],
        "historical_solver_roundoff_certified":False,
        "row_count":raw["row_count"],
        "retained_event_storage_bytes":raw["storage_bytes"],
        "compact_events":raw["compact_events"],
        "time_s":number(t),"incidence_mass":number(m),
        "mean_age_interval_s":[number(al/mh),number(ah/ml)],
        "age_first_moment_interval_vehicle_s":[number(al),number(ah)],
        "bounds":bounds,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt",type=Path)
    parser.add_argument("--out",required=True,type=Path)
    parser.add_argument("--birth-min-s",type=int,default=0,
                        help="source-proven lower birth clock; never infer it from the mean")
    args=parser.parse_args()
    receipt=json.loads(args.receipt.read_text())
    result={
        "schema":"V03_NATIVE_EVENT_MOMENT_ENVELOPE_20261123_V1",
        "source_receipt":str(args.receipt),
        "native_sha256":receipt["current_native_binary_sha256"],
        "candidate_source_sha256":receipt["current_candidate_source_sha256"],
        "source_case":receipt.get("case"),
        "source_driver_identity":receipt.get("current_driver_identity"),
        "source_matrix_sha256":receipt.get("original_matrix_sha256"),
        "observer_script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "initial":observe(receipt.get("initial_event_moment_observation"),birth_min_s=args.birth_min_s),
        "final":observe(receipt.get("final_event_moment_observation"),birth_min_s=args.birth_min_s),
    }
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"output":str(args.out),"initial_status":result["initial"]["status"],
                      "final_status":result["final"]["status"]}))


if __name__=="__main__":
    main()
