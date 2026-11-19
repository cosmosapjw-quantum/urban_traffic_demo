# V03-FIFO-SERVICE-STREAM · physical/algorithmic theory R1–R4 (2026-11-20)

Based on source b94670d03407a4fd2626884f58a1a293f57fd7cc, isolated research/v03-fifo-service-stream-20261120 worktree. SSOT PLAN 1.1.26, native source V1Road::step_state, original 100000 residents per city, 86400s per run, 3 cities ×3 repeats, 8GiB RSS and 7200s wall fixed. Prior authority 19/21 scoped DAG, P01/V01/V02 3/3, all 3 city calendars prepared on previous binary, source-matched Valley 25300 and 25600 prefix, full day 0/9 BLOCKED. No physical micro rate, demand, output tolerance or traffic closure fitted.

## R1. Original exact service contract

In original crates/metroflow-rust/src/v1_road.rs, the active head logic computes fraction=(rate*h/mass(packet)).min(1), applies original near-full 1−fraction threshold, checks work.transfer, then creates a temporary served Vec<Part> via portion(parts,f). It optionally records trace row counts, computes remainder via portion(parts,1−f), sums served masses via deterministic expansion sum (f64), updates cell movement moments, and traverses served Parts to construct original EventRow / incoming Part / Mark / sink mass / birth / route/clock ledgers. Only successful returned physical states count for this proof. Downstream event storage and pending offers remain unaffected.

## R2. Exact IEEE order-preservation lemma SES-1

Let an original finite physically valid sequence P=(p1,...,pn) of Part rows have nonnegative finite mass and original birth extensive first moment; fraction f is computed by the UNMODIFIED physical head-rate algorithm. Define per-row T_f(p): let m=fl(p.mass*f); if m>0, clone p, assign mass=m, birth=fl(p.birth*f), return row; otherwise emit none. The existing portion(P,f) and the new lazy iterator P.iter().filter_map(T_f) generate **exactly the same ordered Part sequence and to_bits of all fields**. Proof: per-row transformation and predicate are identical; induction on source index shows sequence equality including removed underflowed rows. No accumulation is involved in this lemma, and no class/route time priority is changed.

## R3. Exact expansion sum, per-event and resource lemmas SES-2/3

Given identical emitted mass order, original function sum (Shewchuk-like ordered expansion, round-to-even correction) follows identical deterministic state transitions and returns bit-identical scalar. Reiterate the immutable input to stream per-row EventRow/incoming/marks. A successful physical step remains exactly equivalent if queue-head replacement is committed after the same per-event processing, since the per-event body reads the original row, position[i], physical receiver/clock/motion and out/incoming buffers but NOT the modified head packet. Remainder is computed AND packed before the stream, retaining the original allocation/validation order; only commit of its value is delayed until the stream ends. All outgoing original flow/source/mass/birth f64 operations are unchanged and per-destination row order is unchanged. This is a conditional source-level equivalence theorem; every bit must be checked on actual V03 checkpoint and source-matched finite fixtures.

With n original Part rows, original portion temporarily retains a Vec with capacity <=n and up to n Part words. Direct per-row streaming avoids that single O(n) temporary vector; two independent walks can be required to preserve ordered expansion sum and event output. It does NOT bound actual process RSS, nor reduce original retained packet genealogy or explicit EventRow/incoming buffers. The nontrivial source issue is original work.transfer accounting and trace row counts; these must continue reporting the original logical count, not the new scratch count. Distinguish error-path failure order from successful semantic equality.

**Counterexample to an invalid optimization:** fsum of individually rounded m_i*f is not generally equal to f*fsum(m_i), and nested fl(fl(m*f)*g) differs from fl(m*fl(f*g)) (prior computed positive f64 witnesses). A correct stream must compute each Part multiplication and original ordered sum; no flattening or new tolerance is allowed.

## R4. Alternatives, adversarial gate and bounded acceptance

A. persistent EVCB across all queues and nodes: actual future source-of-truth redesign, requires versioned state and proven downstream callback/rollback, too wide to assume correctness in this narrow stage.
B. **Selected** stream the ORIGINAL served-side Part transformations, leave remainder and state history unchanged, preserve source/receiver physics and original checkpoint. This is an isolated actual engine modification with reversible minimal diff, not a claim of full EVCB.
C. fixed dimension moment closure/modified triangular FD: violates original time/route/birth FIFO observations, reject as silent substitute.
D. approximation or heuristic pruning: strict FIFO red/green head-of-line counterexample refutes unconditional small mass error implies small exit error; reject without explicit different physical acceptance.

Implement in a new isolated worktree, with independently old/eager and new/lazy tests including random Part, Uniform/Mixed intervals, signed zero, birth and subnormal underflow; then full Rust+Python regression, new binary source-bound 100k calendar preparation and original Valley 25300 checkpoint, optionally 25300→25600 congestion if resources allow. Compute time and true peak RSS on identical original source, report actual checkpoint bytes. Only then publish a scoped outcome; no full-day V03 acceptance until 86400s×9 original release runs actually finish.
