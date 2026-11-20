# V03-FIFO-UNIQUE-ACCOUNTING-01: source-locked theory and code

Parent SHA c76e4712bac41b8c089844c842bc6ce55c782501; isolated research/v03-fifo-unique-accounting-20261120 branch. Authority docs/v1/PLAN.json v1.1.26, unchanged original main, PR41 and physical model. Release: 100000 residents/city, 86400s/day, 3 cities x3 repetitions, 8GiB process cap, original internal road-work cap 5242806391 bytes, 10s step. No fitted coefficients or reduction of original transport demand.

## R1. Exact measured failure and hypotheses

Original source crates/metroflow-rust/src/v1_road.rs: PacketParts Uniform holds Arc<Vec<CorePart>>; Mixed holds Arc<Vec<Part>>. RoadState::debug_stats counts packet.parts.allocated_bytes once PER OWNER even if Arc owners share the identical allocation. The work-budget formula charges max(retained current, retained input) times 3, plus event, incoming, retained/transient interval and extra. Thus owner-counted bytes may conservatively overestimate physical retained backing, but the original work budget also needs headroom for other live states and scratch.

Source-locked actual 100k Valley 25600->25650 tests from the same initial checkpoint SHA 75bae0ea200a0bd3fd0842770efd0cecec9ce6297179149db88f77ded91b134d:
- old non-Arc FAILED_BudgetExceeded: native required 5242810432, budget 5242806391, excess 4041 bytes; peak RSS 3640336384 bytes and elapsed 52.976s.
- Arc FAILED_BudgetExceeded: required 5242811264, same budget, excess 4873 bytes; peak RSS 3273211904 bytes and elapsed 53.127s.
Neither reached 25650, so checkpoint/ledger at 25650 unverified. Actual process RSS did not exceed 8GiB. Hypotheses to discriminate: duplicated Arc owners inflate a particular structural estimate; packet genealogy creates distinct allocations anyway; scratch/events dominate; and crossing a conservative internal bound is distinct from actual system OOM.

## R2. Exact unique allocation accounting lemma

For a finite set S of simultaneously live packet OWNERS and each p in S, let a(p) be the allocation identity from Arc pointer identity, B_a=Vec capacity(a)*element-size(a) [bytes]. Define n_a as number of owners that reference a. Then

Owner-summed O = sum_p B_{a(p)} = sum_a n_a B_a.
Unique-payload U = sum_a B_a.
Difference D = O-U = sum_a (n_a-1) B_a >= 0.

Proof: partition the finite owner multiset by allocation pointer identity, count each same backing once in U and n_a times in O. Distinct Arcs whose payload bytes are identical must remain different allocations; an empty Arc with Vec capacity zero still needs its Arc header allocation. This is exact for the stated Vec capacity payload and the enumerated owner set, NOT an exact process RSS estimate or a bound on all allocator metadata. Across current/input/candidate simultaneously live RoadStates, de-duplicate identities across the union and add each independent state shell, Vec owner slot, Arc control block, free-list reserve and working buffer.

Conditional bound: if at most three complete RoadState snapshots coexist and each corrected per-state accounting C_i upper-bounds all state payload+metadata, then sum_i C_i <= 3 max_i C_i, and the unique union <= sum_i C_i. This follows from elementary nonnegative inequalities; it requires proving the actual lifetime/capacity assumptions for the phase and accounting separately for incoming, events, interval_retained, interval_transient and extra. Therefore this lemma does NOT authorize reducing the original storage budget check yet.

## R3. Computer-science/physical semantics and falsifiers

Arc::ptr_eq or Arc::as_ptr identifies actual shared backing, unlike comparing Part payload values. Official Rust reference: https://doc.rust-lang.org/std/sync/struct.Arc.html . Every original Part remains (tag,offset,mass,birth,entry-times), and original FIFO/junction/kinetic rates and IEEE operation order remain frozen. Persistent packet-sharing gives no universal guarantee of bounded memory with distinct time-interval genealogy or full-network FIFO; related strict cohort bundle theory: H. Bar-Gera and M. Carey (2017), https://doi.org/10.1016/j.trb.2017.02.002.

