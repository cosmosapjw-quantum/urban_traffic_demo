# C01 원자적 WorldState 실행·체크포인트

WorldState는 T04 TransportState의 실제 packet/queue/latent/출생·유출 모멘트/event,
R01 InformationState, R02 RoutingState, phase journal, 완료 비용 관측과 결정 제안을
immutable 값으로 소유한다. CitySnapshot의 canonical JSON과 TripSchedule 객체도
선택적으로 소유하며 제공된 입력의 identity를 검사한다. 입력이 없는 toy는 명시적
synthetic LaneGroupContract와 T04 고정 flux schedule을 사용한다.

fast phase는 유일한 T04 transport를 진행한다. medium clock은 과거 완료 route 표본을
관측하고 R01이 허용한 링크 비용으로 R02 후보를 계산한다. route 평균을 링크 평균으로
분해하지 않는다. 실제 완료 표본과 링크 prior는 서로 다른 관측 필드에 남는다.
slow phase는 그 tick의 medium publication 전 snapshot을 읽는다. AccessibilitySnapshot의
completed_veh는 관측 예제이며 토지 이용 접근성 점수 또는 M04 입지 법칙을 대신하지 않는다.

advance 호출은 전체 WorldState transaction이다. 예산·수치·모델 실패 시 입력 checkpoint를
예외에 붙이고 부분 world를 내보내지 않는다. graph_edit는 점유·pending·미래 수요가 있으면
DRAIN_REQUIRED를 반환한다. drain 후 READY_TRANSACTION descriptor를 반환하며 실제
새 CitySnapshot/TransportModel 생성은 명시적 다음 transaction이다. 점유 링크를 지우거나
기존 차량량을 삭제하면서 graph를 hot-swap하지 않는다.

checkpoint는 허용 목록 dataclass와 tuple만 복원하는 JSON이다. 임의 import/pickle 실행을
허용하지 않는다. schema/입력 identity/phase clock/수송 보존 검사를 통과해야 로드한다.
save는 임시 파일 flush/fsync 뒤 atomic replace한다. Runtime.run은 최대 simulation900s
간격과 마지막 시각에 실제 파일을 저장한다. 실제 host 중단 뒤에는 마지막 완전 파일을
--resume으로 읽는다. host 중단 자체를 실험한 것은 아니며 저장·로드 및 연속 실행과의
정확 일치가 검증 범위다.

`python -m metroflow.v1 run --scenario toy_day --resume-check`는 60s synthetic fixture를
중간에서 실제 JSON 저장/로드하고 중단 없는 실행과 WorldState 전체를 비교한다.
--checkpoint PATH, --resume PATH, --until S, --out PATH를 지원한다.
이름 toy_day는 작은 진단 fixture이며 24h 도시 실행·100k 성능을 주장하지 않는다.

현재 runtime은 이미 동결된 T04 flux를 실행한다. D01 calendar를 실제 도시의 road source에
연결하는 자동 조합과 매 medium 후보를 실제 inflight suffix에 적용하는 정책은 아직 없다.
TripSchedule retention을 그 자동 결합 완료로 해석하지 않는다. 전체 도시 조합은 C02,
실제 느린 입지 법칙은 M04에서 소비할 표면이다. renderer와 과학 core는 분리되어 있다.
