# Urban Traffic Demo: 최신 결과 감사와 보존적 진입시간 투영

작성일: 2026-11-17 (KST). 감사 기준은 `v1/v03-acceptance-20261027`의
`0b9caa8cc60a3ba087722e0360b997c5dfb61d62`다. 개선 작업은 별도
`research/conservative-kinetic-closure-20261117` 브랜치에서 진행한다.
최종 소스·실행 identity는 이 작업의 통합 영수증을 따른다. allocation 교정을
포함한 마지막 Rust binary의 SHA-256은
`b34832c7803e5ca2be5e7c1a1f83c2d2a83faf29ca7d7956e4943a01f1ce57a3`다.

## 1. 판정

최신 보고서의 **A: 오차를 명시하는 interval 집계**를 선택하고, 즉시 다음
movement의 지지집합 변화와 원래 point 사건을 보호하는 선택적 수치 정책
`entry_projection_support_v1`을 Python과 Rust의 실제 incoming 경로에 이식했다.
이 선택은 주민 10만·전체 수요·24시간이라는 목표와 유한응답 운동, 차량 종류·목적·경로,
공유 도로의 저장·수신 제약을 유지한다. 기존 정확 경로는 폭 `h=0`의 기본값이자
비교 oracle로 남는다. 정책과 시간폭은 model/checkpoint identity에 들어간다.

국소 보존·구현 대조·재개 검증의 근거는 확보했다. 실제 Valley의 같은 전체 calendar를
25,500초까지 계산한 paired 비교에서 peak records는 약 23.85%, peak RSS는 약
11.52% 감소했다. 완료량에는 작은 비영 차이가 있었고 속도 향상은 관측하지 못했다.
이어 26,100초를 목표로 한 pilot는 **26,010초에서 transfer-candidate 자원 guard로
중단**했다. 이전 exact guard보다 모의시간 360초 더 진행했지만, 표현 폭증과 전일
실행 문제는 해결되지 않았다. **V03 BLOCKED, 구현·한정 실행 19/21, 24시간 완료
0/9**를 유지한다. 전체 3개 도시×3회×24시간, 전체 CI·통합·merge·최종 수용은 미실행이다.

또한 전체 calendar 918,450 leg의 보관·계상과 전체 leg의 물리 수송 지원은 다르다.
이번 construction에서 610,820개 leg record가 `kind==0 && !assigned`로 분류됐다.
이 수요는 삭제되지 않고 장부에 남지만 물리 수송을 지원하는 것으로 셀 수 없다.
이 기존 coverage 한계는 새로운 투영이 만든 오류가 아니며, 자원 개선과 별도로
해결할 과학적 적용 범위다.

이번 감사는 기존 보고서와 코드를 읽고, 직접 유도 및 저장된 새 실행 결과를 연결한
검토다. 아래의 원격 테스트는 주 실행자가 실행하고 전달한 결과이며, 본 보고서 작성
작업은 별도의 회귀시험을 추가하지 않았다. 같은 시험들의 중첩된 개수를 합산해
하나의 독립 시험 수처럼 보고하지 않는다.

## 2. 원래 동기와 선택 A의 적합성

[원 PRD](../../docs/PRD.md)는 설명 가능한 도시 생성–교통–접근성–도시발전의 연결,
mesoscopic bulk 수송, 경로 대안과 generalized cost, 사건 대응, 평일·주말 및 AM/PM
수요, 느린 접근성 피드백을 목표로 한다. lane-level microscopic default는 제외한다.
[V1 foundation](../../docs/v1/FOUNDATION_REPORT_KO.md)은 지속 단위를 개별 주민의
매초 위치가 아닌 활동 상태를 가진 집단으로 정리한다. 원래 목표의 중심은 관측 가능한
집단 운동과 인과적 상호작용이다.

최신 [외부 감사 요약](../v1_v03_workspace_20261117/AUDIT_BRIEF_KO.md)의 세 선택지를
그 목표에 비추면 다음과 같다.

