# C8: 같은 25,710 s wire에서 다른 road allowance

**범위:** 기존 source·JSON·log의 read-only 분석. 실험·테스트·코드 변경 없음. HEAD `bec506abb5247e76e8f74e2846eedf9e1c5c501a`, repo `/home/cosmosapjw/urban_traffic_v03_bottleneck_theory_20261123`.

**확인된 결과:** allowance 차이 102,114,816 B는 journey 쪽 최대 구조비용 차이 34,038,272 B에 `WORKING_COPIES=3`을 곱한 값이다. 최대값을 만든 실제 input/current/pending owner와 stage/history allocation은 **UNRESOLVED**다.

두 receipt의 `trace.sites["road_work:timed incoming direct combine"]`는 동일한 25,710→25,720 s 계산을 비교한다. 아래 required·base는 `max_required`와 `terms_at_max.base`, allowance는 `limit_at_max`다.

| 항목 | checkpoint 재개 | fresh 0→25,710 뒤 계속 |
|---|---:|---:|
| 공통 dynamic pool T | 5,789,366,871 | 5,789,366,871 |
| Road allowance A | 4,952,574,903 | 4,850,460,087 |
| Journey 예약 T−A | 836,791,968 | 938,906,784 |
| 역산한 journey 최대값 (T−A)/3 | 278,930,656 | 312,968,928 |
| Direct-combine required | 4,925,817,240 | 4,925,982,264 |
| 그중 road base | 3,050,335,280 | 3,050,500,304 |
| 여유 / 초과 | 26,757,663 여유 | 75,522,177 초과 |

`v1_journey.rs:1455,1550–1565`의 정확한 계산은

`A = T − 3 × max(J_input, stages(current)+history_bytes, stages(pending)+history_bytes)`.

`phase_storage_allowance` (`:316–325`)가 위 차감을 수행한다. `journey_storage_bytes` (`:200–205`)는 세 StageQueue와 receipt-history 저장비용만 합하며 dense per-leg 배열은 제외한다. 따라서 allowance 차이는 **이 journey 최대값 항에만** 귀속된다. Event/incoming 비용은 해당 allowance 산식의 입력이 아니다.

Required 차이 **165,024 B는 road base 차이와 정확히 같다.** 두 direct-combine site의 `event_bytes=1,214,423,864`, `event_candidate_live_bound=652,902,864`, `incoming_actual_page_charge=661,058,096`, `incoming_rows=19,989,328`, `timed_incoming_control_bytes=8,228,096` 및 나머지 terms는 모두 동일하다. Base 차이를 만든 세부 road capacity/공유 항은 이 시점의 양쪽 분해가 없어 미식별이다.

동일 wire가 동일 allocation을 뜻하지는 않는다. Journey writer (`:1258–1289`)는 논리 행만 기록하고 reader (`:1293–1366`)는 StageQueue/ReceiptHistory를 다시 만든다. `v1_stage.rs:85–96`은 payload와 block-vector **capacity**를 비용에 넣고, decoded/filtered queue의 capacity 차이를 명시한다. `v1_history.rs:178–181`도 persistent prefix의 cached allocation 비용을 센다. 이것은 representation 경로 차이를 설명할 수 있는 source 근거이지, 이번 34,038,272 B가 특정 stage나 history에서 나왔다는 실측 증거는 아니다.

**집계 주의:** `phase_allowance:road step`는 후보별 terms를 기록하지 않는다(`v1_journey.rs:317`의 빈 terms). 재개 receipt의 그 site 최대값 955,831,728 B와 `road_base:components` 최대값은 **다음 25,730 s 시도**에 해당한다. 이를 fresh의 25,720 s 실패와 직접 비교하면 안 된다. 재개 log는 25,720 성공 후 25,730 transfer-candidates 실패, fresh log는 25,710 wire·ledger 일치 후 25,720 실패를 명시한다.

**다음 측정 위치 두 곳:** (1) `v1_journey.rs:1550–1565`, road allowance 직전에서 t·call-input 시각·J_input/J_current/J_pending·argmax와 각 owner의 세 stage 비용·history 비용을 기록한다. (2) `v1_engine.rs:1220–1233` restore 직후 및 `:1816` journey decode 직후의 같은 분해와 stage len/capacity/block count를 비교해 representation 차이가 들어온 경계를 찾는다. 현재 분석에서 새 계측은 수행하지 않았다.

**근거 identity:** journey blob `129be60fb2f9a4eaabeae71dd31be9b634cec38e`; engine blob `c9634f4876a0f02be437115ad4bb29d6c9b2229d`; stage blob `cb6c48a7fc3f6d0b481cbbe1a6bf732746680f06`; history blob `9920212dd0a0e3fa85e6ba2f73c536388809833b`. Receipt 경로는 `artifacts/v03_coding_reconstruction_20261123/`; `C8_keyset_continuation.json` SHA-256 `568d3cd9dcf3d3a6ce3997a9ddb09bb5970e5473f1479a17906d8d9f5505fdb1`, `C8_fresh_from_zero.json` SHA-256 `09f582cb77650db0c1d5cdec268f507aef968bb57490bc7378a1d8713c7d9d2c`. Fresh 최종 25,710 s wire와 재개 입력 wire SHA-256은 모두 `64b77baece5ba45fa0928d59b58d9f8f9fc2178bcd93542b05264736978733fe`다.
