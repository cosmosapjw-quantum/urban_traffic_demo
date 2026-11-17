# V03 공동 상태 장부 검사 비용

2026-11-16. 노드 상태는 **19/21 (90.5%)**이며 V03의 전체 도시 실행은 아직 차단 상태다.

## 원인과 동일성 조건

기존 `JointReleaseRuntime.check`는 leg마다 모든 ingress/egress/internal 기록을
다시 검색하고 모든 bus/freight service index를 다시 검색했다. 달력 leg 수를
`L`, 접근 단계 기록 수를 `A`, service record 수를 `S`라 하면 이 부분의
검색 비용은 `O(L(A+S))`였다. 실제 64개 internal leg의 유효 상태에서 tag 비교가
4,160회 발생하여 선형 비교 예산 640회를 초과하는 행동 회귀를 먼저 확인했다.
초기 수집은 다른 병렬 작업의 새 계측 모듈이 아직 생성되지 않아 import에 실패했으며,
이 환경적 중간 상태는 행동 RED에 포함하지 않았다.

각 tag에 대해 기존 생성식

```text
fsum(e.mass for e in entering + egress + internal if e.tag == tag)
```

이 소비하는 수열을 `entering → egress → internal` 순서 그대로 한 번 분배한다.
그 수열에 동일한 `math.fsum`을 적용하므로 float 합산 순서와 값이 유지된다.
egress-only 검사도 독립적으로 같은 순서를 유지한다. bus/freight index는 생성 시
leg별로 모으되 원래 service 순서를 보존한다. 이는 물리 cohort 병합이 아니다.
각 leg의 요청량·원래 birth moment·완료·미완료·귀가 자격과 개별 service 장부를
기존과 동일하게 검사한다. 상태·checkpoint schema·model identity는 바뀌지 않는다.

변경된 부분의 검사 비용은 `O(L+A+S)`, 상태 검사 동안 필요한 추가 임시 저장량은
`O(A)`의 mass 참조 목록이다. 생성 시 역색인은 `O(S)`이다. road 검사·receipt
순회·전체 달력 물질화 등 다른 비용은 이 개선의 범위 밖이다.

## 직접 검증

`tests/v1/test_joint_release_runtime.py`의 7개 테스트가 Python 3.12.14와 3.13.5에서
각각 통과했다. 검사는 단일 physical step, 귀가 자격, destination egress,
원래 birth moment, 물리 class 장부, checkpoint 저장/복원, internal-only 상태를
포함한다. 이번 회귀는 선형 tag 비교 예산, 전체 질량은 유지하며 두 tag를 바꾸는
변조 거절, 한 leg에 속한 여러 departure window와 tied fleet service를 모두
검사하는 경우를 추가했다. Ruff도 통과했다.
별도 독립 검토에서도 순서·multiplicity·identity·실패 조건에 관한 구체적 결함을
발견하지 못했고, 같은 7개 테스트를 추가 실행하여 통과했다(0.62 s).

재현 명령:

```sh
.venv/bin/python -m pytest -q tests/v1/test_joint_release_runtime.py
.venv313/bin/python -m pytest -q tests/v1/test_joint_release_runtime.py
.venv/bin/python artifacts/v1_v03_joint_cost_20261116/benchmark.py
```

benchmark는 기준 commit `b41f807c490dda12e036bcb40d9c13370f04223e`에서 원본 검사
함수를 읽고 동일한 실제 유효 상태에서 기존/변경 함수를 5회씩 짝지어 실행한다.
1,500 legs와 1,500 active stage records에서 평균 검사 시간은
`0.0576485538 s → 0.0074861466 s`였다. 이는 약 7.70배의 이 한정 검사 가속이며,
전체 tick·프로세스 RSS·전체 도시 24시간 결과로 외삽하지 않는다.
4 tick의 최종 상태가 정확히 같았고, checkpoint 바이트와 복원된 상태도 같았다.
질량 보존 tag 변조는 두 함수가 같은 오류로 거절했다.

원시 측정값과 검사 결과, 원본·변경 source SHA256은
`artifacts/v1_v03_joint_cost_20261116/RESULT.json`에 보존했다.
달력 20,000-leg 한도·실제 release 입력은 유지하며, 전체 CI·통합은 사용자 지시에
따라 보류한다. 이 결과만으로 V03 또는 RLS01을 완료 처리하지 않는다.
