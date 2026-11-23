# R3 selected theory contract — clipped motion plus joint FIFO service

Base prior loop: 90bfca2c2ddf081cbdf40d11b95ff820837d03b5.
R2 portfolio pushed at c4c90f1; parent selected A+B. C identification is deferred.
This contract is for a separate research observer, not a change to native physics or production routing.

## Claimed physical model

One fixed homogeneous motion characteristic, without bulk mixing jumps:
v'=clip((V-v)/tau,-B,A), x'=v; tau>0s, b>0m/s, A>0m/s², B>=0m/s²,
0<=V,v<=b and initial speed lower 0<=v_lower<=b.
No positive instantaneous lower speed/forcing is assumed.
Motion-ready time and FIFO node-outlet time remain distinct.

Each guaranteed forcing window has length H>0s and integral V>=J with 0<J<=bH [m].
The source of J must be available at decision time and valid through every used window.
No past average or future realized oracle is promoted into a future guarantee.

Node available service is min(Cg,R), C>0veh/s, 0<=g<=1, 0<=R<=C.
Within any backlogged guaranteed window it serves its available mass to this same movement.
The actual tagged FIFO rank has ahead+tagged mass <=W [veh] at its motion-ready time.
W is not a route mean, journey birth moment or nominal capacity; new mass behind that rank cannot overtake.

## Causal authority and finite scope

Typed input basis includes context, caller authority/statement, available_at_s,
valid_from_s and valid_until_s. A nonempty authority string records the caller's assumption;
it does not prove that the native model meets it.
Every basis must match the requested context, be delivered by decision_s, and cover its
required physical interval. The request requires 0<=decision_s<=entry_s.
The motion and queue-rank basis must cover every possible ready time used by the bound.
The service basis must cover the complete service windows used for the final bound.

Future oracle histories are used only to test declared guarantees and compare outcomes.
Endogenous rerouting, mixing, changed context, missing receiving guarantees and unbounded
ahead rank require a new certificate or an unresolved result.

## Aligned versus sliding windows

SLIDING means the stated lower bound holds on every length-H window whose endpoints
lie within the validity interval.
ALIGNED means only windows [origin+kH,origin+(k+1)H] are guaranteed.
The observer moves to the next aligned boundary, adding a phase delay; it does not
silently treat an aligned promise as sliding.
Ignored motion before that boundary is nonnegative and therefore safe to omit; any
initial-speed lower bound is reset to zero after this ignored interval.
Aligned service similarly waits to the next valid grid boundary.
For unknown actual ready time u<=motion_upper, the aligned start plus fixed number
of service windows is monotone in u, so evaluation at motion_upper is conservative.
Grid arithmetic will use exact rational interpretations of finite binary-float inputs;
reported upper times will be rounded upward for this arithmetic only.

## Derived lower and finite search

eta=min(1,A*tau/b). For n full motion windows:
L_n=tau*v_lower*(1-exp(-nH/tau))
 +eta*[nJ-b*tau*(1-exp(-J/(b*tau)))*(1-exp(-nH/tau))/(1-exp(-H/tau))].
L_n is increasing; its n->infinity slope is eta J>0.
K=b*tau*(1-exp(-J/(b*tau)))/(1-exp(-H/tau)),
N_sufficient=ceil((ell/eta+K)/J) is a calculable sufficient upper in the unbounded-horizon model.
Only windows within the caller's finite validity are admissible.

For node marginals, J_s=max(0,J_green+J_receiving-C*H_s).
A direct joint-service lower can alternatively be stated with its own explicit basis.
For W>0 and J_s>0, ceil(W/J_s) complete service windows suffice.
The motion-to-service composition preserves SI units and the physical distinction
between motion distance [m] and served mass [veh].

## API and failure states

Files owned by this work:
- src/metroflow/v1/stop_go_window_certificate.py
- docs/research/V03_STOP_GO_WINDOW_THEORY_20261123.md
- tests/research/test_v03_stop_go_window_20261123.py
- tools/research/v03_stop_go_window_experiment_20261123.py
- this contract plus R5_/R7_ theory receipts in the current artifact directory

Planned frozen typed API: ExAnteBasis, WindowPhase, ClippedMotionLaw,
ForcingWindow, JointServiceWindow, QueueRankBound and evaluate_link_bound.
Results separate motion and node-service components.

Invalid parameters, mismatched contexts or future-delivered evidence raise ValueError.
Numerically unrepresentable evaluation raises a separate ArithmeticError subtype.
HORIZON_UNCERTIFIED is returned when a valid finite promise cannot establish the required bound,
when no positive joint-service bound follows, or when the declared numeric margin cannot
separate the distance threshold. It is not a claim of physical UNREACHABLE.

Analytic bounds are statements in real arithmetic. Float evaluation uses an explicit
absolute/relative guard margin and reports its size; it is NOT a directed-rounding
interval certificate. Source comparison, high-precision oracle checks and exact Fraction
side checks are separately identified.

## Focused success/discriminator cases

The R2 declared fixture has clipped motion L=20m and an actual zero-service wait of6s:
motion upper24s, node upper10s, total upper34s; actual final-rank outlet23.639484898s.
A separately known legal alternative B of36s is strictly dominated by the analytic
upper34s for A, conditional on the declarations. No baseline routing behavior is invented:
the old strictly-positive-speed observer is inapplicable with a=0.
The new research selector may report this pairwise ordering; production rerouting remains inactive.

Tests will cover phase delay, causal delivery, finite horizon, zero joint service,
the constructive case, clipping comparison, queue-rank units and exact same-input determinism.
Experiments increase physical horizons and problem sizes without artificial sleep,
reuse the existing Python characteristic as a separate motion oracle, and retain all failures.

## Drift watchdog

Original intent: self-propelled mesoscopic traffic, stop/restart, constrained routing cost.
Progress: a new clipped finite-window physical lemma plus a service condition that permits actual stops.
Preserved: native continuous velocity, FIFO/mass, causal information, demand, dt, resource caps and V03 criteria.
Observation population: same homogeneous characteristic and same movement's FIFO mass rank.
Verdict: ALIGNED_WITH_OPEN_OBLIGATION. Remaining obligation is ex ante native J/J_s/W provenance;
synthetic guarantees and research tests provide no original100k24h execution credit.