| 선택지 | 변화의 성격 | 이번 판단 |
|---|---|---|
| A. 근사 interval 집계 | 물리식을 유지하며 시간 조성의 수치 해상도를 정한다. | 채택. 보존·반례·refinement와 함께 구현한다. |
| B. 부분 서비스·FIFO/event 모델 변경 | 어떤 흐름이 언제 어느 순서로 서비스를 받는지 바꾼다. | 이번에는 선택하지 않는다. 물리 법칙 변경까지 요구할 근거가 없다. |
| C. 인구·시간·혼잡 구간의 수용 범위 축소 | 원래 관측하려는 도시 규모와 하루 목표가 달라진다. | 이번에는 선택하지 않는다. |

현재 사용자가 원래 직관에 맞는 선택지를 고르고 코드로 이식하라고 요청했으므로,
과거의 무조건적 시간 집계 금지를 이 이름 있는 정책에 한해 개정했다. 과거 실패 기록,
전체 수요, 자원 한도, 기존 수용 허용오차는 보존한다. A도 정확한 표현 중복 제거가
아닌 수치 근사다. 이전 checkpoint를 새 정책의 상태로 재해석하지 않는다.

또한 프로젝트는 이미 출입구별 접근시간 분포를 조건부 평균으로 투영하고, 질량과
첫 시간 모멘트 및 압축 오차를 기록한다. 따라서 통제된 근사 자체가 원래 모델의
직관에 어긋나지는 않는다. 도로에서는 FIFO와 신호의 비선형 민감성이 추가되므로
접근시간 압축의 검증을 그대로 전용할 수는 없다.

사용자의 일곱 관찰 원문 `AXIOMATIC_FOUNDATIONS_KO.md v0.1`은 기존 유도에서
참조되지만 이번 기준 tree에는 없다. 원래 동기에 대한 판단은 실제 읽은 PRD,
foundation, [기존 공리–모형 유도](../../docs/research/axiom_gap_20261024/DERIVATION_KO.md)에
근거하며, 원문을 직접 읽었다고 주장하지 않는다.

## 3. 기존 결과의 감사: 실측 병목과 과도한 일반화

이전 수명 계상 오류는 교정됐고, 이후에도 아침 유입 구간에서 packet/part가 급증한
실측이 남았다. Valley의 guard 우회 진단에서는 8 GiB 주소공간에서 실제 할당 실패가
발생했다. [기존 보고서](../v1_v03_workspace_20261117/REPORT_KO.md)와
[귀속 결과](../v1_v03_workspace_20261117/ATTRIBUTION_KO.md)는 부분 head 서비스가
served/remainder에 모든 조성 행을 반복해 보유하고, downstream에서 다시 분할되는
기제를 뒷받침한다. 이것은 현재 표현의 자원 문제이며, 물리적인 교통 불안정성이나
모든 알고리즘의 실행 불가능성 증명이 아니다.

다음 문구는 근거 범위를 좁혀 해석해야 한다.

| 이전 해석 | 감사 후 채택할 해석 |
|---|---|
| bit 동일한 해결책은 없다. | 계측한 bit-equal 밀도 병합은 관측 workload에서 충분한 감소를 주지 못했다. |
| 실수 산술 정확 병합의 최대 이득은 1.01–1.08배다. | 같은 source-set 판정으로 찾은 병합 이득이 해당 구간에서 1.01–1.08배였다. |
| 근사 집계가 유일하게 가능한 경로다. | 현재 목표를 보존하면서 이 작업에서 실제 구현·검증할 수 있는 직접적인 개선으로 근사 집계를 선택했다. |

`exact_merge_census`의 동일 source-set 조건은 비례 조성을 판정하는 충분조건이다.
서로 다른 source-set이 동일한 물리 조성을 갖는 모든 경우를 배제하는 필요조건은
아니다. 따라서 이 census는 모든 exact 표현에 대한 최적 압축률이나 strong no-go를
증명하지 않는다. 과거 측정값은 보존하고 해석의 양화 범위만 교정한다.

## 4. 수학·물리 모델의 평가와 이번 개선의 위치

현재 도시 solver는 연속 위치·속도를 출발점으로 한 **축약된 kinetic/common-speed
closure와 FIFO cohort 수송**으로 읽는 것이 정확하다. 연속 phase-space 분포의
모든 속도·gap·차종 상관을 직접 푸는 solver는 아니다.

[T02 closure](../../docs/v1/t02/CLOSURE_KO.md)의 class별 차량량과 공통 운동은