Falsifiable probes: count distinct Arc backing pointers and owner-multiplicity at t=25600; validate per-owner sum equals legacy debug_stats payload contribution; measure unique bytes and potential difference. Snapshot alias observed only in input/committed/candidate but not one snapshot would favor a cross-state treatment, whereas numerous genuinely distinct Part roots and large transient/event buffers would limit improvement. No gate alteration until source-verified, adversarial tests and physical source-bound trials establish a conservative new upper envelope. Default V03 remains 19/21 scoped, full calendars 3/3 on parent branch, full day 0/9 BLOCKED.


## R4. Exact structural native-work decomposition at failure (derived + directly measured)

Existing v1_trace::guard is enabled by METROFLOW_BUDGET_TRACE=record, which does NOT change its original physical or budget decision. The observed failed C5 original 100k Valley 25600->25650 replay has RoadWorkBudget::require(required, phase='packet interval packing') and exact source formula:

required = base + event_bytes + incoming_rows × 2 × (sizeof(Part)+sizeof(Mark)) + interval_retained + interval_transient + extra.

On x86_64 this exact native struct identity has sizeof(Part)=48, sizeof(Mark)=32, so incoming row charge=160 bytes/row. Actual terms at the exceeded guard:
- base 1,980,005,976 bytes (37.77%).
- event_bytes 2,047,480,928 bytes (39.05%).
- incoming_rows=6,751,471, charged 1,080,235,360 bytes (20.60%).
- interval_retained 131,126,880 bytes (2.501%).
- interval_transient 3,955,912 bytes (0.075%).
- extra 6,208 bytes.
Their exact integer sum is 5,242,811,264 bytes, against the unchanged internal budget 5,242,806,391 bytes, excess 4,873 bytes. Wolfram Language and independent Python integer arithmetic both reproduced the sum. This is a structural resource-check equation, not an equation for actual RSS; event_bytes and base are conservative concurrent owner/scratch envelopes, not measured resident heap.

The trace also reports 498,636 packet-packing guard calls and 836,307 entry interval split guard calls in this bounded failure, 44,852 partial-service events and 23,901,798 split output row occurrences; these are actual counters under record tracing, not complete V03 full-day rows. They support that the distinct lineage and output materialization paths remain active. Even proving safe deduplication of 257,596,256 bytes from two live Arc-backed snapshots would NOT by itself prove that the 2.05GB event and 1.08GB incoming structural reserves are physically eliminable or that 25,650 can complete with a fixed resource gate.


## R5. Disjoint Arc pair credit as a rigorous lower bound

For the simultaneously live supplied snapshot S and committed owner C, match their packet owner slots by cell/pending index. For every matched pair (p,q), credit B=capacity(Arc<Vec> backing)×element size only if Arc::ptr_eq of identical storage type holds; otherwise credit zero. Because no owner slot participates in more than one index-matched pair, the resulting matching edges are vertex-disjoint. For each shared allocation with n live owners, the total owner-charge redundancy is (n−1)B, while at most floor(n/2) matching pairs are credited; floor(n/2)≤n−1 for n≥2. Hence the sum D_pair of matched-pair credits cannot exceed the true redundant payload due to shared backing among C and S. This remains valid when each state internally has repeated references or when identical content is stored in different allocations, because only actual Arc pointer identity generates a credit.

**Conditional three-state bound:** Let original source-budget state upper envelope M bound the retained payload + metadata of each complete live supplied/committed/candidate RoadState, with all additional event/incoming/interval scratch charged separately as in original source. Then the actual unique retained bytes of those three owners are at most 3M-D_pair, preserving all separately charged scratch. Proof: sum three per-owner bounds ≤3M, and remove only the lower bound D_pair on duplicated physical backing bytes. This is a valid mathematical tightening under the stated phase-lifetime and completeness hypotheses. It is not yet a universal theorem about every native whole-engine control state: the original 3M envelope is an engineered conservative assumption whose complete phase ownership/scratch proof remains dependent on original implementation. If committed snapshot storage exceeds M, or the current/supplied clock mismatch, refuse any experimental credit.

The C7 implementation is **opt-in only** through METROFLOW_EXPERIMENTAL_ARC_PAIR_BUDGET=source_pair_only. Without the exact token, original RoadWorkBudget computes the unchanged 3M and original 5242806391-byte gate. With it, source adds D_pair-based admissibility only when same clock and the committed retained snapshot does not exceed M; the actual native limit and 8GiB process limit are unchanged. Source still must be independently checked for any unaccounted transient allocations, so successful opt-in runs cannot automatically be promoted to accepted release. Time complexity: O(number of corresponding packet slots) without heap allocation for pointer pairing, excluding the original retained_storage_bytes scans. No physical coefficient or FIFO event arithmetic changes.


