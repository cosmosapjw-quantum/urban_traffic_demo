"""Certified adaptive route FIFO coalescence over the partition-invariant KCMB node.

Only adjacent, currently eligible runs of the SAME registered route are
collapsed. This is an exact quotient for this route-moment/one-lane model,
NOT for per-vehicle arrival-timestamp observations or arbitrary micro traffic.
The full history is never silently compressed if route or eligibility differ.

Temporary expanded-run budget is larger to permit output canonicalization.
Persistent run budget is the user-specified strict_max_runs, with fail-closed
checkpoint if that output cannot be represented exactly.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from hashlib import sha256
import json

from .kcmb_ordered_fifo import (
    OrderedKCMBBoundedNetwork, OrderedRun, FIFOQueueState, FIFOQueueBudgetError,
)

_VERSION="kcmb_adaptive_eligible_fifo_v1"


class CertifiedAdaptiveFIFO(OrderedKCMBBoundedNetwork):
    def __init__(self, config, *, backend="python", max_runs=256):
        if isinstance(max_runs,bool) or not isinstance(max_runs,int) or not 1<=max_runs<=100_000:
            raise ValueError("positive finite persistent FIFO run budget required")
        # At most a bounded number of new incoming link/source subevents can
        # occur in one timestep, before eligible same-route runs are merged.
        # If even that bound is exhausted, the underlying solver fails closed.
        slack=min(10_000, 2*len(config.links)*(len(config.routes)+1))
        internal=min(100_000,max_runs+max(8,slack))
        super().__init__(config,backend=backend,max_runs=internal)
        self.strict_max_runs=max_runs
        self.model_id=_VERSION+":"+sha256(
            (self.model_id+"|persistent="+str(max_runs)).encode("utf-8")).hexdigest()

    def _strict_check(self,state):
        self._check_ordered(state)
        n=sum(len(q) for q in state.runs)
        if n>self.strict_max_runs:
            raise ValueError("persistent FIFO run state exceeds strict budget")

    def _coalesce(self,state):
        merged_queues=[]
        removed=0
        # State tick is the decision time after *all* source/turn admissions.
        # Newly-entered runs have ready_tick>tick, so are never hidden.
        for queue in state.runs:
            collapsed=[]
            for run in queue:
                if (collapsed and collapsed[-1].route==run.route and
                    collapsed[-1].ready_tick<=state.tick and
                    run.ready_tick<=state.tick):
                    last=collapsed[-1]
                    collapsed[-1]=OrderedRun(run.route,last.mass+run.mass,
                                             last.ready_tick)
                    removed+=1
                else:
                    collapsed.append(run)
            merged_queues.append(tuple(collapsed))
        compacted=replace(state,runs=tuple(merged_queues))
        self._check_ordered(compacted)
        return compacted,removed

    def _must_fit(self,state,checkpoint):
        nr=sum(len(q) for q in state.runs)
        if nr>self.strict_max_runs:
            error=FIFOQueueBudgetError(
                f"adaptive exact FIFO persistent run budget exceeded: "
                f"{nr}>{self.strict_max_runs}")
            error.checkpoint=checkpoint
            raise error
        return nr

    def initial_profile(self,profile,*,order_by_link=None):
        expanded=super().initial_profile(profile,order_by_link=order_by_link)
        compacted,_=self._coalesce(expanded)
        self._must_fit(compacted,self.initial())
        return compacted

    def step(self,state,offers,*,gates=None):
        self._strict_check(state)
        try:
            raw,receipt=super().step(state,offers,gates=gates)
        except FIFOQueueBudgetError as exc:
            # The engine already does not mutate state. Preserve this exact
            # adaptive identity rather than returning a transient raw one.
            exc.checkpoint=state
            raise
        compacted,removed=self._coalesce(raw)
        count=self._must_fit(compacted,state)
        self._strict_check(compacted)
        receipt=dict(receipt)
        receipt.update(
            model_id=self.model_id,
            run_count=count,
            run_budget=self.strict_max_runs,
            runs_certifiably_merged=removed,
            adaptive_certification="adjacent_same_route_all_eligible",
            internal_transient_budget=self.max_runs,
        )
        return compacted,receipt

    def to_bytes(self,state):
        self._strict_check(state)
        return json.dumps({"format":_VERSION,**asdict(state)},sort_keys=True,
                          separators=(",",":"),allow_nan=False).encode("utf-8")

    def from_bytes(self,data):
        limit=4096+64*self.state_scalars+120*self.strict_max_runs
        if not isinstance(data,(bytes,bytearray)) or len(data)>limit:
            raise ValueError("adaptive FIFO checkpoint size budget exceeded")
        try:
            row=json.loads(data)
            if set(row)!={"format","model_id","tick","moments","pending",
                           "released","completed","runs"}:
                raise ValueError("adaptive FIFO checkpoint shape")
            if row["format"]!=_VERSION or row["model_id"]!=self.model_id:
                raise ValueError("adaptive FIFO checkpoint identity mismatch")
            state=FIFOQueueState(row["model_id"],row["tick"],
                tuple(row["moments"]),tuple(row["pending"]),
                tuple(row["released"]),tuple(row["completed"]),
                tuple(tuple(OrderedRun(**v) for v in queue) for queue in row["runs"]))
            self._strict_check(state)
            return state
        except (ValueError,TypeError,KeyError,OverflowError) as exc:
            raise ValueError("adaptive FIFO checkpoint format/identity/state invalid") from exc