\[
N=\sum_c n_c,\qquad w_c=n_c/N,\qquad
\bar g=\frac{L_{\rm lane}-\sum_c n_c\ell_c}{N},
\]
\[
U=\min_c U_c(\bar g,\mathrm{cap}),\qquad
\nu_c=\beta_c\left(\frac{s_c}{\bar g+\ell_c}\right)^2,
\]
\[
\dot p_c=r_c(1-p_c)-\nu_c p_c,\qquad
\dot u=\operatorname{clip}\!\left(
\sum_c w_c\frac{Up_c-u}{\tau_c},
-\min_c b_c,\min_c a_c\right),\qquad \dot x=u.
\]

질량은 veh, 길이는 m, 시간은 s, 속도는 m/s, 가속도는 m/s²이며
`p`는 실제 속도가 아닌 latent 제어상태의 확률이다. 각 local interval에서 밀도·조성·cap을
고정한 후 `p` 반 step, 유한응답 characteristic, `p` 반 step을 계산한다. 비포화 구간의
유효 응답시간은 `tau_eff^-1 = sum(w_c/tau_c)`이며, 순간 속도를 `U*mean(p)`로
교체하는 모형과 다르다. 이번 투영은 이 운동식과 그 유한응답을 변경하지 않는다.

물리적으로 유용한 점은 운동과 최초 도달시각·예측 비용을 같은 characteristic에
연결하고, 실제 정보와 인지 정보 및 느린 피드백의 시계를 분리한다는 것이다.
반면 다음 제한은 여전히 남는다.

- **공통 속도:** class별 질량과 latent 성향은 남지만 속도분산과 class–speed 상관은
  도시 상태에서 해상되지 않는다. 입장 모멘트를 하나의 bulk 상태로 투영하는 추가
  closure가 있다.
- **mean-gap:** `phi(g)=beta*s²/(g+ell)²`는 convex하므로 일반적으로
  `E[phi(g)] != phi(E[g])`다. 평균 간격만으로 heterogeneous gap hazard를 복원할 수 없다.
- **tiny slow class:** 아무리 작은 양의 느린 class도 `min_c U_c`를 결정할 수 있다.
  작은 질량 제거를 작은 물리 변화라고 보장할 수 없다.
- **안전성과 경험적 타당성:** 이 집계식의 장부 보존은 개별 차량 충돌 회피, 실도시 보정,
  일반적인 shock/FIFO 수렴 정리를 대신하지 않는다.

즉 이번의 개선은 물리적 표지와 보존량을 유지하는 계산 표현의 개선이다. 위 closure
전체가 원래 관찰에서 유일하게 유도된다는 주장이나 새로운 경험적 교통 법칙을
확립했다는 주장은 하지 않는다. 추가 이론 확장은 목적 관측량에서 gap·velocity
상관의 영향이 실제로 판별될 때 검토할 과제다.

운동식의 범위와 별도로, calendar의 모든 활동을 물리 수송으로 연결하는 coverage도
완전하지 않다. 실제 Valley construction에서 미지원으로 분류된 leg는 장부에
보존되지만 일반 road/internal 흐름으로 release되지 않는다. 아래 실제 실행 절의
record 분류와 같이, 입력 계상의 완전성과 운동·서비스 연결의 완전성을 구분해야 한다.

### 진입시간 투영의 계산식

한 cell의 같은 admission step·운동 target을 갖는 양의 interval만 처리한다.
폭 `h`의 고정 격자에 즉시 다음 movement support가 바뀌는 시각, 원래 point
admission 시각, 양의 구간의 처음·끝을 추가한다. category는 `(tag, remaining route)`다.

보호 segment와 원 interval의 교집합을 `[a_i,b_i]`라 하고, 그 구간의 질량과
birth moment를 각각 `m_i`, `B_i`라 쓰면 category별로

\[
M=\sum_i m_i,\qquad B=\sum_i B_i,\qquad
E=\sum_i m_i(a_i+b_i)/2,\qquad \mu=E/M
\]

를 계산한다. 출력 Part는 `M`, `B`, `entry_start=entry_end=mu`를 보유한다.
segment 하나를 FIFO cohort 하나로 만들되 각 category를 별도 Part로 유지한다.
실수 산술에서 질량·원래 birth moment·진입시간 첫 모멘트와 양성성을 보존한다.
부동소수점은 기존 장부 허용오차로 검사하며 양의 underflow는 삭제하지 않고 실패로
보고한다. 서로 다른 시각의 원래 point atom은 시간·순서가 보존된다. 같은
시각의 atom들은 기존 exact 경로와 동일하게 exchangeable한 packet으로 취급한다.

