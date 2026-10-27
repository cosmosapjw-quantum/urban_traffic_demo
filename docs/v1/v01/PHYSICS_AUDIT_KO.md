# V01 한정 물리·관측 감사: release 판단 보류

## 관찰과 범위

| 관찰 | 실행 범위 | 상태 | 범위 밖 |
|---|---|---|---|
| freeflow | T04 210 m, 실제 PacketNetwork 수송과 해석해 21 s | PASS | 전역 shock 수렴 |
| collision/reference | T02 동질 latent reference와 mean-gap 반례 | PASS | 일반 pair hierarchy 폐쇄 |
| merge | T03 실제 flux와 3:1 물리 우선순위 | PASS | 보존으로 안전 증명 |
| turn | T03 pooled/독립 lane 및 봉쇄 반례 | PASS | 임의 geometry 충돌 인증 |
| signal | half-open signal에서 실제 event 시각 | PASS | 모든 network signal 설계 |
| closure | 양방향 교량 노드 창 반영 | PASS | 과부하 10k 하루 closure |
| cost error | T04 현 상태 자유흐름 ETA와 같은 link 실제 outlet | PASS | 주행 전체 조건부 분포 |

사전 고정 허용오차는 210 m 해석오차 ≤1 s, 시간세분 차이 ≤1 s, 한 링크
ETA와 입장 후 outlet 시간 차이 ≤0.25 s다. 후자는 실제 10.000 s 예측과
10.005 s outlet의 차이 +0.005 s다. 시간과 birth 기준은 명시적으로 맞춘다.

기존 packet quotient·birth 장부, 정보 지연·범위 paired worlds, 시간구간 수송,
경로 재명명/physical priority/Braess 테스트는 원본 구현을 재사용한다.
재명명은 물리 대칭이고 physical priority 변경은 다른 물리 입력이다.
Static Braess는 65→80 분 기준이며, 이는 dynamic traffic 실측이 아니다.

OVM ring에서 U'=1 s⁻¹, τ=2 s, k=0.1에 대해 characteristic root의
Re λ≈0.01272884 s⁻¹, residual≈3.1×10⁻¹⁷ s⁻¹을 확인했다.
이는 별도 조건부 연속 OVM 선형화 reference이며 V1 PacketNetwork의
성장률·안정성 인증이 아니다. 이 조건에서 반례가 없다는 가정을 넣지 않는다.

## 열린 release 문제

V02가 보존한 38개 synthetic 지도는 등록 portal 0개이고 각각 주민 100,000명의
등록 서비스 접근 CDF가 미지원이다. 주민은 삭제하지 않았다. 이 사실에 대한
**release 범위 잠정 P1 분류는 본 감사의 위험 평가**이며 별도 정식 심사 분류가
아니다. 이는 V01의 일곱 물리 fixture에서 발견된 물리 P1이 아니다. 그러나 V01의
`P0/P1 미해결 0` 조건을 현 시점에 입증할 수 없으므로 감사 exit code는 2,
노드 수용은 BLOCKED로 남긴다. 해결은 실제 city portal 등록·유효 접근 검증이나
별도 심사의 근거 있는 분류 결정이 필요하다. 예측·가상 boundary-door 분포를
등록 서비스 결과로 치환하지 않는다.

C02 10k closure의 추가 하루 실행도 자원 한도로 중단돼 결과가 없다.
이번 audit은 full FIFO, microscopic safety, 전역 V1 stability, shock convergence,
실도시 보정 또는 전체 CI·통합을 주장하지 않는다.

## 실행 증거

`artifacts/v1_v01_20261027/AUDIT.json`은 각 oracle 원시 관측과 일곱 항목을 수록한다.
`AUDIT_EXIT.txt=2`는 release blocker를 정확히 나타낸다. 동시 P01 수정 중 초기 결과는 소스 identity가 불확실했으므로 승격하지 않았다.
P01 동결 후 Python 3.12·3.13에서 각각 90개 한정 회귀를 다시 실행했고,
실행 전후 packet_network/transport SHA256 일치를 확인했다. Ruff는 PASS다. 테스트 성공 수를
release 조건의 대용으로 사용하지 않는다.
