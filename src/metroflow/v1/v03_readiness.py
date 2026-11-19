"""Read-only MetroFlow V03 readiness from authoritative DAG, source matrix and receipts.

Does not alter PLAN, accept a packet-physics substitution, count a preflight as
a full-day campaign, or create new DAG nodes. Numeric denominators come only
from the existing source: 21 project nodes, 3 cities and 3 runs/city.
"""
from __future__ import annotations

import math
from typing import Mapping,Sequence


_COMPLETED={"ACCEPTED","VERIFIED_SCOPED"}


def _sha256(value):
    return isinstance(value,str) and len(value)==64 and all(
        c in "0123456789abcdef" for c in value
    )


def _prepared(
    row:Mapping,case:Mapping,matrix:Mapping,expected_sha:str,
    *,live_candidate_sha:str|None=None,live_native_sha:str|None=None
)->tuple[bool,str]:
    if row.get("status")!="WHOLE_CALENDAR_PREPARED":
        return False,"NO_SUCCESSFUL_EXACT_CALENDAR_PREPARATION"
    if row.get("engine_backend")!="rust_whole":
        return False,"NOT_ORIGINAL_WHOLE_NATIVE_ENGINE"
    if row.get("case")!=case["id"] or row.get("matrix_sha256")!=expected_sha:
        return False,"CASE_OR_MATRIX_SOURCE_BINDING_MISMATCH"
    if row.get("step_s")!=10 or row.get("horizon_s")!=0:
        return False,"PREPARATION_ONLY_MUST_HAVE_ZERO_EXECUTION_HORIZON"
    if row.get("simulated_s")!=0:
        return False,"PREPARATION_EVIDENCE_CLAIMS_AN_ACTUAL_RUN"
    if any(not _sha256(row.get(k)) for k in (
        "source_sha256","patch_sha256","candidate_source_sha256","native_binary_sha256"
    )):
        return False,"NATIVE_OR_SOURCE_IDENTITY_NOT_MEASURED"
    if live_candidate_sha is not None and row.get("candidate_source_sha256")!=live_candidate_sha:
        return False,"CURRENT_SOURCE_CONTENT_HASH_DIFFERS"
    if live_native_sha is not None and row.get("native_binary_sha256")!=live_native_sha:
        return False,"CURRENT_NATIVE_BINARY_CONTENT_HASH_DIFFERS"
    if not isinstance(row.get("driver_identity"),str) or not row["driver_identity"]:
        return False,"DRIVER_IDENTITY_MISSING"
    if row.get("candidate",{}).get("source_dirty") is not False:
        return False,"SOURCE_DIRTY_OR_PROVENANCE_MISSING"
    calendar=row.get("calendar")
    if not isinstance(calendar,dict) or calendar.get("resident_stock")!=matrix["population"]:
        return False,"RESIDENT_STOCK_NOT_PRESERVED"
    legs=calendar.get("legs")
    if isinstance(legs,bool) or not isinstance(legs,(int,float)) or not math.isfinite(legs) or legs<=0:
        return False,"CALENDAR_LEG_COUNT_MISSING"
    for field,limit in (
        ("wall_s",matrix["limits"]["wall_s"]),
        ("peak_rss_bytes",matrix["limits"]["peak_rss_bytes"])
    ):
        val=row.get(field)
        if isinstance(val,bool) or not isinstance(val,(int,float)) or not math.isfinite(val) or val<0 or val>limit:
            return False,"RESOURCE_MEASUREMENT_MISSING_OR_EXCEEDED"
    return True,"WHOLE_CALENDAR_PREPARATION_VERIFIED_NOT_DAY"