전체 endpoint로 elementary packet을 먼저 확장하지 않는 것이 계산상의 핵심이다.
support sweep은 `O(P log P)`다. Python은 interval과 보호 segment의 실제 교집합을
방문하지만, 현재 Rust 구현은 K개 선택 segment마다 P개 입력을 다시 훑으므로
적분 비용이 `O(PK)`다. K가 크면 재스캔 자체가 성능 병목이 될 수 있다.
많은 category나 물리적 support 변화까지 일정 크기로 압축한다는 보장은 없다.
기존 record/byte 예산과 실패 원자성은 계속 필요하다.

## 5. 국소 오차식과 반례

질량으로 정규화하지 않은 시간측도의 Wasserstein 비용은 veh·s 단위다. category의
시간측도 `nu`를 평균점으로 옮기면

\[
W_1(\nu,M\delta_\mu)=\int|t-\mu|\,d\nu(t)
\le \frac{M(b-a)}2\le\frac{Mh}2.
\]

질량·첫 모멘트 보존과 이 상한은 [이론 문서](../../docs/v1/CONSERVATIVE_ENTRY_PROJECTION_THEORY_KO.md)에
유도했다. 코드의 `local_w1_bound_veh_s`는 실제 적분값 자체가 아니라 category별
지지구간 폭으로 계산한 **국소 비용 상한**의 합이다. 비교 JSON의
`summed_local_projection_cost_veh_s` 역시 이 상한들을 합친 진단이다.
이는 전체 network travel-time 오차나 누적 궤도 오차의 인증값이 아니다.

### tiny blocked-turn 반례와 보호 조건

현재 node solver는 `q_i <= S_i`, `sum_i beta_ij*q_i <= R_j`를 적용한다.
첫 packet A가 열린 출구로 가는 1 veh, 그 뒤 B가 닫힌 출구로 가는 임의로 작은
`epsilon > 0` veh라면, 정확 FIFO는 A를 처리한 후 B에서 정지한다. 둘을 섞으면
blocked share가 양수이므로 head 전체의 서비스가 0이 된다. 시간 분포 차이나
뒤따르는 질량이 작아도 완료량에 큰 차이가 생길 수 있다.

새 정책은 immediate movement support 변화에 경계를 두어 이 반례를 막는다.
`tests/test_entry_projection.py`는 실제 `_rates`를 호출해 이 동작을 검사한다.
그러나 같은 support 안의 분기율 변화까지 exact하게 만드는 것은 아니다.
같은 다음 link를 거친 뒤 future branch가 달라지는 route도 별도 Part로 남지만,
segment 내부의 원래 조성 순서는 근사된다. 관련 시험은 경로 표지와 모멘트의
보존을 확인한 것이며, 모든 후속 분기의 동역학적 동등성을 증명한 것이 아니다.

신호 경계 역시 민감하다. green 끝의 앞뒤로 도달시각이 조금 움직이면 거의 한
red 주기만큼 대기가 달라질 수 있다. admission 단계의 신호·폐쇄 경계 보호가
후속 신호 도달시각까지 고정하는 것은 아니다. 따라서 `h`와 운동 step `dt`를
독립적으로 바꾸고 실제 완료곡선·queue·class/destination flux를 비교해야 한다.

## 6. 실제 이식·검증 결과

### 구현 경로

Python의 `src/metroflow/entry_projection.py`는 독립 projection oracle이고
`packet_network.py`가 선택 정책을 호출한다. Rust `v1_road.rs`는 같은 알고리즘을
실제 incoming 경로에 적용한다. `v1_engine.rs`, Python native frontend,
`NativeReleaseDriver`, `tools/run_v1_local_acceptance.py`까지 시간폭과 identity가
연결된다. `--entry-projection-width-s`는 명시적 opt-in이며 `0`이 정확 경로다.
record/byte 예산 실패, policy/width가 다른 checkpoint 거절, replay를 검사한다.

