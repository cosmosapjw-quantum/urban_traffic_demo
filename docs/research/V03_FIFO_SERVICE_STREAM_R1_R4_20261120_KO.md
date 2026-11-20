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
## R5. 불변 조성의 Arc 소유권 공유 정리와 오차·자원 범위

Original PacketParts carries two representations: Uniform{common PackedTime a,b; Vec<CorePart>} and Mixed(Vec<Part>). All original update/partial-service operations build a NEW PacketParts from owned Part rows and then replace the packet.parts slot; no source routine mutates a previously packed row Vec in place. Thus an immutable Arc<Vec<CorePart>> or Arc<Vec<Part>> can replace the Vec value without changing any row payload or iteration order. All read-only PartIter views unpack identical original row fields, including signed-zero endpoints. Clone operations Arc::clone the immutable backing Vec, retaining the same row bits. This is a semantic ownership refinement, not a new traffic model or fitted coefficient.

**Theorem AS-1 (clone-read observational equivalence).** Let V be a finite immutable array of Part/CorePart with fixed original source order, and let k≥1 packet snapshots hold references Arc(V). If every physical update either (a) reads V or (b) constructs a new array V' and replaces only that owner, then each snapshot's Part iteration yields the identical row sequence it would have yielded under eager deep clones of V. Proof: Arc::clone does not modify V; reading indices 0…P−1 is invariant under changing the number of references; replacing a value in one owner changes only its pointer and cannot mutate V still owned by others. The physical generator, routing and original accumulator see the same rows and hence, given fixed operation ordering, identical f64 results.

**Theorem AS-2 (bounded structural storage on shared snapshots).** P Part rows copied to k independent snapshot Vec buffers require Θ(kP) row words; k Arc handles to one immutable Vec require Θ(P+k) row words/handles plus O(k) pointer/control metadata, *if* no owner mutates the shared backing array and no additional unique V_i exists. This does NOT reduce the number of distinct Part arrays created by congestion-induced partial service, which may still grow rapidly, or force original checkpoint byte count to shrink. It also does not prove RSS drop unless the cloned snapshots actually coexist in the memory-heavy V03 path.

**Budget caveat:** the original retained-storage and working-budget formulas count each live packet's capacity conservatively as independent even when an Arc backing buffer is shared, so they do not silently widen original admission. This may overestimate physical memory and cause early resource refusal. The global 8GiB process bound remains authoritative. Any performance claim must compare equal original matrix, 100k residents and source-bound native SHA with actual peak RSS, time and full-state checkpoint bytes.

**Numerical caveat:** Arc introduces shared ownership but no rounding operation and no row merge. Changing clone allocation/failure timing changes resource-error behavior (even if successful output is identical), and cannot be called identical error-path semantics without a separate test. Payload correctness must be verified at actual original 25300s and 25600s checkpoints and physical ledgers. AS-1 and AS-2 are DERIVED conditional; present Rust unit tests establish only an implementation-scoped finite check until full native trials.
## R6. 불변 Arc 공유의 unique-allocation 계수 명제 (DERIVED)

한 RoadState의 packet 소유자 집합을 S, 각 packet p가 참조하는 실제 immutable Arc<Vec> backing 할당의 identity를 a(p)라 하자. backing별 명시적 capacity 비용을 B_a=cap_a×sizeof(Part 또는 CorePart)≥0이라 정의하고, n_a=#{p∈S:a(p)=a}라 두면 원래 debug_stats의 packet별 합산량은 Σ_p B_{a(p)}=Σ_a n_a B_a이다. 동일한 allocation identity로 중복 참조된 payload의 unique resident backing bytes는 Σ_a B_a이므로, packet별 합산과 unique 합산의 차이는 **Δ=Σ_a(n_a−1)B_a≥0**이다. 증명은 동일 backing identity별 단순한 partition/counting이다. Arc refcount/control-block, outer Vec, queue, in-flight snapshots과 allocator headers는 각각 별도로 상계해야 한다. 어떤 packet도 두 개 이상의 서로 다른 backing bytes를 하나로 identity 병합하면 안 된다.

실제 crates/metroflow-rust/src/v1_road.rs의 RoadState::debug_stats는 packet별로 out.vector_capacity_bytes += packet.parts.allocated_bytes()를 호출한다. packet.parts는 이제 Arc<Vec>를 공유하므로 **동일 RoadState 내 backing 중복 계상의 가능성은 source-supported**이다. 그러나 실제 RoadWorkBudget에는 state.retained_storage_bytes()와 retained_input_bytes의 max에 multiplier 3, event/incoming, interval_retained/transient, extra 및 native storage cap이 별도로 포함된다. Δ만으로 실제 fail 시점·초과량의 원인을 판별할 수 없다. Unique-count 기반 수정을 할 때에는 동시에 살아있는 input/committed/candidate state 사이의 공유 identity와 transient buffer 수명을 추적해야 하며, allocator 제약·안전 상한을 유지해야 한다. 임의의 budget 상향은 금지한다.

## R7. 서로 다른 packet genealogy의 출력량 하한 (DERIVED, conditional)