## R6. 엔진 전체 예산과 동적 road phase allowance의 구분

원본 v1_engine.rs의 pool_after(reserved, phase)는 기준 pool에서 다른 소유자/phase의 reserved를 뺀 양을 실제 road phase allowance로 제공한다. 따라서 **동일한 사용자 설정 8 GiB process cap과 동일한 native policy**라도 원래 물리 state와 다른 소유자 reserve가 달라지면 개별 road-work 단계의 허용량이 바뀔 수 있다. 실제 25,600초에서 실패한 phase cap은 5,242,806,391 bytes였고, 25,650초 이후 실험의 transfer 단계에서 관측한 cap은 5,264,781,391 bytes였다. 차이 21,975,000 bytes를 사용자가 예산을 올린 것처럼 단정하는 것은 오류다. C10의 raw error와 record-only trace를 원천으로 보존하고 source/phase를 명시한다.

**한정 정리:** 고정된 전체 pool P와 단계별 동시 reserved R_i에 대해 phase_allowance_i=P-R_i라면 P 불변과 allowance_i 불변은 동치가 아니다. 증명: 차분 allowance_2-allowance_1=R_1-R_2. 두 시점의 reserve가 서로 다를 수 있다. 이것은 source-level 산술 정리이며 실제 R_i의 모든 allocator lifetime을 자동 인증하지 않는다.

## R7. Arc deduplication과 원본 다중 상품 출력의 구별

이미 검증한 한 RoadState 내부의 중복 Arc payload는 25,600초에서 0 bytes였으며, committed+supplied 두 상태 사이 중복은 257,596,256 bytes였다. 25,650초 실험 성공 상태를 read-only debug_state로 조사한 결과 단일 상태의 owner_count=unique_backing_count=310,031, per-owner=unique Vec payload 528,923,200 bytes, 내부 중복 0 bytes. committed+supplied 두 상태의 owner_count=620,062, unique backing=310,031, payload 중복 528,923,200 bytes였다. 따라서 Arc sharing이 실제로 존재하지만, 서로 다른 packet 소유자/계보에 의해 생성된 **독립 backing 수**는 25,600초의 158,498에서 25,650초의 310,031로 늘었다.

**조건부 하한:** N개의 독립적으로 관측 가능한 route/offset/birth/entry-time Part payload가 기존 flat native checkpoint wire 형식으로 각각 직렬화되어야 한다면, 그 형식을 유지하는 writer는 Ω(N) row write와 크기가 고정된 row당 Ω(N) serialized bytes를 필요로 한다. 이 말은 새 별도 포맷의 entropy coding 자체가 불가능하다는 주장이 아니라, **기존 flat wire를 그대로 출력하면서 행 생성·저장 비용을 0으로 만들 수 없다**는 형식 종속 명제다. 실제 기존 체크포인트는 25,600초 866,763,962 bytes에서 25,650초 1,683,486,650 bytes로 1.9423배 늘어났다. 단일 50초 구간에서 일반적 시간에 대한 지수성은 증명되지 않는다.

## R8. 이어진 25,650→25,700초의 조건부 실험과 반증

동일 source/bin identity, 같은 100,000-resident Valley original physical driver, checkpoint SHA 89e3230b23b4423509f6036035e9b03c7299204b5d317cdb3f6226c5b0c53e8b에서 시작했다. 기존에 검증한 opt-in pair credit과 record-only tracing을 유지했고, 원래 8GiB process cap과 모델/코호트 입력은 변경하지 않았다. 실제 execution은 PHYSICAL_ADVANCE에서 FAILED_BudgetExceeded, phase=transfer candidates, required=5,264,847,112 bytes, **그 단계에서 동적으로 배정된 한도** 5,264,781,391 bytes, 초과 65,721 bytes였다. Peak RSS=3,445,784,576 bytes (3.2091 GiB), wall=31.720s. 25,700초의 완료된 물리 상태/ledger/native checkpoint는 **없다**.