진단은 마지막으로 검증된 **road proposal**에 관한 것이고, coupled 작업 전체가
rollback됐을 때의 최종 수용 상태나 checkpoint 누적값과 같지 않을 수 있다.
실패한 road proposal과 checkpoint restore는 이 진단을 덮어쓰지 않는다. 따라서
마지막 실패 전의 검증 proposal, 분기 또는 replay를 기술할 수 있다. 진단 자체는
checkpointed가 아니며 그 scope를 출력에 명시한다. 실패 JSON이 초기 진단 0을
남기던 P2 finding은 마지막 진단을 읽도록 수정했다.

### 검증 기록의 identity와 범위

| 실제 실행 | 결과 | 해석·근거 범위 |
|---|---:|---|
| Python 변경 의존성 검사 | 87 passed | [PYTHON_TESTS.log](PYTHON_TESTS.log). 이후 CLI 회귀 추가와 구분한다. |
| CLI 회귀 추가 후 최종 Python 검사 | 88 passed, 3.97 s | [PYTHON_TESTS_FINAL.log](PYTHON_TESTS_FINAL.log). 앞선 87개와 합산하지 않는다. |
| 원격 native 관련 검사 | 163 passed | 최종 allocation 용량 교정 이전 실행. 최종 전체 native 재실행으로 재명명하지 않는다. |
| 마지막 Rust binary의 전체 선택 native 재검증 | 164 passed, 1.92 s | [NATIVE_TESTS_FINAL.log](NATIVE_TESTS_FINAL.log). 최종 allocation 교정과 추가 회귀를 포함한다. |
| 최종 allocation 교정 영향 검사 | 30 passed | 교정된 할당·보존·관련 경로의 선택 회귀. |
| Rust private unit 검사 | 7 passed | 내부 projection·경계·예산 동작의 한정 검증. |
| 실패 JSON 진단 교정의 CLI 검사 | 4 passed | 초기 0 진단 잔류 수정 및 관련 CLI 회귀. |
| 독립 diff 검토 | P0/P1 finding 없음 | 검토 범위 안의 결과다. P2 진단 finding은 위 수정·시험으로 처리했다. |

원격 native·Rust·CLI 결과는 주 실행자가 실행했고, 마지막 native 로그와 비교
JSON을 회수하여 확인했다. [Rust unit 로그](RUST_UNIT_TESTS.log),
[allocation 영향 로그](ALLOCATION_FIX_TESTS.log) 및 통합 영수증으로 소스 바인딩을
연결한다. 위 숫자들의 합을 고유 테스트 수로 취급하지 않는다. 소스가 바뀌기 전의
결과와 교정 후의 선택 회귀는 그 적용 범위를 따로 보존한다.

### 합성 5-link·40초 비교

`tools/probe_v1_entry_projection.py`의 동일 합성 수요는 유한응답 운동, 합류·분기,
신호·폐쇄를 포함한다. 두 `dt`와 여러 `h`의 7조건에서 Python/Rust 대조와 각 조건의
checkpoint replay가 성공했다. 직접 읽은 Python 원자료는
[PYTHON_COMPARISON.json](PYTHON_COMPARISON.json)이며, 원격 결과는
[NATIVE_COMPARISON.json](NATIVE_COMPARISON.json), backend 간 대조는
[PYTHON_RUST_COMPARISON.json](PYTHON_RUST_COMPARISON.json)에 있다.
두 backend의 모든 기록된 최종 scalar 차이는 0이었고, 공통 시각 cell occupancy의
최대 차이는 `4.163336342344337e-17 veh`였다. 관측한 출력의 수치 일치이며 모든
숨은 상태의 bit identity를 의미하지 않는다.

| `dt` [s] | `h` [s] | 40초 완료량 [veh] | peak parts | replay |
|---:|---:|---:|---:|---|
| 1 | 0, 정확 기준 | 3.583054538210508 | 57 | 동일 |
| 1 | 1 | 3.583054538210508 | 56 | 동일 |
| 1 | 0.5 | 3.583054538210507 | 57 | 동일 |
| 1 | 0.25 | 3.5830545382105083 | 68 | 동일 |
| 0.5 | 0, 정확 기준 | 3.8163009742979708 | 107 | 동일 |
| 0.5 | 0.5 | 3.8163009742979708 | 104 | 동일 |
| 0.5 | 0.25 | 3.8163009742979708 | 106 | 동일 |

