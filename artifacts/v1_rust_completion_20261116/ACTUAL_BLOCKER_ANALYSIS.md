# 실제 campaign의 남은 resource blocker

2026-11-16 · 읽기 전용 분석 · 후보 commit `532effe32f90c20cf3cbc1de350d0e7267f52584`.
근거는 `runtime_budget_campaign/CAMPAIGN.json`, 세 도시의 `*.run1.json`, 동일 commit의 `v1_engine.rs`, `v1_journey.rs`, `v1_road.rs`다. 세 실행 모두 candidate-source SHA `65bd00608c6546a2895d2b7e12aa1aab4ee71587205fe98c398be887b5e48179`, native binary SHA `3e06969385dffdb9834c56d2cf0831e67e07e618df4f1f2169cff974aa9a3972`에 결속된다.

**결론 — 관측·소스 확인:** 세 도시의 첫 실행이 모두 `BLOCKED_RESOURCE`로 끝났다. 실패 candidate는 commit되지 않았고 아래 시각의 마지막 유효 상태를 보존했다. 현재 blocker는 물리 ledger 오류나 관측 RSS 8GiB 초과가 아니라, 현재 저장 표현과 보수적 동시 수명·workspace admission의 경계다. 후속 반복·resume·refinement 9건은 `NOT_RUN_DEPENDENCY_BLOCKED`; 24h 완주 및 refined 검증의 성공 증거가 아니다. 전체 CI·통합은 사용자 지시에 따라 보류 상태다.

| 사례 | 마지막 유효 시각 | 실패 guard | 요구 bytes > 해당 allowance | 초과 bytes |
| --- | ---: | --- | ---: | ---: |
| River weekday s17 | 25,350s | checkpointability | 3,187,741,149 > 3,135,452,254 | 52,288,895 |
| Coastal weekend s41 | 32,660s | entry interval split | 3,803,788,656 > 3,803,738,862 | 49,794 |
| Valley weekday s7 | 25,600s | packet interval packing | 5,333,479,128 > 5,333,475,127 | 4,001 |

| 마지막 유효 상태의 관측값 | River | Coastal | Valley |
| --- | ---: | ---: | ---: |
| Journey entering | 8,938,145 | 7,402,019 | 2,282,814 |
| Journey egress / internal | 25,030 / 83,131 | 453,224 / 76,590 | 1,077,150 / 70,763 |
| Receipts / 전체 Journey records | 76,125 / 9,122,431 | 193,082 / 8,124,915 | 554,941 / 3,985,668 |
| Road parts / packets | 2,210,205 / 19,091 | 6,035,911 / 102,539 | 8,049,883 / 158,498 |
| Service last events | 612,218 | 2,128,610 | 3,145,131 |
| Peak RSS bytes (GiB) | 2,787,835,904 (2.596) | 2,539,757,568 (2.365) | 2,114,449,408 (1.969) |

**River — checkpoint 검증·decode reserve:** 전체 accounting budget 6,442,450,944 B에서 fixed retained/dense/scratch 3,306,998,690 B를 뺀 단일 shared pool은 `T=3,135,452,254 B`다. commit 직전 `Q=3R*+3J*+3E*+max((V_whole−B)_+,V_road_decode,64 KiB)`가 `T`를 49.87MiB(1.67%) 넘었다. `R*`,`J*`는 알려진 input/current/candidate와 canonical decode footprint의 최대, `E*`는 input/current/new event storage의 최대, `B=461,213,867 B`는 이미 fixed에 포함한 call binding이다. 실패 구간 25,350→25,360s에서 entering 생성 807,562, retire 498,545, candidate entering 9,247,162행이었다. 전체 candidate는 9,455,127 records다. 마지막 유효 Journey의 97.98%가 entering이므로 단순 receipt-history 누수라는 설명은 맞지 않는다.

**River의 보수 상한을 소스에서 계산:** candidate stage 9,369,938행과 전체 leg 5,093,765개를 사용한 `whole_validation_scratch_bytes`의 stage-map 분기는 가능한 key 수를 `min(stage rows,all legs)`로 잡는다. 두 HashMap과 expansion Vec의 성장·공존 상한은 이 x86-64 실행에서 **2,058,634,424 B**, 이미 계상한 `B`를 뺀 reserve는 **1,597,420,557 B**다. 이는 실제 map allocation 측정치가 아니다. Receipt가 `Q`의 모든 항을 개별 기록하지 않으므로 owner별 정확한 기여율은 확정하지 않는다.

**Coastal·Valley — road의 phase workspace reserve:** 둘 다 `road_step`에서 실패했다. Journey prepare 후 entering은 각각 7,443,510행과 2,288,396행이었지만 owner에 commit되지 않았다. `RoadWorkBudget::require`는 기존 owner/candidate 기반 reserve에 service event/sink 공간, incoming workspace, 누적 interval 분할행의 `3×sizeof(Part)` 및 해당 allocation의 extra를 합한다. Coastal의 `interval()`은 새 구간의 행 수를 `interval_rows`에 더하고 실제 split Vec를 할당하기 전에 guard한다. Valley의 `pack_parts()`는 Uniform packet을 만들 때 raw `Part48`와 새 `Core32` 배열이 공존하는 추가 공간을 할당 전에 guard한다. 표의 allowance는 다른 살아 있는 owner를 차감한 **해당 phase 예산**이지 전체 6GiB나 RSS 제한이 아니다. 초과량이 작다는 사실만으로 약간의 예산 변경이 24h 완주를 보장한다고 해석할 수 없다.

**해석의 한계·미구현 가능성:** 옛 constructor 추정치를 runtime에서 차감하고 owner에 고정 반분하던 false quota는 현재 원인이 아니다. 지금은 실제 retained 자료와 알려진 수명을 계상하는 shared pool이지만, 공유 payload의 logical-owner별 중복 계상과 보수 workspace 상한이 남아 있다. 이 accounting은 actual RSS의 엄밀한 상계 정리도, 같은 수요의 24h 실행 불가능성 증명도 아니다. Exact stage-law batching, 공유 allocation을 인지한 workspace 계상은 **미구현·성능 이득 미검증** 후보이며, float/FIFO/row 순서·checkpoint 의미·실패 원자성 보존 검증 없이는 해결책으로 확정할 수 없다. 이번 분석에서는 코드·정책·예산을 변경하지 않았다. River fresh-load/byte roundtrip은 root의 별도 진단 receipt로 판정하며 이 campaign 결과에서 성공을 추정하지 않는다.

Receipt SHA-256: River `bd8312daa99d145dfb238730828f7a8822a2ba80a0ace066ff5c1903daba6108`; Coastal `2b7be6e647f6232c8f836b7a8e32f8a8076f56ec96375bbe4ad136c52c2610b0`; Valley `b70036f8b12f629bf750a43259b036b413f2e5a0feac040eb1bfb8a148e01716`.

## 실제 복구 확인

`river_fresh_recovery.json`에서 새 프로세스의 load/report/byte roundtrip이 검증됐다. 원본과 재저장 SHA-256은 `e179f3b9b5b9081a8adb121e51761514654743a8e8bbe4166691dd04cc46425e`로 같다. decode 후 capacity는 달라질 수 있으며 실제로 별도 진단은 25,360s까지 한 tick 진행했다. 이 사실은 guard 경계가 물리적 불가능 시각이라는 해석을 배제하며, 원래 campaign의 25,350s last-valid를 소급 변경하지 않는다.
