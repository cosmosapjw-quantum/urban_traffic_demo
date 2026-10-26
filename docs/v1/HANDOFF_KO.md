# V1 I01 검증 이후 인계

repo: cosmosapjw-quantum/urban_traffic_demo
integration: research/v1-integration-20261025
bootstrap: v1/foundation-access-journey-20261025
plan: docs/v1/PLAN.json 1.0.1
PR: https://github.com/cosmosapjw-quantum/urban_traffic_demo/pull/25

AGENTS.md, PLAN.json, I01_INTEGRATION_KO.md, artifacts/v1_i01_20261025/RECEIPT.json을 먼저 읽는다.
실제 HEAD와 병렬 변경을 확인한다. `python tools/v1_plan.py validate`와 `next`를 실행한다.

I01 구현 소스 b7ff813504b4a4e1beb97cb51f7d43ce33deb338은 CI run 40182521270의 최종 gate까지 통과했다.
Python3.12 전체 CI 회귀: 1818 passed, 41 skipped, 3 xfailed. 두 Python V1 profile은 각각45 passed다.
로컬 작업공간 회귀:1814 passed,41 skipped,3 xfailed. 이 수를 CI 수와 합산하지 않는다.
후속 증거·계획 문서 커밋은 src/tests/tools/pyproject.toml/.github 바이트를 바꾸지 않는다.
현재 bootstrap은 병합하지 않았으므로 P00/M01/T01/I01은 VERIFIED_SCOPED이며 next_node=I01이다.
같은 소스에서 next가 I01이라는 이유만으로 전체 감사를 반복하지 않는다. 남은 작업은 실제 bootstrap 병합이다.
현재 사용자는 push까지 요청했다. 이후 병합 작업이 승인되면 actual merge SHA와 evidence를 확인하고
네 노드를 함께 ACCEPTED로 갱신한 뒤 PLAN 위상 순서의 후속 노드 하나를 선택한다. M02/T02를 선행하지 않는다.
최종 main merge와 release tag는 별도 사용자 승인 전 실행하지 않는다.

과학 코어 진입점은 metroflow.v1이며 설치 CLI는 metroflow-v1 capabilities다. 하루 실행기는 아직 미구현이다.
기존 도시 재현 입력은 `python -S tools/run_v1_foundation.py --prepare-inputs --out artifacts/v1_replay`로 재생성한다.
그 결과는 과거2veh 사례의 관측과 일치하며 10만 배경 주민의 교통이나24h 실행이 아니다.
물리적 모델·수치 근사·표현 중복을 구분하고 기존 PLAN의 수용문턱·WIP=1을 유지한다.