총 방출량은 약 4.48 veh이며, 최대 질량 잔차는 약 `2.67e-15 veh`다.
같은 `dt=1`의 정확 기준과 투영의 공통 시각 완료곡선 최대 차이는
`8.88e-16 veh` 이하였다. 다만 `h=0.25`에서 유출시간 첫 모멘트 차이
`2.8095993144461318e-5 veh·s`가 남았다. 관측 완료량이 일치한다고 모든 상태가
정확히 같다는 뜻은 아니다.

이 작은 사례에서 압축 이득은 `57→56`, `57→57`, `57→68`이었다. 따라서
표현 폭증을 일으킨 실제 도시에서도 큰 압축 이득이 난다고 예단할 수 없다.
격자를 세분하면 출력 record가 오히려 늘 수 있으며, 이는 해상도와 자원 사이의
실제 trade-off다. 매우 짧은 단일 실행 wall time으로 속도 향상을 주장하지 않는다.

별도의 **정확 경로끼리** `dt=1`과 `dt=0.5`를 비교하면 공통 시각 완료곡선의
최대 차이는 `0.23712892558629584 veh`였다. 총 방출량의 약 5.29%에 해당한다.
이는 projection 오차와 구분되는 시간해상도 민감성이다. 이 두 점만으로 수렴 차수를
확립하거나 기존 수용 기준의 통과를 선언할 수 없다. 큰 도시에서도 투영폭뿐 아니라
`dt`의 영향을 별도로 비교해야 한다.

### 실제 Valley: 같은 구간의 paired 비교

[PAIRED_CITY_COMPARISON.json](PAIRED_CITY_COMPARISON.json)은 원래 Valley의 같은
전체 calendar·초기조건·`dt=10 s`에서 `h=0`과 `h=1 s`를 각각 25,500초까지
계산한 결과다. 두 실행은 모두 완료됐다. 종단 집계와 peak 자원 비교이며 전체
시계열 오차 인증은 아니다.

| 관측량 | 정확 경로 `h=0` | 투영 `h=1 s` | 해석 |
|---|---:|---:|---|
| peak tracked records | 5,304,240 | 4,039,278 | 약 23.85% 감소 |
| peak RSS [B] | 973,053,952 | 860,958,720 | 약 11.52% 감소 |
| wall [s] | 107.778914 | 110.307374 | 공유 host의 단일 paired 실행; speedup 근거 없음 |
| 차량 완료량 차이 [veh] | 기준 | −0.0010362488134898484 | 작은 비영 수치 변화 |
| 사람 완료량 차이 [person] | 기준 | −0.0012953110168485438 | 작은 비영 수치 변화 |
| road 완료량 차이 [veh] | 기준 | −0.0005869497134831647 | 전체 여정 완료와 다른 관측량 |

requested·released·pending과 released-intent 첫 모멘트의 차이는 사람·차량·화물
모두 0이었다. 두 실행의 기록된 장부 최대 잔차도 0이었다. 완료량 차이는 active
잔량의 반대 부호 변화와 함께 남는다. 이는 같은 구간에서의 보존과 자원 감소를
확인한 것이며, projection의 모든 물리 관측 오차가 0이거나 허용 범위임을 인증한
것은 아니다.

### 실제 Valley: 아침 혼잡 구간 pilot의 자원 실패

원자료는 [VALLEY_PILOT.json](VALLEY_PILOT.json)이다. 주민 stock 100,000,
calendar 918,450 legs를 모두 준비했고 `remaining_legs=0`이었다.

| 항목 | 실제 결과 |
|---|---|
| 선택 정책·step | `h=1 s`, `dt=10 s`, scientific worker 1 |
| 목표 / 마지막 유효 모의시각 | 26,100 / **26,010 s** |
| 상태·분류 | **BLOCKED_RESOURCE**, `phase_working_budget_guard` |
| 실패 phase | `transfer candidates` |
| 요구 / 당시 phase 예산 | 4,538,183,888 / 4,538,183,714 B |
| wall / peak RSS | 285.712926 s / 3,176,062,976 B, 약 2.958 GiB |
| 마지막 유효 road | 10,530,239 parts / 14,103 packets |
| 마지막 검증 projection | 5,059,064 → 3,540,968 parts, 5,243 cohorts |
| 보호 support 경계 수 | 2,600 |
| 저장된 마지막 유효 상태 | `valley_projection_h1_gate.last_valid.bin`, 26,010 s |

