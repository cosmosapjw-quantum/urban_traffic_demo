# 지지집합을 보존하는 진입 측도 투영

기준: `0b9caa8cc60a3ba087722e0360b997c5dfb61d62`, 2026-11-17.

## 결정과 권위

현재 사용자가 최신 보고서의 선택지를 원래 모델의 동기에 맞게 선택하고 실제 이식하라고 요청했다. A(명시적 수치 근사)를 선택한다. 전체 주민·수요·24h 목표, 유한응답 운동, 저장공간, 차량 종류·목적·경로와 장부는 유지한다. B(FIFO 물리 규칙 교체), C(규모 축소)는 선택하지 않는다. 과거 무조건 시간 집계 금지는 이 이름 있는 선택적 정책에 한해서 대체한다. 정확 경로를 기본값 및 비교 oracle로 보존하며 수용 오차나 완료 상태를 변경하지 않는다.

## 구현 계약

정책명 `entry_projection_support_v1`, 폭 `entry_projection_width_s > 0` (초). 0은 기존 정확 경로다. 정책과 IEEE-754 폭 bit를 모델/checkpoint identity에 포함한다. 기존 비영 상태에 정책을 끼워 넣지 않는다.

한 cell의 한 admission step에서 동일한 운동 target을 갖는 incoming 측도만 투영한다. 전역 원점 0의 폭 h 격자에 다음 경계를 추가한다.

1. 양의 interval들이 가지는 즉시 다음 movement(다음 lane group 또는 sink)의 **지지집합이 바뀌는 시각**.
2. 원래의 모든 point admission 시각. 서로 다른 시각은 별도 순서를 유지하고, 동일 시각의 atom들은 기존의 한 exchangeable packet으로 보존한다.
3. 입력의 처음과 끝. 기존 driver의 신호·폐쇄 경계는 서로 다른 admission step으로 이미 분리된다.

모든 endpoint의 elementary packet을 만들지 않고 endpoint sweep으로 support-change 경계만 추출한다. 각 입력 interval을 위 경계에서 적분한 뒤 각 segment의 `(tag, remaining route)`별 질량 M, birth moment B, entry first moment E를 합산한다. Part는 `M, B, entry_start=entry_end=E/M`를 보관한다. 하나의 segment는 하나의 FIFO cohort packet이다. 원래 point packet은 그 시각에서 양의 다음 interval cohort보다 앞선다. 서로 다른 tag·class·route를 하나의 Part로 합치지 않는다.

이 정책은 segment 내부 순서를 유한 해상도로 근사한다. 같은 segment 안의 즉시 movement support는 일정하여 open-only head 뒤에 blocked turn이 새로 섞이는 단순 반례를 막는다. 분기율 변화·후속 경로 분기·신호 민감성은 여전히 근사 오차를 만들 수 있다.

## 보존과 오차

각 segment와 tag에 대해 질량과 원래 birth 1차 모멘트, 진입시각 1차 모멘트를 실수 산술에서 보존한다. 부동소수점은 기존 장부 허용오차에서 검증한다. 양의 부분만 적분하며 임의 질량 cutoff를 사용하지 않는다. 부분질량이 float에서 0으로 underflow하면 명시적으로 실패한다.

tag별 입력시간 지지구간 [a,b]와 조건부 평균 μ에 대해 `W1(ν,M δ_μ) <= M (b-a)/2 <= M h/2` (veh·s)다. 이는 **이번 투영의 국소 시간측도 비용 상한**이며 network travel-time 오차나 누적 궤도 bound가 아니다. 진단의 재실행·rollback·checkpoint 지위를 명시한다. 폭 refinement와 dt refinement를 별도로 비교한다.

## 실행할 작업

- Python 독립 projection oracle 및 PacketNetwork 연결, 질량·모멘트·support 반례·시간경계 검사.
- Rust 동일 알고리즘을 실제 V1Road incoming 경로에 연결하고 byte/record guard·실패 원자성을 유지.
- NativeWholeEngine / Python frontend / local campaign CLI까지 선택적 정책을 연결하고 identity 격리.
- 정확 경로 회귀, Python/Rust 대조, 압축·오차·refinement 실험, checkpoint replay.
- 실행 증거와 수정된 PLAN, 이론 유도 및 local agent 명령·반환 계약 보존. 전체 CI·merge·release와 3×3 24h 성공은 실제 수행 전 미완료로 유지.

## 검토 초점

tiny blocked movement, future route divergence, point atoms, high absolute clocks, invalid/under-resolved widths, byte-budget failure, zero-width exact replay, incompatible checkpoint identity를 실제 검사한다. 실제 도시에서 support 전환이 너무 많으면 해당 비용을 보고하며 경계를 제거해 성공으로 바꾸지 않는다.
