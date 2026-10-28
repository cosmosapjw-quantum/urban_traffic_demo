# V03 전체 calendar driver와 고정 운영 재고

기준은 `dc0efbade8cc6d536dcecd072680f41a5d5672fc`의 V03 공동 실행 구현이다. 완료율은 19/21이고, V03의 최종 수용은 세 실제 100000 주민 지도에 대한 로컬 86400초 실행·자원 계측·수치 대조·저장/재개 증거를 요구한다. 이 문서는 그 기준을 바꾸지 않는다.

## 전체 calendar와 하나의 도로 상태

고정 calendar C의 모든 leg를 구성하는 연산을 M, 완성된 경로 registry를 G=M(C), 한 번의 도로 갱신을 F_G라 두자. registry가 실행 동안 불변인 현재 계보에서 합법적인 실행은 하나의 상태 X에 반복하여 X_{k+1}=F_G(X_k)를 적용한다. calendar page는 M의 메모리·구성 순서 단위다. 서로 다른 page별 X를 만들고 결과를 더하면 공유 receiving/storage 공급이 중복된다. 기존 V03 실제 반례에서 독립 실행 합산 도로 재고는 1.8 veh, 공동 실행 재고는 0.9 veh이었다. 따라서 이 driver는 페이지별 독립 교통 실행을 구성하지 않는다.

이 단계의 건설적 선택은 **전체 registry 사전 활성화**다. 모든 leg가 예산 안에 들어오면 전체 calendar를 먼저 구성하고 하나의 JointReleaseRuntime을 생성한다. 이는 점유 상태에 새 경로를 동적으로 삽입하는 online activation을 구현했다는 뜻이 아니다. 두 방법은 구분된 구현 경로이며, 사전 활성화 방식도 유한 전체 calendar를 실제로 실행하는 완결된 방법이다.

calendar의 폐쇄형 leg 수 N과 materialization 예산 B에 대해 N>B이면 교통 상태를 만들기 전에 자원 실패를 반환할 수 있다. 이 실패의 보존 대상은 schedule identity, offset 0의 calendar cursor와 정확한 잔여 사람·차량·화물량이다. N≤B이면 전체 registry와 완성 cursor를 하나의 checkpoint에 결합해야 한다. 동적 advance 중 자원 실패가 나면 실패 이전의 유효한 공동 상태와 같은 calendar cursor를 보존해야 한다. 실패 후 일부 page가 독립적으로 완료된 것으로 표시되는 상태는 허용하지 않는다.

정확한 독립 OD의 저장을 인수분해하는 것은 calendar를 저장하는 비용을 줄인다. 그것만으로 모든 동시 물리 경로·접근·귀가 영수증의 수가 작아진다는 결론은 나오지 않는다. 실제 세 입력의 전체 leg 수는 하천 5,093,765, 해안 2,449,750, 계곡 918,450이며 귀가를 별도 leg로 센 값이다. 이는 resident stock이 증가한 값이 아니다. 사전 활성화 예산 실패는 해당 입력·표현·예산에서 관측되는 자원 결과이며, 모든 가능한 수송 표현에 관한 불가능성 정리로 확대하지 않는다.

## 운영 재고의 의미

bus fleet와 freight depot는 passenger OD에서 역산한 숨은 공급으로 만들지 않는다. 새 inventory는 고정된 합성 정책에 따른 명시적 모델 입력이다. 실제 등록 출입구와 합법 route를 사용하고, 고정 departure·capacity·dwell 및 depot identity를 기록해야 한다. 태그 순서는 inventory 재현 식별용이며 교통 공급 우선순위를 추가하지 않는다.

inventory가 전체 OD를 운송한다고 가정하지 않는다. 운행 뒤 남은 승객·미배정 서비스·화물·접근/이탈 중 수요는 기존 정량 장부에 남는다. road-stop arrival과 destination egress 완료를 구분하는 공동 runtime의 계약을 그대로 사용한다.

## 로컬 수용 영수증의 조건

최종 로컬 수용에는 다음이 모두 필요하다.

- 원본 map archive·portal patch·calendar·inventory·source identity가 고정되어야 한다.
- 세 case 각각 3회의 실제 86400초 실행이 있어야 한다. preflight, 구성 페이지 또는 작은 fixture의 성공으로 이 실행을 대신하지 않는다.
- 각 실제 실행의 CPU/RAM/OS/Python 및 thread 환경, wall time과 peak RSS를 측정한다. 목표는 wall≤7200 s, peak RSS≤8 GiB다.
- source/road/access/egress 및 waiting/unreleased/unassigned/completed 장부를 유지하고, 전체 calendar를 포함하는 보고 모집단을 명시한다.
- 같은 입력의 짧은 refined-dt 대조와 실제 checkpoint에서의 중단 없는 실행 복원 동등성을 확인한다.
- 자원·입력·수치·구현·호스트 실패를 분리하고, 실패 시 마지막 유효 상태 또는 실행 전 전체 미구성 calendar를 보존한다.

전체 저장소 CI와 PR 통합은 사용자 지시대로 별도 심사 후 수행한다.

## 연구·코딩 루프 연결

R1–R3에서는 AGENTS와 PLAN의 V03 계약, 불변 route registry, 기존 공유 공급 반례 및 calendar identity를 재사용했다. R4–R5에서는 불변 registry에 맞는 전체 사전 활성화와 예산 전검사를 선택했고 위 단일 상태 합성 관계를 정리했다. R6은 독립 코드 검토에서 단일 runtime 소유권, cursor와 상태의 identity 결합 및 실패 원자성을 확인한다. R7의 실제 테스트와 실입력 결과, R8 판정은 아래의 실행 근거 절에 기록한다. R9–R10은 이 문서와 해당 receipt의 재개점으로 연결한다.

