# 지형·구역·인구 기반 집계 교통 연구 계획

2026-10-24. Base: 3d83db01e9d028578de857ab66d98bf7964a5e3c. 연구 branch 전용, production default 불변.

목표는 로컬 100000 주민 도시를 향한 다음 계산 단위다. 이번에는 그래픽·게임 비교를 하지 않고 sandbox의 작은 구조·수요·운송 시험을 수행한다. 100000 주민 stock, 시간별 person-trip, 자동차 점유율을 거친 vehicle-equivalent, 동시 active mass를 구분한다. Cities: Skylines보다 낫다는 비교 판정은 하지 않는다.

## 선택한 설계
기존 평면지도에 수계 색상만 추가하는 대신 명시적 지형 입력이 실제 도로 허용성과 개발용량을 제한하는 작은 environment compiler를 추가한다. 원격의 active_meso.py와 첨부 active_suffix는 다른 API다. 첨부 archive 2f325e19126b42be80bbff98fefa77230e476778a687da3293e37d316026b022의 active_suffix를 byte-preserved 연구 dependency로 복원하되 기존 파일은 덮어쓰지 않는다.

대안은 full procedural erosion/parcel economy, 기존 평면지도의 사후 색칠, 제한된 raster terrain와 stock-flow 결합이다. 마지막을 채택한다. 합성 입력과 authored prior를 실제 관측 calibration으로 부르지 않는다.

## 단계와 양성 종료조건
0. 실제 원격 refs·첨부 identity·정책 확인 및 이 계획 게시.
1. Terrain/수계/보호구역/경사와 명시적 bridge를 갖는 도로·구역 컴파일, 주거/일자리 용량 내 정확한 인구 stock 할당. 작은 반례/보존/연결성 시험 통과 후 source+tests+설계+receipt 게시.
2. 지형 도로 비용과 구역 인구/일자리에서 capacity-constrained 집계 OD 생성. 목적지 접근성, 도달 불가능한 쌍, intrazonal flow, person-to-vehicle 변환과 시간 profile을 명시. Source-only 변화, active collision closure, suffix 운송과 연결하여 경량 검증 후 게시.
3. 감사·회귀·100000 주민의 구성비용 및 작은 운송 시험. 실패와 미수송량을 보존하고 최종 결과·인계 게시. 각 단계는 동일 branch의 부모를 확인하고 fast-forward로만 갱신한다.

## 불변조건
순수 Python stdlib scientific core, JAX/GPU 없음. 개별 차량 ID 및 1대씩의 운동 적분 없음. 물리적 finite storage, 질량보존, 최소 이동시간, signal/incident 조건을 유지한다. Braess 악화를 자동으로 버그로 분류하거나 없애지 않는다. housing/job capacity 부족, OD infeasibility, 계산 budget 실패는 숨기지 않는다. 지형과 zoning은 교통 중 고정하고 slow land-use feedback은 이번 범위 밖이다.

## 검증 및 인계
RED/GREEN은 실제 공개 behavior 단위로 기록한다. 기존 active_suffix 검증을 필요한 범위로 재사용한다. native_subagent: NOT_RUN; 이번 host에 native delegation 도구가 없어 직렬 구현/CAS/수치 반례 검증을 사용한다. 독립 모델 심사를 주장하지 않는다. Python 버전·명령·exit·선택한 scientific scope·remote readback을 기록한다. 전체 저장소 CI와 local 100k full-day 성능은 별도 의무다.
