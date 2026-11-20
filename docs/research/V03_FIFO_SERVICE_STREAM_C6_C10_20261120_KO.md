# V03 FIFO service-stream / immutable composition · C6–C10 evaluation (2026-11-20)

Authority: previous C1–C5 measured negative temporary-scratch result and C6/C7 derived immutable Arc sharing + verified 81 Rust / 50 Python tests; frozen PLAN 1.1.26, original 100k ×3×3×24h contract, original binary budget 8GiB process/7200s wall. Source branch research/v03-fifo-service-stream-20261120. Original main/PR41 untouched.

## C8. Current Arc native binary 3-city 100k calendar preparation

The C7 Arc-backed original PacketParts was built as native Rust release binary SHA256 aafd80fa786df68ce007f6a025c3b469dd2b5dcd699a6b7203f0a12d84bce9c9 from candidate source SHA256 983d2f0829c46666e4412d83308ee9fe5ed1930677b3795f4d7d19642abca74a. The previous pre-Arc binary and source SHAs are DIFFERENT and get zero preparation credit on this native. All three original rust_whole 100k residents/day/seed inputs were prepared again without reduced population, changed demand, source parameter fitting or relaxed resource/tolerance.

| City/day/seed | 100k source planned legs | Actual prepare wall [s] | Worker peak RSS [GiB] | Bound source |
| River weekday s17 | 5,093,765 | 71.403 | 2.022 | WHOLE_CALENDAR_PREPARED |
| Coastal weekend s41 | 2,449,750 | 40.661 | 1.038 | WHOLE_CALENDAR_PREPARED |
| Valley weekday s7 | 918,450 | 23.063 | 0.416 | WHOLE_CALENDAR_PREPARED |

Total planned legs 8,461,965 across three independent model cases. Each source receipt has the EXACT live Arc native binary, source and matrix SHA, signed status and measured resource identity; original tools/research/v03_readiness.py and independently written v03_arc_readiness.py verify **3/3 CURRENT native whole-calendar preparation**, 19/21 scoped project DAG, V03 predecessors 3/3, **0/9 full-day accepted and V03 BLOCKED**. The old pre-Arc receipts are rejected 0/3 for the new binary. Plan validator remains VALID_PLAN_NOT_RELEASE and the host's 31.25GiB RAM is not the 64GiB baseline reference; process 8GiB and 7200s limits remain unchanged.

This C8 outcome is a successfully executed original whole-native **source and input preparation prerequisite**, not an actual physical traffic run. The decisive physical benchmark is C9: load old source-matched native checkpoint at t=25300 into this new Arc binary, verify source/receiver/mass/calendar identity and re-save old 25300 bytes identically, then execute 25300→25600 under original source and compare old/non-Arc vs Arc entire 25600 checkpoint, wall and peak RSS. Source and output are not allowed to fit new rates or accept approximation.
## C9. 원본 25,300→25,600초 Cross-binary replay와 실제 메모리 측정

현재 Arc-backed native 바이너리에서 이전 C5 served-stream non-Arc의 Valley 100,000 주민 t=25,300 체크포인트를 로드한 후 재저장하여 동일한 SHA-256을 확인했다. 이어 실제 original rust_whole 물리식·signal·turn·receiver·clock 및 8GiB process limit을 유지하며 t=25,600까지 진행했다. 이전 C5 reference와 최종 전체 checkpoint SHA-256 및 모든 vehicle/person/cargo ledger가 완전히 같았다. Final checkpoint SHA는 75bae0ea200a0bd3fd0842770efd0cecec9ce6297179149db88f77ded91b134d, 파일 크기 866,763,962 bytes, 판정 BYTE_IDENTICAL_SCOPED. Python independent replay tests 3개 통과.

Source-locked 한 번씩의 원본 물리 실행 결과:
- 이전 non-Arc process RSS: 2,054,717,440 bytes (약 1.9136GiB).
- Arc candidate process RSS: 1,896,656,896 bytes (약 1.7664GiB).
- Peak RSS reduced by 158,060,544 bytes, reference 대비 7.6926%.
- 이전 elapsed 57.9808s; Arc candidate elapsed 60.6488s, 약 4.6016% 느려짐. 양쪽 모두 source-plan rebuild+binary load 포함. 반복 실행 분포는 아직 측정되지 않음.
- 최종 checkpoint raw bytes는 같고 serialized logical packet 크기는 전혀 감소하지 않음.

**과학적 verdict: IMPLEMENTATION_VERIFIED_SCOPED_BIT_EXACT, MEASURED_MEMORY_BENEFIT_ONLY_WITH_SLOWER_WALL.** 사용자의 동시 속도+메모리 개선 수용조건은 불충족. Arc clone 저장소 공유는 특정 중복 backing snapshot을 줄이지만 distinct per-event Part genealogy의 폭증은 제거하지 못한다. 신호·입력률·micro hazard·외부 data fitting을 변경하지 않았다. 25,600→25,650 구간의 추가 original source-matched 검증 없이는 혼잡 병목 구간 전체에 대한 일반 성능결론을 내리지 않는다.

관련 FIFO 표현 준거: Bar-Gera & Carey (2017), https://doi.org/10.1016/j.trb.2017.02.002. Cohort bundle의 형식적 FIFO sufficiency는 이 Arc 소스 구현의 bounded runtime/memory를 증명하지 않는다. 원래 21개 DAG 중 19개 scoped complete, source-native whole-city input 3/3 prepared, full 24h acceptance 0/9, V03 BLOCKED는 유지한다.
