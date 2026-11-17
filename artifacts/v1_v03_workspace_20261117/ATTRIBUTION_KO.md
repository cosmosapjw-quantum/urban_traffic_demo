# Road interval 행 증가의 귀속과 bit 동일 병합 가능성 (선택 a)

2026-11-17 · Valley weekday s7, guard 우회 진단 build(비-campaign), 25,000s 이후 50s 단위 호출.
원자료: [attrib2_valley.json](attrib2_valley.json)(조정 계수), [attrib_valley.json](attrib_valley.json)(병합 census),
요약 [ATTRIBUTION.json](ATTRIBUTION.json). 계측 코드는 tracing이 꺼진 campaign build에서 아무 일도 하지 않으며,
설치 build에서 legacy 점유 구간 checkpoint `ef4719a8…`가 3회 동일했다.

## 관측: 무엇이 행을 만드는가

25,600→25,650s 50초(5 tick) 동안 road cell part가 약 7.2 M 행 늘었다.

| 원천 | 행 |
|---|---:|
| **head packet 부분 서비스**(served 조각과 remainder가 모든 행을 각각 보유) | **+7.21 M** |
| entry interval 분할의 추가 행 | +2.07 M |
| 새 offer | +0.77 M |
| entry combine 병합 | −0.59 M |
| sink | −0.46 M |

| 50s 구간 끝 | 평균 cell parts | 평균 packet | 부분 서비스 수 | 50s 처리 wall |
|---:|---:|---:|---:|---:|
| 25,450s | 1.11 M | 21 k | 903 | 5.1s |
| 25,500s | 1.91 M | 38 k | 2,524 | 9.2s |
| 25,550s | 3.20 M | 64 k | 7,370 | 13.6s |
| 25,600s | 5.63 M | 111 k | 17,097 | 25.7s |
| 25,650s | 10.98 M | 210 k | 44,852 | 91.3s |

부분 서비스되는 head packet은 평균 약 160행(최대 약 880행)으로 커지지 않는다. 늘어나는 것은 **packet 수**다.
부분 서비스 한 번마다 head는 남고 downstream에 모든 행의 사본 packet이 생기며, 그 사본이 다음 cell에서
다시 interval로 나뉘고 다시 부분 서비스된다. 이 되먹임으로 packet·행·부분 서비스 수가 50초마다 약 2–2.6배 늘고,
같은 구간의 계산 시간도 함께 늘었다.

## 관측: bit 동일 병합으로 줄일 수 있는 상한

- entry combine은 이미 같은 `(tag, offset, a, b)`를 병합한다(약 2.3%).
- 인접 interval packet `[a,b],[b,c]`의 행 중 94%가 같은 `(tag, offset)`를 갖지만, 시간 밀도 `mass/(b−a)`가
  bit 단위로 같은 행은 **1.9%**뿐이다(25,700s 구간 40.9 M 중 0.79 M). 밀도가 다른 조각을 합치면 이후 분할 결과가
  달라지므로 bit 동일이 아니다.
- road의 합산은 정확 반올림 fsum이라 packet 내부 행 순서는 결과 bit에 영향이 없다. 따라서 저장 순서 변경이나
  복사 없는 지연 표현(공유 행 + scalar 곱 연쇄)은 bit 동일하게 만들 수 있다. 그러나 bit 동일성을 유지하면
  tick마다 논리 행 전체를 계산해야 하고, 논리 행 수 자체가 지수적으로 늘어 7,200s wall도 넘는다.

## 결론

bit 동일한 병합·저장 변경으로 회수 가능한 양은 수 % 수준이며, 증가 기제(부분 서비스마다 새 time-interval
packet 생성)를 멈추지 못한다. 선택 (a)는 **원인 귀속에 성공했으나 bit 동일 해결책은 없다**는 음성 결과다.

해결은 다음 중 하나의 사용자 결정이 필요하다(모두 physics contract 심사 대상, 이번 작업에서 미구현):
1. **실수 산술에서 정확한 비례 표현:** 같은 source에서 나온 부분 서비스 조각은 모든 행에 같은 비율 `f`가
   곱해진 동일 조성이다. packet을 "조성 + 총질량 + 구간"으로 저장하면 실수 산술에서는 같은 해이지만
   부동소수점 bit는 현재와 달라진다. 수치 동등성(허용오차 정의 포함)을 새로 검증해야 한다.
2. **조성 단위 FIFO 집계:** 같은 cell·같은 조성의 인접 구간을 시간 분포 모멘트로 합치는 근사 — 시간 binning과
   가까우므로 현재 금지 범위에 해당할 수 있다.
3. V03 수용 범위 재검토.