기존 exact guard의 25,650초보다 모의시간 360초, guard 우회 진단의 실제 할당
실패 약 25,700초보다 310초 더 진행했다. 후자의 실행 조건은 다르므로 동일
조건의 성능 비교로 삼지 않는다. 이번 실패의 요구량이 당시 phase 예산보다
174 B 컸다는 사실은 작은 예산 증액으로 전체 하루를 해결할 수 있다는 뜻이 아니다.

마지막 projection 진단은 실패한 새 proposal의 결과가 아니라 그 전에 검증된
road proposal의 결과다. state guard, 동시 생존 allocation의 예산, 실제 RSS는
서로 다른 관측량이며 RSS가 더 작다는 이유로 guard를 오류라고 판정하지 않는다.
시간 cohort 수를 줄인 뒤에도 많은 category part와 transfer event의 동시 보관이
남았다는 것이 이번 실행으로 확인된 후속 병목이다.

### 전체 calendar coverage와 물리 수송 coverage

`v1_engine.rs`의 construction 분류와 위 pilot를 대조하면 다음과 같다.

| construction 항목 | leg record 수 / 의미 |
|---|---|
| 전체 calendar | 918,450 |
| road legs | 304,368 |
| internal legs | 3,012 |
| `kind==0 && !assigned`인 unsupported legs | 610,820, 전체 record의 약 66.51% |
| 나머지 service-assigned `kind==0` | 250 |
| `physical_routes=304856` | 등록된 route tag 수이며 위 leg 분류와 다른 개수 |

모든 leg의 amounts와 profile identity는 보관된다. report의 requested는 전체
시간 profile을 반영하고 `pending=requested-released`로 남긴다. 미지원 leg를
삭제한 결과는 아니다. 그러나 journey의 `kind==0`은 일반 road/internal release
경로에 들어가지 않으므로 **전체 calendar의 준비·계상 완료를 전체 물리 수송
지원으로 해석하면 안 된다.** 66.51%는 사람이거나 차량질량의 비율이 아닌 leg
record 비율이다.

현재 `unsupported_legs`에는 mode·endpoint·access·route·service 등 이유별
분해가 없어 주원인을 단정할 수 없다. 이번 projection이 이를 새로 발생시켰다는
근거도 없다. 이 finding은 이전 입력·adapter의 scientific coverage를 정확히
구분한 것이며, 새로운 P0 수송 삭제 버그라는 판정이 아니다. 원래 10만 주민의
활동·교통 목표를 달성하려면 후속 물리·서비스 지원 범위를 분해하고 개선해야 한다.

현재 candidate에 새 대형 구조 변경은 추가하지 않았다. transfer-event 비용의
정확한 수명식과 EventBatch 제안은
[자원 후속 문서](../../docs/v1/ENTRY_PROJECTION_RESOURCE_FOLLOWUP_KO.md)에,
category 측도를 불변 block과 계수로 공유하는 다음 구성은
[mark block 후속 문서](../../docs/v1/CONSERVATIVE_MARK_BLOCK_NEXT_KO.md)에 있다.
두 후속 표현은 **제안·미구현**이며 이 보고서의 검증 완료 기능에 포함되지 않는다.

## 7. 이론·코딩 루프의 실제 대응

이론 R1–R10의 식·전제·유도·문헌·반례·코딩 계약은
[이론 문서](../../docs/v1/CONSERVATIVE_ENTRY_PROJECTION_THEORY_KO.md)에 기록되어 있다.
이번 코딩 단위의 실제 대응은 다음과 같다. 단계 번호가 전체 도시 수용의 완료율을
뜻하지는 않는다.