def assess_v03_readiness(
    plan:Mapping,
    matrix:Mapping,
    *,
    matrix_sha256:str,
    preparation_receipts:Sequence[Mapping]=(),
    live_candidate_source_sha256:str|None=None,
    live_native_binary_sha256:str|None=None,
)->dict:
    """Conservative V03 diagnostic; never interprets prepare-only as full-day."""
    if not isinstance(plan,dict) or not isinstance(matrix,dict):
        raise ValueError("authoritative plan/matrix maps required")
    nodes=plan.get("nodes")
    if not isinstance(nodes,list) or not nodes:
        raise ValueError("nonempty plan nodes required")
    by={n["id"]:n for n in nodes}
    if len(by)!=len(nodes) or plan.get("plan_id")!="METROFLOW-V1":
        raise ValueError("plan node identity/authority invalid")
    actually_done=[n["id"] for n in nodes if n.get("status") in _COMPLETED]
    progress=plan.get("implementation_progress",{})
    if (progress.get("completed_count")!=len(actually_done) or
        progress.get("total_count")!=len(nodes) or
        set(progress.get("completed_nodes",()))!=set(actually_done)):
        raise ValueError("plan progress/count disagrees with node statuses")
    if not "V03" in by or not "RLS01" in by:
        raise ValueError("V03 or release node absent from authority")
    if not isinstance(matrix.get("cases"),list) or len(matrix["cases"])<1:
        raise ValueError("release matrix cases missing")
    cases=matrix["cases"]
    known=[c["id"] for c in cases]
    if len(set(known))!=len(known):
        raise ValueError("duplicate release matrix cases")
    if not _sha256(matrix_sha256):
        raise ValueError("matrix source hash must be verified")
    if matrix.get("population")!=100000 or matrix.get("horizon_s")!=86400 or (
       matrix.get("repeat")!=3):
        raise ValueError("source matrix does not match original 100k/24h V03 contract")
    if matrix["limits"].get("peak_rss_bytes")!=8*1024**3 or matrix["limits"].get("wall_s")!=7200:
        raise ValueError("original resource acceptance limits changed")
    if plan.get("next_node")!="V03":
        raise ValueError("plan next node differs from V03 source authority")
    evidence={}
    for row in preparation_receipts:
        if not isinstance(row,dict):
            raise ValueError("evidence receipt must be a mapping")
        key=row.get("case")
        if key not in known:
            raise ValueError("unknown release matrix case in evidence")
        if key in evidence:
            raise ValueError("duplicate source preparation receipt")
        evidence[key]=row
    prep={}
    for case in cases:
        key=case["id"]
        if key not in evidence:
            prep[key]={"status":"NOT_RUN","reason":"NO_FRESH_PREPARATION_RECEIPT"}
        else:
            ok,reason=_prepared(
                evidence[key],case,matrix,matrix_sha256,
                live_candidate_sha=live_candidate_source_sha256,
                live_native_sha=live_native_binary_sha256)
            prep[key]={"status":"PREPARED_SCOPED" if ok else "REJECTED_EVIDENCE",
                       "reason":reason}
    deps=by["V03"].get("depends_on",[])
    deps_done=sum(by[k].get("status") in _COMPLETED for k in deps)
    unfinished={n["id"]:n["status"] for n in nodes if n["id"] not in actually_done}
    n_prepared=sum(v["status"]=="PREPARED_SCOPED" for v in prep.values())
    return {
        "authority":{"plan_id":plan["plan_id"],"version":plan["version"],
                     "matrix_sha256":matrix_sha256},
        "dag":{
            "completed":len(actually_done),
            "total":len(nodes),
            "completion_percent":100.*len(actually_done)/len(nodes),
            "completed_node_ids":actually_done,
            "not_completed":unfinished,
            "scope":"ACCEPTED or VERIFIED_SCOPED; not release acceptance",
        },
        "v03":{
            "status":by["V03"]["status"],
            "dependency_nodes_completed":deps_done,
            "dependency_nodes_total":len(deps),
            "calendar_preparation_verified":n_prepared,
            "calendar_preparation_total":len(cases),
            "population_residents_per_case":matrix["population"],
            "horizon_seconds":matrix["horizon_s"],
            "required_full_day_runs":len(cases)*matrix["repeat"],
            "completed_full_day_runs":0,
            "rss_bytes_max":matrix["limits"]["peak_rss_bytes"],
            "wall_seconds_max":matrix["limits"]["wall_s"],
            "ready_for_release":False,
            "execution_status":"BLOCKED_BY_EXACT_INTERVAL_PACKET_EXPLOSION",
            "real_full_day_execution_evidence":"NONE_IN_SUPPLIED_PREPARATION_RECEIPTS",
            "physics_scope":"unchanged original packet FIFO, no source/data/tolerance relaxation",
        },
        "case_preparation":prep,
        "declared_engineering_inputs_not_fitted_here":{
            "inventory_policy":matrix["inventory_policy"],
            "max_cohorts_by_case":{c["id"]:c.get("max_cohorts") for c in cases},
            "route_materialization_budget":matrix["route_materialization_budget"],
            "worker_shortfall":matrix["worker_shortfall"],
            "current_driver_freight_kg":"literal 1000 in tools/run_v1_local_acceptance.py; not derived"
        },
        "next_required_evidence":"actual 3-city x 3 86400s original-physics run with replay/ledger/refined_dt under original 8GiB/7200s limits",
    }
