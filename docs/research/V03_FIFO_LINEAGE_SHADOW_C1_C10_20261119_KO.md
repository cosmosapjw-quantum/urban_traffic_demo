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
