# V03-FIFO-LINEAGE-C1 · executable bounded coding research contract

Source parent: \`8e891b907f3f85e9ae8ff7c86a1b8836f4341815\` (ten proved/checked R1–R10 research stages); isolated branch \`research/v03-fifo-lineage-coding-20261119\`. Original main \`01c80b4\`, PR41, PLAN v1.1.26, native original road source and all original memory/wall/physics contracts are protected.

## C1. 목표·기준 결과 설정

Execute the **first bounded EVCB coding slice**: a Rust immutable shared \`Part\` composition + ordered binary64 operation DAG, with lazy per-row materialization and callback streaming, compared against the ORIGINAL \`portion\`, \`interval_packets\` split and route/offset/time rewrite behavior. Scientific goal is to test whether a shared source template can avoid repeated retained Part arrays **without changing any original physical claim**. There is no authorization to replace default road flow or change the V03 release target. Any actual original runtime modification must be in an opt-in branch and must first pass byte-based source/reference tests.

Locked V03 execution counts: project scoped DAG 19/21, P01/V01/V02 3/3, original 100k population per city for River/Coastal/Valley, earlier matching native 3/3 calendar preparations, previous original/optimized 25,600s binary-equal prefix for Valley, release 24h×3 cities×3 repeats **0/9** and V03 BLOCKED. A new compiled source hash makes old receipts **stale** for the new binary; freshly verify those prerequisites before counting them under the new branch. Do NOT increment the existing authoritative DAG node merely for research tests.

Accept C1 scope only with positive source identity, a RED/GREEN exact physical operation test, constructive edge-case coverage, a bounded finite microbenchmark recording retained storage + materialization + callback costs, a truthfully labeled opt-in shadow-vs-eager status, and a downstream event-consumer analysis. Failure exits with concrete native compiler/runtime/physics classification, not a broadened tolerance.

No fitted \`U,\alpha,\nu,\tau\`, source demand, probe weight, packet birth correction or new performance-tuning threshold. Original stored IEEE binary64 fraction \`f\` is an input supplied by the original rate/event resolution, not a fitted coefficient.

## C2. 코드·수식·데이터 정본 재확인

Original core: crates/metroflow-rust/src/v1_road.rs. The private \`Part\` is \`{tag,offset,mass,birth,a:PackedTime,b:PackedTime}\`, deriving \`Copy\`; \`PacketParts\` variants \`Uniform{a,b,rows:Vec<CorePart>}\` and \`Mixed(Vec<Part>)\`. \`portion(parts,f)\` allocates \`Vec<Part>\`, loops in input order, evaluates \`m=p.mass * f\`, drops p when \`m<=0.0\`, otherwise sets \`q.mass=m; q.birth *= f\` and pushes. \`interval_packets\` selects source rows at \`[a,b]\` with original eligibility, then uses \`q.mass=q.mass*(b-a)/(pb-pa)\`, and the identical birth expression, followed by the original \`PackedTime::new(Some(a/b))\`.

Downstream execution still builds \`Vec<EventRow>\`, \`incoming: Vec<Vec<Part>>\`, service \`marks\`, and \`combine\`/full native state serialization. New shadow evaluator cannot decrease these costs without redesigning the consumers, as proved by previous R5-L5. The original storage policy, rate/turn optimization, sign of \`-0.0\`, deterministic \`sum\` order, route travel birth moment, and checkpoint identity are not changed.

The earlier exact source baseline: \`docs/research/V03_FIFO_LINEAGE_THEORY_R1_R10_20261119_KO.md\`, and \`tools/research/v03_fifo_lineage_theory_checks.py\`, with Fraction mass/birth conservation, 420 marked prefix checks, 2812 exact coalescence checks, and IEEE counterexamples. A correct shadow must match *actual operations* not multiply a cumulative fraction. Include repeated reductions, zero-positive-rounding, signed timestamp endpoints and original order under multiple tags; compare all Part fields as \`to_bits\` or exact tag/offset values.

Benchmark identity: one immutable root of P rows, E branch service operations and all retained child views. Measure (i) retained root \`Arc\` pointer identity and allocation counters, (ii) stored distinct graph nodes and structural bytes with \`size_of\` plus actual \`Vec\` capacities, (iii) eager duplicate row capacities, (iv) callback checksum including per-row target/timestamp, and (v) time per source operation and per forced output. Do not substitute structural accounting for process RSS or claim V03 runtime acceleration from a shadow.

## C3. 알고리즘·수치기법 설계

A shadow-only \`Arc<LineageNode>\` DAG supports \`Base(Arc<[Part]>)\`, \`Scale{parent,fraction_bits}\`, \`Restrict{parent,a,b}\`, \`Rewrite{parent,offset_delta,a,b}\`. For later extension, ordered \`Concat\` over views gives a deterministic stream of source order, but the initial slice does not reimplement \`combine\`; its exact evaluator simply provides the old ordered Part stream as input to the existing combine.

**Canonical executable semantics.** For each source row, walk the immutable operation chain from base toward leaf:
- Scale f: in original order evaluate \`m=p.mass*f\`; if not \`m>0.0\` drop; else assign \`p.mass=m; p.birth *= f\`. Record the fraction *as its original binary64 value*, including independently computed \`1.0-f\` for the remainder. Neither f multiplication nor birth computation may be reordered.
- Restrict a<b: only rows satisfying \`p.a<=a && p.b>=b && p.b>p.a\` are retained, then exactly \`p.mass = p.mass*(b-a)/(pb-pa)\`, same birth, assign packed new a,b. For equal-endpoint point-event passthrough, use the original separate equality selector, without inventing a tiny width.
- Rewrite: increment offset exactly once (with overflow check) and set original event time supports using \`PackedTime::new(Some(...))\`.
- A public \`visit(f)\` streams one Part at a time into a callback. A \`materialize()\` adapter collects the same stream into a \`Vec<Part>\`; it is intentionally a reference bridge, not a production memory cure.

**Proof of exact trace for this restricted operator language.** Fix finite source rows and ordered operations \`O_1,...,O_k\`. By induction on k, base materialization equals source. Every Scale, Restrict or Rewrite applies the exact same per-row IEEE expression, branch predicate, field rewrite and relative row order as the eager reference; therefore the resulting list of Part payload bits after one additional operator matches. A nested source expression can be streamed by iterating base rows and applying the k operators in order, with no eager intermediate row vectors. This proves *per-view operation equivalence* for the supported language under a fixed toolchain/ABI. It does **not** prove end-to-end original V03 physical equivalence, since native FIFO/event/marks/network consumers may differ if redesigned.

**Complexity.** P base rows, E retained split/view nodes, maximum chain depth D, V forced output rows. Retained shared state O(P+E) graph elements **only when every branch refers to the same base and each event adds O(1) nodes**, in contrast to eager O(P E) retained rows. The simple shadow materializer may cost O(PD) per view, so it can be *slower* than eager calculation, especially for deep trace chains. An optional separately verified memoization or a persistent materialization buffer would alter this cost but must never collapse floating arithmetic. Streaming one view uses O(D) operation scratch plus O(1) row scratch, excluding the caller's output. Fan-in merges and explicit output APIs can restore Ω(P E) work. No bounded 24h memory conclusion.

**Safety.** Use no arbitrary depth cutoff; represent the chain iteratively instead of recursive stack growth. Reject nonfinite fraction outside [0,1] and nonexistent invalid time intervals (the source should already guard these). Store actual original physical fields; do not insert a traffic approximation. A test that fails due to underflow (rounded mass zero) identifies a bug in the lazy evaluator.

## C4. 구현 DAG, 작업 격리, 명시적 중단 조건

Implementation activities are intentionally stage-local, with separate pushes:
- C1 baseline/acceptance written and pushed, no production code changes.
- C2 exact source map and numeric bit contracts written and pushed.
- C3 trace-DAG design, type units and output-sensitive complexity written and pushed.
- C4 bounded implementation DAG and tests defined, pushed before mutation.
- C5 test-first new private Rust shadow expression evaluator under v1_road.rs test module, with independent old \`portion\` and interval rows; no production application or source flow modification; all failing tests first observed locally, green after implementation, then push.
- C6 fresh native cargo tests + selected original V1 Python regressions, classify environment errors separately, push actual logs.
- C7 independent physical/IEEE source-equivalence cases (nested split, overflow/underflow, mixed time intervals, exact birth/route FIFO tags), push measured results, no ungrounded city claim.
- C8 a deterministic release-mode bounded synthetic repeated-split benchmark (same Part array for all runs, no fitted hyperparameters), report retained symbolic node/bytes, eager copy bytes, streamed materialization time and benchmark process resource usage. Judge BOTH storage and computational time; do not claim speed gain if slower.
- C9 one bounded adversarial review of the source and untested contracts, fix only genuine issues and push.
- C10 authoritative V03 readiness from unchanged PLAN 19/21 and fresh source/binary-bound calendar receipts. If new native is rebuilt, 3/3 old receipts are STALE until recomputed; if full-day 0/9 remains, mark it BLOCKED. Final artifact hashes, source SHA, remote SHA readback, handoff and push.

**Explicit blocker gate.** A test-only shadow that does not change native production is NOT a V03 accepted implementation and does NOT alter DAG. Preserve original source/fleet/time/signal and 8 GiB and 7200s; do not launch uncontrolled 86,400s×9 until a real representation change suppresses packet explosion. No production PR/main mutation. Coding correctness admission requires semantic and bitwise equivalence of the supported expression language and honest performance measurements, not merely Rust compilation.

**Need for later theory on demand:** if expression DAG cannot preserve an event-time grouping with a changing ready/target mark, derive a typed counterexample before adding a new rewriting rule; do not "fix" it by silently dropping route-specific event marks.

## C5. 실제 Rust shadow EVCB 구현 및 기록된 RED→GREEN

Direct Rust code artifacts: crates/metroflow-rust/src/v1_lineage_shadow.rs (test-only) with LineageArena, LineageNode::Base(Arc<[Part]>), Transform(parent_node_id, LineageOp), and visit()/materialize(). Its sole inclusion in v1_road.rs is guarded by cfg(test): the original traffic solver's source dataflow/physical transition and existing serial checkpoint schema have NOT been switched to the new representation.

**Implementer correction to C3:** although an immutable Arc<Node> chain was initially specified, this concrete shadow uses an append-only indexed arena with stable integer node IDs. Its Base holds an immutable Arc slice and transforms store a parent index. This avoids deep recursive destructor/stack behavior and makes new nodes O(1) apart from vector reallocation. The mathematical DAG semantics are unchanged; it is NOT yet a thread-safe production-permanent arena or an EVCB implementation of perfect network-wide FIFO.

**Exact supported physical primitives:** scale(f) repeats original source 'let m=p.mass*f; if m>0 {q.mass=m;q.birth*=f; keep row}', including the drop test and separately supplied complement f. restrict(a,b) selects the original row interval predicate, computes mass=mass*(b-a)/(pb-pa) in original Rust operation order and does the same for birth; advance_offset increments route offset exactly once; rewrite_time retains IEEE signed-zero time payloads. visit streams rows to a callback without allocating a whole output array, while materialize deliberately reconstructs the old ordered Part vector when required. All root rows are shared by multiple views, no source mass is fitted or pruned outside the original m>0 rule.

**TDD evidence:** Before the API existed, the focused command 'RUSTFLAGS="-C link-arg=-lpython3.12" cargo test --offline --workspace --lib exact_shadow_tests' exited 101 with E0433 LineageArena undefined (expected behavior RED). Implementation initially needed the missing pyo3::prelude::PyResult import (compiler defect, repaired without changing assertions). Final unchanged focused command exited 0: **7/7** passed, including nested two-stage binary64 0.1×0.3×0.7 oracle, 160-row 0.29 served/remainder sharing, a Mixed interval split with time/birth signs, offset/time rewrites, 20,000 operator depth without recursion, invalid fraction/handle rejection, and streaming versus materialization exact bit signatures. The test oracle uses original PacketParts::pack and original portion where applicable, not only the shadow implementation itself.

**Admitted evidence:** bounded original-operations shadow IMPLEMENTATION-VERIFIED in the tested range. The actual full original V03 code is still eager and would consume Vec<EventRow> and incoming Vec<Vec<Part>>. Neither a city-scale RSS speedup nor an exact overall V03 checkpoint result follows from these seven tests. Need C6–C10 for Rust workspace regression, resource/memory microbenchmark, source-identity-bound calendar readiness and full scientific claim gate.

**Source identity:** source ancestry 8e891b907f3f85e9ae8ff7c86a1b8836f4341815, stage C1–C4 pushed in four exact commits with verified remote SHA. This C5 stage is pushed only after new module compilation and full cargo regression; original main and PR41 remain unchanged.

## C6. 소프트웨어 회귀검증·디버깅

After the C5 RED→GREEN slice was pushed (SHA 9e820f986649d6a8d421d6d87000c36c3a697097), a fresh complete Rust library test command was run on the same source and compiler: RUSTFLAGS="-C link-arg=-lpython3.12" cargo test --workspace --lib --offline. Observed **71 passed, 0 failed, 1 ignored** (the ignore is a pre-existing opt-in selector benchmark). The new shadow tests contribute seven passing tests; all preceding original road/eager ordering tests remain green.

Bounded original V1 Python regressions (native packed interval, native road, storage policy, exact reductions, plan validator) ran **43 passed**. Cargo workspace test check finished successfully, Python theoretical-oracle script compiled, and original tools/v1_plan.py validate reports VALID_PLAN_NOT_RELEASE, 21 nodes, counts ACCEPTED=5, VERIFIED_SCOPED=14, BLOCKED=1, PLANNED=1, next_node=V03. These tests do not constitute full repository CI or the actual 3×3 full-day campaign.

**Error classification preserved:** The initial E0433 missing LineageArena was a deliberately failing behavior test; the later missing PyResult import was a compiler integration defect, repaired without weakening any existing test. No physical theory inconsistency or runtime floating-point failure was inferred from either compiler diagnostic. No modified original V03 native tick or build release acceptance was represented as PASS.

Evidence stored under artifacts/v03_fifo_lineage_coding_20261119/C6_{CARGO_TEST.log,PYTEST.txt,CARGO_CHECK.log,PLAN_VALIDATE.txt}. Scope gate: SHADOW_RUST_UNIT_IMPLEMENTATION_VERIFIED, ORIGINAL_V03_FULL_DAY_BLOCKED. No fitted micro rates, source demand, timing or resource threshold introduced in this stage.

## C7. 물리적·수학적 정확성 검증

Under the previous R5 per-row trace-induction theorem, each lazy operator applies exactly the old Part-level operation with the same IEEE rounding, row filter, input order and route/clock marks. This is **per-view operation equivalence only**, not an equivalence of different junction solvers or the original 24h V03 release.

Added three independent adversarial Rust tests to the existing 7:
1. A deterministic 17-step sequence over root sizes 1,2,19,61,160. At every step the shadow is compared against ORIGINAL eager PacketParts::pack+portion, using exact f64 bits for mass, birth, both endpoints and route/offset. The root of size 1 undergoes exact f=0 and verifies all subsequent empty states; sizes 2/19/61/160 remain nonempty and exercise 17 consecutive rounded transformations each; f=1 is explicitly tested at step10. Seed 0xF00D_2026_0019.
2. A source array with signed-zero endpoints, four different tags, distinct time support, a Scale then original interval Restrict then offset increment and time rewrite; the reference is calculated from independent eager loops using the original multiply-then-divide order.
3. A subnormal-mass input containing binary64 minimum subnormal and two subnormal units at f=0.5. The source's strict m>0 retention predicate is followed exactly, including dropped rounded-to-zero rows and original birth bits. No invented epsilon threshold.

Fresh Rust cargo library verification on this revision: **74 passed; 0 failed; 1 ignored**. The ten new shadow checks remain scoped to the private cfg(test) module. The original V03 conservative runtime/mass ledger is not substituted and no new traffic class parameter or demand coefficient was fitted. IEEE bit identity of this restricted operator language is IMPLEMENTATION_VERIFIED on the finite test population; full V03 physics/checkpoint identity on the new code path is UNTESTED because the path is not activated.

C7 exact-input identity, compiler version, tests and original source SHA are preserved in artifacts/v03_fifo_lineage_coding_20261119/C7_ADVERSARIAL_RESULT.json and C7_ALL_RUST.log. Next C8 benchmarks memory and actual computation separately, not treating the idealized O(P+E) theorem as observed wall/RSS.

## C8. 정확도·표현 용량·시간을 분리한 5회 성능 실험

A release-mode ignored Rust test executes the identical finite synthetic experiment five times in separate cargo invocations. A single 160-row immutable physical Part template is used by 8192 independent service events; each event's fraction f=((event mod 61)+1)/64 is a deterministic synthetic stimulus, NOT a fitted traffic parameter. The eager reference calls original PacketParts/portion twice for served and complement, retaining every output Vec<Part>. The append-only indexed arena stores only one immutable Base and two child Scale nodes per event. Both implementations visit all output rows and compute the identical ordered bits-based rolling checksum; equality asserted inside the executable benchmark.

Observed five-process medians (source-bound artifact C8_SYNTHETIC_BENCHMARK.json):
- Eager retained Part Vec capacity: 125,829,120 bytes, 2,621,440 logical copied Part rows.
- Shadow structural vector+base rows+view-ID capacity: 1,187,328 bytes with 16,385 DAG nodes. Capacity ratio 105.98×; these numbers exclude allocator metadata/peak RSS and the user of streamed outputs. They are NOT a measured whole-process memory saving.
- Representation construction wall: median eager / shadow ratio 229.41×. This reflects no per-event Part cloning, not throughput for a real physical V03 traffic step.
- Full per-row traversal cost: median (shadow emitted stream time / eager scan time) 0.998. Eager already holds the rows; the shadow still has to regenerate every logical row and preserve floating-point order. This is effectively equal at this synthetic scale, not an end-to-end speedup.
- Every one of five runs obtained the same bit-signature checksum for all 2,621,440 streamed rows, and the independently defined eager trace.

**Falsifiable conclusion:** one shared-template representation can greatly lower synthetic retained Part storage and creation cost without changing the per-row output bits; **but** original V03 still creates flat EventRow and incoming parts and retains full checkpoint state. Thus the result alone neither fixes the 25,600–25,650s packet genealogy explosion nor satisfies the full 100k/24h 8GiB/7200s resource gate. No new model coefficient, observed Chicago probe weight or traffic forcing was fitted. Need C9 review and a source-bound production-boundary acceptance decision.

**Precision and resource conditions:** only a fixed toolkit/test-runner/ABI and finite original Part inputs were tested. Structural bytes are an estimate from actual Vec capacities and size_of, not process peak RSS, allocator allocation count or complete native state. The ignored release test is deliberately excluded from ordinary cargo unit suites; five separate explicit invocations and hashes are retained.

## C9. 독립 오류 심사와 제한된 이벤트 소비 인터페이스

**Recovered interruption [verified].** At resumption, the isolated branch Git HEAD and GitHub remote were both 34cdeebdcfa15dd2d130b5c10846dd0decb651b6 (C8) and worktree contained only one uncommitted shadow Rust file with new C9 event consumer tests. The previous remote command had not executed: /tmp/v03_shadow_C9_EVENT_RED.log was absent, no cargo test process running. Running the exact focused test produced RED exit 101 due to missing visit_event_rows (E0599). No duplicate commit or speculative work completion was inferred.

**Conservative source-bound implementation.** A private, test-only LineageArena::visit_event_rows accepts (node_id, original source cell, destination resolver from each Part including path offset, finite event start/end, fallible consumer callback) and streams the original seven-field EventRow tuple directly. It preserves source iteration order, float mass/birth bits, event time signed-zero and route destination chosen by the supplied resolver, without allocating a Vec<EventRow> inside the adapter. Physical destination selection and start/end times remain external, because they are determined by the original V03 junction/event-rate solver. No original physical event generator or default traffic path was modified.

**Adversarial review and correction.** The first version test resolver used tag alone and did not establish offset-dependent routing, so it was strengthened to use both tag and offset. The consumer can explicitly return an error; streaming stops immediately and the immutable source can be retried. The existing downstream consumer is NOT transactional: side effects from rows emitted before an error require caller rollback or atomic staging. This is a documented integration blocker, not a solved property.

**Recorded test evidence.** The same focused command first failed with E0599 (missing method), then passed 3/3 without relaxing assertions: bit-exact eager-vs-streaming EventRow, invalid/nonfinite clocks, and early consumer-error propagation with source preservation. Fresh complete Rust unit library: 77 passed, 0 failed, 2 ignored. Selected original native/plan Python regressions: 43 passed; cargo check --workspace --tests --offline finished successfully. No hidden math or physical parameter fitting, no network/junction/GPS claim introduced.

**One review pass only.** Boundaries still missing:
1. Actual original V1Road::step_state builds Vec<EventRow> and incoming Vec<Vec<Part>>; no production route/ready/target conversion to shared expression API.
2. Source event time and destination mapping remain determined by original physical t+cursor, h, source tag/path offset and receiver constraints. The callback accepts supplied values and only verifies correct propagation.
3. Original checkpoint remains eager packet representation. Shadow structure has no versioned checkpoint, persistence or crash-recovery format.
4. In a deep chain visit() allocates O(D) operation scratch and does O(PD) reconstruction, even with O(P+E) retained nodes; the C8 benchmark covers shallow single-scale operations, not arbitrary growing lineages.

Thus C9 is EXACT_PART_TO_EVENTROW_SHADOW_STREAM_VERIFIED_SCOPED, not ORIGINAL_V03_NETWORK_FIFO_VALIDATED or RESOURCE_BLOCKER_SOLVED. C10 must refresh candidate source-native identity and original 3-city 100k calendar preparation before any 3/3 current-branch preflight credit. Full-day 0/9 BLOCKED.
