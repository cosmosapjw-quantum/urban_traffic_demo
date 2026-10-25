# I01 전체 저장소 통합

실행 기준은 `PLAN.json`이다. 이 노드는 수송 법칙을 추가하지 않는다.

- 공개 API: `metroflow.v1`의 접근법칙·여정·PacketNetwork.
- 설치 진입점: `metroflow-v1 capabilities` 또는 `python -m metroflow.v1 capabilities`.
  이는 지원 API를 조회하며 아직 미구현인 하루 시뮬레이션 실행기로 오인시키지 않는다.
- 전체 호환 프로필: `python -m pytest -q` (기존 공용 conftest 사용).
- V1 프로필: `python -m pytest -q tests/v1 tests/test_v1_access.py tests/test_v1_birth_contract.py tests/test_v1_journey.py tests/test_v1_plan.py tests/test_packet_quotient.py tests/test_area_observables.py`.
- 독립 import: `PYTHONPATH=src python -S -c "import metroflow.v1"`.
- 도시 재현: `python -S tools/run_v1_foundation.py --prepare-inputs --out artifacts/v1_replay`.
  이전 커밋에 누락된 세 입력을 원래 seed17/resolution42/8000m로 재생성한다.
  지도의 byte identity와 시간측정값을 포함하는 growth JSON의 byte identity는 구분한다.
- CI의 기존 Python 3.12.14 전체 프로필을 유지하며, 별도 3.12.14/3.13.16 wheel 설치·V1 검증을 필수 ci-gate에 연결했다.
  모든 설치는 기존 ci-constraints.txt를 소비한다. 선택적인 Rust/JAX/GPU/oracle 미설치는 skip으로 보고한다.

기존 HEAD의 원격 CI는 lint에서 실패해 첫 테스트 shard가 실행되지 않았다.
고정 Ruff 0.16.2로 2,100건을 재현했다. 116개 파일의 최초 형식 정리는 AST 불변을 확인했다.
그 뒤의 import 정리·lambda 함수화·모호한 지역변수명 변경은 별도 검토했다.
38개 변경 과학 모듈에서 import·lambda 표기·지역변수명을 정규화한 본문 AST가 원래 HEAD와 일치했다.
기존 공개 import 이름은 명시적 재수출로 보존했다. 독립 실행 도구의 src 경로 설정 뒤 import만
정확한 사유와 함께 E402를 국소 명시하며, 전역 lint 규칙은 완화하지 않았다.

최종 실행·환경·한계는 `artifacts/v1_i01_20261025/RECEIPT.json`에 기록한다.
bootstrap 병합 전 네 노드를 ACCEPTED로 올리거나 M02/T02를 실행하지 않는다.