C1–C5는 기존 ReleasePlan·JointReleaseRuntime을 재사용하는 driver와 독립적인 명시 inventory 구현에 대응한다. C6–C8은 관련 회귀·전체 유한 calendar의 저장/재개·실제 큰 입력의 자원 실패 보존을 실제 명령으로 검사한다. C9는 별도 검토자가 코드와 실행 결과를 대조한다. C10의 게시 commit과 전체 V03 판정은 부모 실행자의 PLAN 및 receipt를 따른다.

## 실행 근거

독립 검토자는 `release_driver.py`와 `release_inventory.py`를 읽고 두 Python에서 다음 명령을 실제 실행했다.

```sh
.venv/bin/python -m pytest -q tests/v1/test_release_inventory.py tests/v1/test_release_driver.py
.venv313/bin/python -m pytest -q tests/v1/test_release_inventory.py tests/v1/test_release_driver.py
```

각각 6개 테스트가 통과했다(3.12: 0.46 s, 3.13: 0.33 s). driver의 3개 검사는 전체 유한 calendar의 사전 활성화와 tick당 단일 road 갱신, occupied checkpoint 저장/복원 후 연속 실행 동등성, 초과 calendar의 enumeration 이전 거절 및 정확한 잔여량, 하위 runtime의 마지막 유효 상태를 driver binding에 감싸는 자원 실패를 확인했다. inventory의 3개 검사는 registry 순서 재배열 불변성, 실제 등록 route 검사, policy identity와 잘못된 입력 거절, 인구·기회량을 바꿔도 fleet을 수요에 맞춰 늘리지 않는 조건을 확인했다.

검토된 유한 driver와 inventory 범위의 중대 미해결 지적은 발견하지 않았다. 현재 driver는 plan page의 route/access 구성 결과를 runtime 조립 때 재사용하지 않고 다시 계산하므로 중복 구성 비용이 있다. 이는 이 단계의 성능 제한이며 독립 page 교통 실행으로 바뀐 것은 아니다.

로컬 캠페인 CLI 검토에서는 같은 output label에 남은 이전 receipt를 실패한 새 child 뒤에 읽을 수 있는 경로를 발견해 부모 실행자에게 전달했다. 현재 수정된 소스는 task-owned 기존 label을 child 실행 전에 제거하고, 성공 receipt의 child exit·case·step·horizon·matrix SHA 일치를 검사한다. 따라서 전달한 지적은 이 수정 범위에서 닫혔다. CLI의 중간·최종 계측 출력은 로컬 최종 수용과 별도이며, refinement와 최종 review를 실제로 닫기 전에는 V03 완료를 선언하지 않는다.

실제 준비 실행은 `artifacts/v1_v03_driver_20261027/CAMPAIGN.json`과 각 `*.prepare.json`에서 확인했다. 입력별 결과는 다음과 같다.

| 사례 | 전체 leg 수 | 사전 활성화 예산 | 남은 leg 수 | 실제 결과 |
|---|---:|---:|---:|---|
| river weekday seed17 | 5,093,765 | 20,000 | 5,093,765 | BLOCKED_RESOURCE |
| coastal weekend seed41 | 2,449,750 | 20,000 | 2,449,750 | BLOCKED_RESOURCE |
| valley weekday seed7 | 918,450 | 20,000 | 918,450 | BLOCKED_RESOURCE |

세 receipt 모두 cursor offset 0, materialized amounts 0, simulated time 0을 기록하고 전체 잔여 calendar량을 유지한다. 준비 wall time은 각각 18.68, 10.98, 17.24 s였으며 이는 24시간 수송 성능 측정이 아니다. 이 예산 검사는 service factory 호출 이전에 수행되므로 해당 준비 receipt만으로 실제 세 도시의 inventory route 검증까지 실행됐다고 주장하지 않는다. inventory 정책은 stop 최대4개, 고정 departure 6시·9시·12시·15시·18시·21시, capacity40명, dwell20초로 명시되어 있다. 추가 실제 inventory 실행은 같은 디렉터리의 `INVENTORY.json`에서 별도로 확인했다. 세 도시 모두 실제 등록 출입구의 고정 stop4개, 단일 departure별 별도 차량으로 센 bus run24개, 명시 depot1개가 구성됐고 합법 route 검사가 통과했다. 이 결과는 OD 수송이나 fleet 수용량 충분성을 주장하지 않는다. 입력 원본/patch SHA와 도시·inventory identity가 각 case에 기록돼 있다.

이 유한 테스트와 준비 실패 근거는 미실행 로컬 캠페인의 통과를 예고하지 않는다. 다음 수치·표현 연구는 이 exact 사전 활성화 예산 실패를 원래 입력의 결과로 보존하면서 진행해야 한다.

최종 CLI 지적 수정의 회귀는 `tests/v1/test_local_campaign_cli.py`를 별도로 실행해 두 Python에서 각각2개 통과했다(3.12: 0.22 s, 3.13: 0.58 s). 기존 성공 label이 남아 있고 새 child가 실패하는 반례에서도 이전 성공을 재사용하지 않는다. 최종 소스·receipt 결합과 게시 identity는 부모 실행자의 최종 영수증을 따른다.
