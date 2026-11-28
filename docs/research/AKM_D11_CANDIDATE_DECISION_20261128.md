# AKM D11: 유한 후보 선택 및 중단 결정

2026-11-28. 시작 기준 a0a8b2d109f6a9c8945a23012af979efb9382b90, AKM SSOT v1.0.0, original V1 PLAN v1.1.55 unchanged. D11 one decision attempt, no new simulation run, no new candidate. The archived comparison is not a common-domain Pareto optimization: A synthetic joint ladder, B projected AM archive and D original-calendar prefix differ in inputs, closures and horizons. No aggregate scalar ranking or runtime compensation for failed physics.

## Decision

| Candidate | scoped positive | failed gate or missing evidence | disposition |
|---|---|---|---|
| A | local positive moment and conservative fixed support | 22/24 day/ladder runs reached, two moment cone stops; selective finest adjacent gap 43.2832%; original service and replay unknown | retain local operators; no whole-network candidate |
| B | projected 24h vehicle run, matched AM mean 774.68645 to 774.66152 s | 300/150s receiving ratio abs gap 0.028614 > 0.02; mean relative gap 0.00003218; original calendar and replay unknown | projected comparator only |
| D | reserved service fixture, causal routing/LUTI synthetic scopes, city checkpoint recovery, 61.0055% row reduction | free-flow extra delay 7s invariant across 1/0.5/0.25s steps; fixed bus seat deficit at least 29040/30000 intents, original parent-profile lower bound 47884.03508925/120000; full day and holdout unexecuted | keep scoped subclosures only |

D09 matched prefix t=25430s: old 953296 rows, new 371733; completed persons decreased 20.774%, not semantic parity. Continuation stopped at 26310s by prior session limit, not resource failure or proof of impossibility. The seat bound is conditional on 24 one-run fixed buses of 40 seats with no added service, not a lower bound for arbitrary transport systems. The parent profile deficit is a separate original owner/eligibility calculation, not an additive deficit. Under the isolated two-pulse free-flow example with T=L/v=10s and epsilon=3s, the sealed policy serializes the second entry and delays its exit T-epsilon=7s; this persists as step size tends to zero and refutes that closure's consistency in the example.

D11 gate is a noncompensatory conjunction: every required claim must be supported, not UNKNOWN. None qualifies. D11 VERIFIED_SCOPED means the finite decision is complete, **not** model acceptance. D12 STOPPED with zero attempts and no release experiment: no selected/approved candidate. D13 READY, terminal synthesis/integration review only; do not auto-launch in this D11 cycle. No reopening D05/D09, no new science candidate or acceptance threshold change.

## Implementation and reproduction

Rust binary: cargo run --offline -q -p metroflow-headless --bin metroflow-akm-d11 -- .
It recomputes evidence from pinned JSON, checks matching scopes and keeps null unknowns. Python frontend only reads the decision receipt and rejects incorrect identity/status. S03 actual RED then GREEN; S07 actual RED then GREEN. S06 identical repeated Rust output; S08 exact rational independent arithmetic from raw A/B/D archives (24 A cases, 7 matched B observations, 3 native D timing log rows) and 26 headless tests plus 10 frontend tests. Not a new trajectory generation or independent agent. No source authentication beyond committed digests. No full CI, main merge, original V03 campaign or D10 holdout.

AD1 original goal preserved: physical dynamics, explicit units, demand/service and replay. AD2 scope and candidate identity explicit; no cross-closure parity or projected-to-original extrapolation. ALM1 no new exact tick or cap change. ALM2 D05/D09 terminal limits honored. See artifacts/akm_d11_decision_20261128/S06_decision.json, S08_independent.json, S08_review.md. CAUTION_RESEARCH_ONLY.