기록된 transfer guard의 산술 분해는 base 1,742,656,808 bytes (33.10%), event_bytes 2,329,821,664 bytes (44.25%), incoming_rows 7,452,304 ×160 = 1,192,368,640 bytes (22.65%)이고 interval_retained/transient/extra=0으로, 정확하게 5,264,847,112 bytes이다. Event+incoming의 **보수적 structural envelope** 합계가 이번 guard 요구량의 66.90%다. 이들은 실제 할당되어 동시에 상주하는 heap 바이트와 동일하다는 주장이 아니며, 근본적인 과대계상 가능성을 모두 제거했다고도 주장하지 않는다.

## R9. 적대적 검토 및 다음 실행단위 수렴

검토한 반례는 (a) 같은 내용이지만 포인터 identity가 다른 두 Arc는 shared storage가 아니며, (b) snapshot 사이 공유를 packet 소유자 전체에 잘못 중복 공제하면 true distinct backing를 빠뜨릴 수 있고, (c) 현재 pair-match credit이 제어하는 것은 특정 두 owner의 중복 backing에 대한 lower bound일 뿐, 변하는 candidate·다른 engine snapshot·event/incoming live-set의 총 안전상한이 완전히 증명된 것은 아니라는 점이다. 따라서 C8의 25,650 성공은 수학적으로 **R5 가정을 명시한 조건부 실험**으로 기록해야 하며, native 기본 모드 릴리스로 승격하지 않는다.

C10의 25,700 실패는 다음 bottleneck이 event/incoming과 각각 독립적 packet interval lineage의 결합이라는 경로를 지지한다. 기존 포인터 deduplication만 반복해도 이들을 제거하지 않는다. 다음 검증 가능한 단위는 V03-FIFO-COMPOSED-EVENTS-01: 원본 7필드 EventRow와 incoming/Mark의 source-order, route/offset/birth/clock f64 연산과 junction priority를 유지하면서 참조형 event/mark 소비를 구현하고, 먼저 bounded seed/source 25,600~25,650 및 25,650~25,700 단계의 **논리행 수, 강제 materialization, source-bound byte/ledger, 실측 RSS와 wall**을 비교한다. checkpoint 포맷을 변경한다면 원래 wire bit-exact와 distinct versioned semantic-exact 계약을 분리한다. 본 데이터로 새 traffic coefficient를 fitting하거나 내부 한도를 숫자로 올리지 않는다.

## R10. 물리·계산과학 판정 및 종료조건

- DERIVED (조건부): source-order f64 보존, immutable Arc owner dedup identity O-U=Σ(n_a-1)B_a, 서로 다른 owner의 vertex-disjoint pair lower-bound, 기존 flat wire writer의 output size lower bound, dynamic phase allowance의 산술 구조.
- IMPLEMENTATION-VERIFIED_SCOPED: Rust pointer census의 RED→GREEN, source-bound 25,300/25,600/25,650 Arc backing 측정, C8에서 같은 source/bin의 default blocked와 2회 opt-in replay 25,650 byte-identical, 동일 8 GiB 및 기본 budget policy 유지.
- IMPLEMENTATION-BLOCKED: opt-in으로 25,650까지는 재현되지만 다음 목표 25,700에서 BudgetExceeded, 따라서 24h ×9 runs 완료 0/9, V03 BLOCKED, RLS01 PLANNED.
- UNRESOLVED: 모든 native 단계의 candidate/committed/input/scratch 동시 생존에 대해 실험식의 완전 안전성을 증명하지 않았으며, 독립 packet genealogy와 EventRow/incoming storage가 계속 증가함. 같은 실패 구간으로 예산 계상만 반복 보정하는 메타루프는 중지하고 실제 표현/이벤트 소비 개선으로 경로를 전환한다.

Authoritative PLAN 1.1.26의 scoped 완료 19/21(90.48%), V03 direct predecessor 3/3, 현재 소스의 전체 도시 달력 준비 3/3, 제한된 원본물리 Valley 25,650 성공 2회는 여전히 단일 도시 partial prefix이며 25,700 성공 0/1, 공식 전일 acceptance 0/9이다. 이번 범위에서 production main 및 PR #41은 수정/merge하지 않는다. 기존 자료와 코드로 완전히 증명되지 않은 지점을 실패의 종류대로 보존하고 다음 C1 실행 계약을 분리한다.