원래 표준 checkpoint writer가 N개의 서로 다른 (target,tag,offset,a,b,mass,birth) Part 기록을 실제로 직렬화해야 하고 모든 기록이 독립적으로 다른 값일 수 있다면, 해당 flat wire-format의 기록 출력에는 Ω(N) 단위 write/시간과 최소 Ω(N) 바이트가 요구된다. Arc 소유권 공유는 같은 backing을 가리키는 복제본의 메모리만 줄이며, 서로 다른 실제 부분 서비스/입력 구간 때문에 생성된 고유 Part마다 새로운 배열을 갖는다면 이 출력 하한을 바꿀 수 없다. 이전 C5와 현재 C9의 t=25600 checksum과 checkpoint bytes 866,763,962가 **완전히 일치**하는 것은 이 한정 구간에서 raw 직렬화 데이터가 줄지 않았다는 직접 관측이다. 하지만 원본 packet genealogy가 임의의 교통 미래에 지수적으로 성장한다는 전칭 정리는 이 관측으로 증명되지 않는다.

## R8. 25,600→25,650초 원본 동역학의 resource-counterexample (IMPLEMENTATION-MEASURED)

원래 full-city 100000 주민, 동일 original matrix/driver/time grid 및 **완전히 동일한 25,600초 초기 native checkpoint SHA**로 출발한 두 독립 소스-고정 run에서:
- non-Arc C5 old: FAILED_BudgetExceeded, phase=packet interval packing, required=5,242,810,432 bytes, native budget=5,242,806,391 bytes, excess=4,041 bytes; peak process RSS=3,640,336,384 bytes, wall=52.976s.
- Arc C6–C9: FAILED_BudgetExceeded, 동일 phase, required=5,242,811,264 bytes, 동일 budget, excess=4,873 bytes; peak RSS=3,273,211,904 bytes, wall=53.127s.
- Arc의 process peak RSS 절감은 367,124,480 bytes (10.085%), 하지만 수행시간은 약 0.2855% 더 길었고 양쪽 모두 25,650초에 도달하지 못했다.
- 두 경우 모두 실제 8GiB process address-space cap보다 훨씬 낮은 RSS로 멈췄다. 내부 보수적 structural/scratch budget 검사와 실제 kernel OOM은 구별해야 한다.

비트 동일성은 **초기 25,600초**에 대해서만 입증됐다. 두 run 모두 목표 시각 이전에 실패했으므로 **25,650초 최종 물리 상태/ledger/checkpoint의 equality는 검증되지 않았다.** 각각 어떤 더 이른 tick에서 실패했는지도 receipt에 기록되지 않아 동일 실패시각이라고 주장하지 않는다. Failure는 동역학 물리론의 반례나 질량비보존 증거가 아니라 현재 자료구조/예산하의 실제 실행능력 blocker이다.

## R9. 다음 판별실험과 수렴 조건

먼저 native source-locked 한 state에서 Arc backing의 pointer identity별 unique capacity, current packet-by-packet counted capacity, in-flight candidate 및 input-state와 공유되는 경계 버퍼, interval_transient/retained와 EventRow buffer를 각각 계측해 실제 BudgetExceeded 시 phase별 오차를 분리해야 한다. 보수적 native-work budget은 5,242,806,391 bytes로 **그대로 유지**하고, 모든 동시 live backing과 Arc overhead를 한 번씩 상계하는 새로운 admissibility bound를 도출·단위 테스트한 다음에만 예산 계산법의 수정을 허용한다. 단지 지금 4~5KB 초과했다는 이유로 budget을 늘리면 재현성·자원 준거 위반이다.

그 뒤 source-locked 25,600→25,650 old-vs-candidate 상태가 모두 성공할 때 checkpoint byte SHA, mass/birth, route FIFO, event clocks, actual peak RSS, wall 및 distinct logical Part count를 함께 비교해야 한다. 만약 unique-accounting으로 한두 tick만 진행하고 서로 다른 Part interval genealogy가 여전히 복제된다면, 다음 route는 prior R1–R10의 immutable marked-cohort lineage 및 압축 EventRow/incoming consumer를 실제 physical state/serialization 계층까지 확장하는 것이다. 무조건적 fixed-dimension BGK/MC-LTM substitution은 original V03 finite-response 물리/관측 계약의 동등성 증명 없이는 금지한다.

## R10. 연구 판정과 반증가능한 다음 작업

이번 루프가 성립시킨 가장 강한 정리는 source-conditional served-stream IEEE order equality (R2–R3), immutable Arc clone read equivalence와 idealized memory sharing bound (R5), 중복 backing-by-owner accounting identity (R6), flat raw output information bound (R7)이다. 측정은 25,600초 이전 원본 bit-identical physical state, C9에서 peak RSS -7.69%/elapsed +4.60%, R8에서 **실제 kernel failure 두 건 및 peak RSS -10.09%/elapsed +0.29%**다. 단일 실행으로 통계적 성능 우월을 추론하지 않는다.

**Stop/claim gate:** scoped optimized composition clone correctness IMPLEMENTATION_VERIFIED, 100k city preparation 3/3, V03 original 24-hour×9 complete 0/9 BLOCKED, release RLS01 PLANNED, authoritative DAG 19/21. 본 source-bound 음성 결과를 코드/실험 영수증과 함께 게시하고 R/C 연구 루프를 일단 닫는다. 다음 최소 코딩 ID는 V03-FIFO-UNIQUE-ACCOUNTING-01: conservative unique Arc backing budget derivation + adversarial in-flight ownership tests + original 25600→25650 recovery; 모든 mutable packet semantics, 물리 hazard, route priority, FFT/transport/time-step와 수용 상한은 고정한다.