| 단계 | 실제 수행·산출물 | 근거와 남는 경계 |
|---|---|---|
| C1 목표·baseline | 최신 SHA, A/B/C, 원래 수요·규모·예산·정확 경로를 고정했다. | 기존 V03 실패와 원본 보고서를 보존했다. |
| C2 식–데이터–코드 | `Part`의 시간측도·birth moment에서 Python/Rust incoming, native driver, CLI, checkpoint까지 추적했다. | 표현 복잡도와 물리 closure의 한계를 분리했다. |
| C3 수치 설계 | support/point 보호, category별 양의 모멘트 투영, `Mh/2` 국소 상한을 정했다. | 전역 network 오차 보증은 주장하지 않는다. |
| C4 실행 DAG·자원 | Python oracle·이론과 Rust 구현을 분담하고 원격 격리 실행으로 native 검증을 연결했다. | 전체 CI·3×3 전일 캠페인은 별도 의무다. |
| C5 구현 | Python/Rust 커널, 실제 native runtime·driver·CLI·identity·실패 출력을 연결했다. | 실제 paired 구간의 자원 감소는 확인했으나 전일 자원 문제는 pilot에서 다시 차단됐다. |
| C6 구현 검증 | 보존, support 반례, point 순서, 고시각·underflow·예산 실패, width identity, replay를 실행했다. | Python 최종 88, native 최종 164, Rust 7 및 중간 선택 회귀의 서로 다른 실행 범위는 위 표를 따른다. |
| C7 과학 검증 | 질량·birth/entry 모멘트·양성성, tiny blocked-turn 반례, 동일 운동식과의 연결을 확인했다. | common-speed/mean-gap의 경험적 타당성·충돌 회피는 미확립이다. |
| C8 수치·재현성 | 5-link·40초의 7조건과 두 backend/replay, `h`·`dt` 분리 비교, 실제 Valley 25,500초 paired 비교와 26,010초까지의 pilot를 수행했다. | paired 자원 감소와 비영 수치 차이를 확인했고 pilot는 자원 실패했다. 전일 비용·일반 수렴은 미확립이다. |
| C9 독립 검토 | 중요한 diff·오차 주장·실패 원자성을 검토하고 P2 진단 finding을 수정했다. | P0/P1 부재는 검토 범위 내 판단이다. |
| C10 판정·인계 | 설계·이론·새 감사 보고서·소스·실행 근거·로컬 인계 및 후속 표현 제안을 연결했다. | 현 candidate와 미구현 후속을 구분하고 V03 BLOCKED를 유지한다. 최종 게시 identity는 통합 영수증을 따른다. |

## 8. 현재 결론과 남은 의무

**derived:** 보호 segment에서 category별 질량·birth moment·entry moment 보존,
양성성, 국소 시간측도 비용 상한을 얻었다.

**implementation-verified / numerically checked:** 선택 정책이 실제 Python/Rust 수송
경로에 연결되고, 한정 보존·반례·실패·identity·재개 시험 및 합성 network 비교를
통과했다. 동일 `dt`의 작은 사례에서는 완료곡선 차이가 roundoff 수준이었다.
실제 Valley의 공통 25,500초 구간에서는 peak records·RSS가 감소했고 완료량에는
작은 비영 변화가 남았다. 이 측정은 보편적 수치 오차나 속도 향상을 증명하지 않는다.

**blocked / unresolved:** 실제 Valley pilot는 26,010초에 transfer-candidate 자원
예산으로 중단했다. 시간 투영을 도입한 현 candidate는 전일 표현 비용 문제를
해결하지 못했다. 신호·분기·혼잡의 network 오차, `dt` refinement, 미지원 활동의
물리 수송 coverage가 남아 있다. support 보호와 보존 장부가 이 의무를 대신하지 않는다.

**NOT_RUN:** 공식 3×3 전일, 전일 checkpoint 대조, 큰 도시의 matched `dt` refinement,
전체 CI·통합·merge·release는 미실행이다. 과거 `19/21`은 구현·한정 실행 진척이며
V1 전체의 과학적 수용률이 아니다.

재개는 [로컬 에이전트 인계](LOCAL_AGENT_HANDOFF_KO.md)의 소스·입력·명령·반환
계약을 따른다. 다음 표현 개선은 위 EventBatch/mark-block 제안을 한정 구현하고
같은 입력·`h`·`dt`에서 비용과 물리 관측을 대조하는 작업이다. 동시에 unsupported
leg의 이유와 사람·차량·화물량을 분해해 물리·서비스 지원 범위를 확인해야 한다.
수요 삭제나 수용문턱 완화로 현재 실패를 성공으로 바꾸지 않는다.
