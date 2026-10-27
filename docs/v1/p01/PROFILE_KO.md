# P01 한정 프로파일·정확 축약

실제 C02 합성 10k 평일 86400s 입력의 cProfile에서 PacketNetwork.check 누적 20.0s,
empty 링크를 포함하는 finite-response motion.advance 누적 5.8s가 확인됐다. 프로파일
전체 50.2s는 계측 오버헤드를 포함하므로 실제 기준 wall 비교에 사용하지 않는다.

FiniteResponseMotion의 빈 링크는 원래 dx=0, speed=0, latent=()를 반환한다. 기존 링크에
packet이 없고 해당 motion이 이 항등법칙을 명시할 때만 그 결과를 직접 사용한다. 이미 저장된
입력 대기열은 축약하지 않고 같은 시간경계에 뒤이어 입장한다. 패킷이 존재하면 기존 T02
운동과 passage 함수를 그대로 실행한다. 동일 모델과 입력에서 최종 TransportState 전체,
입출 event·birth moment·class·latent·관측이 원래 코드와 일치하는 실제 테스트를 둔다.
임의 motion에 조건을 추정해서 적용하지 않는다.

동일 입력 10k 하루의 별도 프로세스 3쌍에서 wall 평균은 기존 12.42s, 변경 11.22s,
표준편차는 각각 1.03s와 1.79s다. 외부 작업 부하가 통제되지 않았고 세 번째 쌍은
역전됐으므로 이 소규모 표본으로 안정적 속도 향상을 확정하지 않는다. 각 실행의 관측
전체는 wall/RSS 필드를 제외하고 정확히 같다. 원시 개별 wall/RSS는 PAIRED.json에 있다.

원래 foundation 실제 2veh 면적접근 fixture를 이전 source와 변경 source에서 재실행했다.
둘 다 최대 290 records, 평균 333.411064005s이고 trace·관측이 resource 필드 외 동일했다.
이 fixture는 T02 motion을 쓰지 않으므로 이번 축약은 이 기록 수를 줄이지 않는다. 기존
20,000 record budget은 그대로이며, 동일 fixture에서 한도를 289로 설정하면
BLOCKED_RESOURCE와 직전 유효 JourneyState(t=304s, 미완료 약1.994467veh)를 보존한다.
서로 다른 entry 시간/물리 법칙을 합쳐 숫자를 맞추지 않는다.

100k 24h wall·RSS gate는 실행하지 않았고 V03의 실제 실측에 남는다. 이 결과는 합성
두 구역의 10k 입력에 대한 한정 구현·측정이며 전체 CI나 최종 수용이 아니다.
