# Urban Traffic Demo V1: 독립 소스 감사 · 수학/물리 연구 루프 · 경량화 탐색

- 작성: 2026-11-18 (Asia/Seoul).
- 원격 기준: `cosmosapjw-quantum/urban_traffic_demo`, draft PR #41 `v1/v03-acceptance-20261027`, commit `0b9caa8cc60a3ba087722e0360b997c5dfb61d62`.
- 기본 브랜치 비교: `main` `01c80b432344f94209daaa198bb1eb007839fc7f`. `main`은 최신 V1을 포함하지 않는다.
- 분리 작업: `/home/cosmosapjw/worktrees/urban-traffic-v1-audit-20261118`, `audit/urban-traffic-v1-theory-lightweight-20261118`. 원본의 미커밋 변경사항은 수정하지 않는다.
- 규범 계약: `docs/v1/PLAN.json` v1.1.26. 본 연구는 별도 탐색이며 V03 release/수치 계약을 변경하지 않는다.

## A. 최신 결과와 물리/구현 감사

**[SOURCE-AUDITED]** V03의 원래 요구는 river weekday s17, coastal weekend s41, valley weekday s7의 실제 10만 주민 입력을 24h(86,400 s)씩 3회 실행하는 것이다. 현재 0/9회 완료, V03 BLOCKED, 전체 구현 진척 19/21(90.5%)이지만 그 수치를 release 승인으로 읽어서는 안 된다. PR #41 head에는 GitHub Actions의 해당 commit 실행 근거가 검색되지 않았다. 로컬 한정 검사 결과와 분리한다.

**[SOURCE-AUDITED + PHYSICAL-BLOCKER]** 현재 선택된 연속 경계구간 packet FIFO 모델은 혼잡 시 부분 서비스가 생기면 `served`와 `remainder`가 각 packet의 모든 행을 실수 곱으로 복제하고, served의 하류 시간구간에 추가 event 분할을 수행한다. 물리 혼잡으로 정당화되는 보유 차량량 증가는 별도 현상이며, **동일 차량량의 표현행이 급증**하는 문제가 V03을 막는다.

기존 guard 우회 진단(캠페인 후보 아님)의 Valley 25,600→25,650 simulated s에서 road part 약 7.2M 증가, 그중 partial-service 원천 +7.21M, entry interval splitting +2.07M, fresh offer +0.77M, combine -0.59M, sink -0.46M. Road packet 111k→210k, parts 5.63M→10.98M, 같은 50s 구간 wall 25.7→91.3s. 8GiB RLIMIT_AS에서 실제 allocation failure가 관측되었다. 파일: `artifacts/v1_v03_workspace_20261117/AUDIT_BRIEF_KO.md`, `ATTRIBUTION_KO.md`.

현재 계산상 bit-identical adjacent merge 후보는 매우 적고, source-proportional real-arithmetic merge의 감소량은 기존 진단에서 1.01–1.08배 정도이다. 이것이 **모든 가능한 정확 표현에 대한 불가능성 정리**는 아니다. 입증된 것은 현 packet 표현과 조사한 병합 후보가 원래 gate를 충족하지 못한다는 제한적 사실이다. immutable DAG/share/compressed event algebra 등 다른 표현의 시간·메모리 하한은 아직 증명하지 않았다.

### 다른 과학적 제한

1. **공통속도 closure의 희소 slow class 민감성 [DERIVED].** `U=min_c U_c`를 모든 양의 질량 class에 적용하므로, 속도상한 20m/s 차량 사이에 상한 5m/s 차종이 극소량 `epsilon>0`만 존재해도 공통 허용속도는 5m/s이고 `epsilon=0`일 때 20m/s로 점프한다. 이 불연속은 차종 혼합 해석의 모형 선택에 따른 결과로, 다차선의 실제 이종차량 속도를 인증하는 규칙이 아니다. 단순 soft-min은 느린 class의 엄격한 safety cap을 위반할 수 있으므로 대체 시 class별 운동·차선 상호작용을 재정의해야 한다.
2. **mean gap hazard의 Jensen 편향 [DERIVED].** `nu(h)=beta[s/(h+ell)]^2`는 `nu''(h)=6 beta s^2/(h+ell)^4>0`. 따라서 `E[nu(h)]>=nu(E[h])`이며, h=4,96m 동률 혼합, ell=5m, s=10m, beta=.3/s라면 평균 hazard는 약 0.1866556/s, 평균 gap 50m 대입식은 약 0.00991736/s로 약 18.82배 차이. 이는 예시 반례이지 도시 데이터 추정치가 아니다. 실제 gap distribution/pair correlation 없이는 안전성·충돌 회피를 주장할 수 없다.
3. **교차로·회전 [SOURCE-AUDITED].** T03은 sending/receiving과 positive priority, shared-head FIFO, lane partition 및 제어 경계의 보존·예산을 검사한다. 그러나 명시되지 않은 geometric conflict 또는 동적 lane change까지 입증하지 않는다.
4. **시간 경계 [SOURCE-AUDITED].** T04의 출입 시각은 유한 `max_step` 및 다음 경계 전달 holding을 포함한다. 이는 물리적 지연과 구분해서 보고하며, global shock-convergence/임의 signal schedules/collision-free 주장을 뒷받침하지 않는다.
5. **합성 도시 수요 [SOURCE-AUDITED].** independent OD product coupling과 `unassigned_home`은 명시된 synthetic prior다. actual traffic sensor/GPS data로 현장 calibration 한 결과가 아니다. 하천·계곡은 요청된 취업 의도 50k명 중 현재 jobs stock 40k명만 배정되고 10k명은 미배정으로 보존된다. 이를 일자리 capacity로 채우거나 demand를 삭제하면 다른 문제를 푸는 셈이다.

## B. 이론 연구 루프: 원방정식과 해석적 개선

**정의와 가정.** 밀도·class weight `w_c`, 공통 admissible target `U`, hazard `nu_c`, restart `r_c`, response time `tau_c>0`를 한 local interval에서 고정하고 acceleration/braking clipping이 **비활성**이라고 한다. 시간 s, 속도 m/s, 위치 m, rate 및 `gamma` 단위 s^-1이다. T02의 잠재확률 `p_c`는 실제 속도가 아니다.

```math
lambda_c = r_c + nu_c,
p_{c,*} = r_c/lambda_c   (lambda_c>0),
p_c(t)=p_{c,*}+(p_c(0)-p_{c,*})e^{-lambda_c t}.

a_c = w_c/tau_c, gamma = sum_c a_c,
v'_t + gamma v = U sum_c a_c p_c(t),
v_* = U (sum_c a_c p_{c,*})/gamma.
```

`lambda_c=0`이면 `p_c(t)=p_c(0)`로 처리한다. 적분인자를 사용하면

```math
v(t)=v_*+(v_0-v_*)exp(-gamma t)
 + sum_c U a_c (p_c(0)-p_{c,*})
   [exp(-lambda_c t)-exp(-gamma t)]/(gamma-lambda_c).
```

`gamma=lambda_c`에서는 분수의 연속극한 `t exp(-gamma t)`를 사용한다. 거리는 `F(z,t)=(1-exp(-z t))/z`, `F(0,t)=t`를 정의하여

```math
x(t)-x(0)=v_*t+(v_0-v_*)F(gamma,t)
 + sum_c U a_c (p_c(0)-p_{c,*})
   [F(lambda_c,t)-F(gamma,t)]/(gamma-lambda_c).
```

위 식은 명시된 동결 입력에서 연속 ODE의 해다. **네트워크 충격파/차량간 미시동역학의 해가 아니다.** `expm1`, `gamma=lambda` 극한 또는 exp-relative 함수가 가까운 rate에서 필요하다. 현재 연구용 oracle은 가까운 rate의 거리 차분몫을 중간 rate 극한으로 계산하는 수치 근사를 명시한다.

**[CAS-CHECKED]** Wolfram에서 `D[v,t]-(-gamma v+gamma v_*+B exp(-lambda t))`를 `0`으로 단순화했다. 공명극한 `t exp(-gamma t)` 확인. **[NUMERICALLY-CHECKED]** `tools/research/frozen_relaxation_oracle.py`의 2-class fixture (U=12m/s, t=5s)는 analytic `v=5.711963631856243m/s`, `dx=29.734737999624503m`; 독립 5000단계 RK4는 `v=5.711963631856226`, `dx=29.734737999624542`. `T/5, T/10, T/20, T/40`로 적분한 기존 midpoint-latent Strang의 최대 오차는 `0.09011466, 0.0226370, 0.00566607, 0.00141694`이며 이 fixture에서 2차 수렴이 보인다.

**구현 판단.** 본 식은 T02 `advance_bulk` / `predict_passage`에서 동일한 frozen local motion을 계산하는 선택적 정확 적분의 후보이다. 그러나 clipped piecewise dynamics, 시간 의존 공급, 경계의 shock/refinement가 있을 때 별도 event matching과 회귀가 필요하다. **본 worktree에서는 생산 solver를 변경하지 않았다.**

## C. 모델 수준의 구조 대안: 조건부 선택

**C1: exact physical semantics 그대로, 표현만 공유 [CONJECTURAL].** time-interval packet의 불변 부분을 `Arc`/persistent DAG 등으로 공유하고 split의 scale/history를 게으르게 계산한다. birth/mass의 IEEE 연산 순서, identity, class, FIFO 순서, checkpoint wire bytes와 budget accounting을 보존하려면 축약과 원래 전이 `T`가 관측 `O`에 대해 교환해야 한다(`QT=\hat TQ`, `O=\hat OQ`). 공유가 물리 논리행의 최악계산량을 줄인다는 근거가 없다. 50s 간격 동일 checkpoint replay/route-event trace로만 개선 여부 판단. **지금은 exact 해결책 검증 없음.**

**C2: 1차 보존형 LWR/CTM 또는 링크전달모형(LTM) [LITERATURE-SUPPORTED, MODEL-CHANGE].** 동질 차량밀도 `k(x,t)`와 `Q(k)=min(v_f k,w(k_j-k))`를 놓으면

```math
partial_t k + partial_x Q(k) = 0,
k_crit=w k_j/(v_f+w),
Q_max=v_f w k_j/(v_f+w).
```

CTM finite-volume cell flux `F_{i+1/2}=min(D_i,R_{i+1})`와

```math
k_i^{n+1}=k_i^n+(dt/dx)(F_{i-1/2}-F_{i+1/2})
```

에서 내부 flux가 망원합 상쇄되어 `sum_i k_i dx` 변화는 경계 유량만 남는다. `dt<=dx/max(v_f,w)`는 삼각 기본도표에서의 CFL 조건이며 positivity/monotone flux의 전제다. 초기 비점유 링크의 누적 N_in/N_out 표현은 free-flow lag `L/v_f`, backward storage lag `L/w`와 `0<=N_in-N_out<=k_j L`를 사용해 링크 내부 full packet 행 열거를 줄일 여지가 있다. Node 모델은 턴 비율과 signal, sending/receiving의 동일 resource ledger를 다뤄야 한다. 개인별 route identity를 보존할 때는 누적 유입 quantile에 불변 tag 정보를 연동하고, 출입 시각과 정량 보존을 별도 검증한다. **이 모델은 기존 finite-response T02/T04와 정확히 동일하지 않으므로 현재 배포 코드에 교체하지 않는다.** LTM은 표준 문헌에 기반하지만 이 프로젝트에서의 성능/정확성은 미검증이다.

**C3: 보존형 interval 근사 [CONJECTURAL, CONTRACT-CHANGE].** 하나의 구간 안에서 질량 `M=sum_i m_i`와 시각 1차모멘트 `B=sum_i m_i t_i`를 보존하여 packet을 합치면 `M,B`의 보존은 직접 증명되지만 시간별 누적곡선 및 spillback은 보존되지 않는다. 반례: `mu_A=(delta_0+delta_2)/2`, `mu_B=delta_1`은 같은 M=1veh, B=1veh·s를 갖지만 t=0.5s에서 누적 방출량이 각각 0.5veh와 0veh다. 신호/수신 상한 아래에서는 도착시간, FIFO 조건, 혼잡이 달라진다. 따라서 **mass+first moment 만으로는 관측동등성과 uniform delay bound가 따라오지 않는다**. 구간별 누적량 오차, 퀀타일·W1, 비음성 조건과 적색 신호/역전 shock 등 적대적 테스트를 사전 고정해야 한다. 현재 금지된 time binning과 구별되지 않는 구현을 조용히 도입해서는 안 된다.

**논문 출처:** Daganzo (1995), *The Cell Transmission Model, Part II: Network Traffic*, https://its.berkeley.edu/publications/cell-transmission-model-part-ii-network-traffic ; Jin (2015), *Continuous formulations and analytical properties of the link transmission model*, https://scispace.com/papers/continuous-formulations-and-analytical-properties-of-the-30xyqkmdki ; de Souza et al. (2025), *A mesoscopic link-transmission-model able to track individual vehicles*, https://www.osti.gov/biblio/2569501 . 이들은 모델 가능성과 문헌 근거이며 본 저장소 V03 수용의 증거가 아니다.

## D. 코딩 연구 루프: 채택과 기각을 나눈 결과

1. **기준 정립 [IMPLEMENTATION-VERIFIED].** 격리 worktree 자체에서 Pyo3 Rust native extension을 release 빌드하고 로컬 Python 3.12 환경에 설치했다. 해당 exact SHA 기준 scoped Python test **84 passed**, Rust 테스트는 PyO3 `extension-module` 링크로 인한 최초 `cargo test` 실패를 `RUSTFLAGS="-C link-arg=-lpython3.12"`로 해결해 **58 passed**, `cargo check --workspace --tests` 통과. 전체 저장소 CI는 하지 않았고 원격 head에 CI 실행도 확인되지 않았다.
2. **부분 서비스 중복 순회 제거 [REJECTED AFTER BENCHMARK].** `v1_road.rs`의 `portion(...,f)`와 `portion(...,1-f)`를 한 번의 vector traversal로 만드는 구현을 독립 worktree에 시험했다. 84개 Python 시험과 체크포인트/이벤트 공개상태 해시가 같은 것은 확인됐다. 첫 비교에서는 47.394→42.265 µs로 개선처럼 보였으나 서로 다른 시점의 unpaired 측정이다. 동일 잠금된 dependencies와 같은 fixture에서 별도 baseline/optimized 확장을 빌드하고 **A/B/A/B 교차 실행**한 결과 중앙 step latency: A=32.018µs, B=31.906µs, A=31.675µs, B=32.366µs, `sqrt(A1*A2/(B1*B2))≈0.991`. 일관된 개선이 없고 실측 오차 수준이므로 수정을 **완전히 되돌렸다**. 이 결과를 도로 패킷 복제의 해결이라고 주장하지 않는다.
3. **추가 제안 [UNVERIFIED].** event-interval 입력 저장을 단조 edge sweep으로 처리하고 동일 frozen interval 계산을 memoization하는 방안은 이미 `combine`의 키 및 stable summation 순서를 보존해야 한다. hot-path에서 profiling으로 실제 시간 비중을 확인하기 전 재작성하지 않는다. 의미를 보존하는 immortal source registry 공유와 compact `CorePart`는 이미 현재 코드에 구현되어 있으므로 새 혁신이라고 주장하지 않는다.

**검산 프로토콜:** `tools/research/bench_v1_packet_split.py` (단일 셀·128 tag·partial service·고정 checkpoint, restore 시간 제외), `tools/research/frozen_relaxation_oracle.py` (분할해 대 RK4), `artifacts/v1_research_20261118/{a_baseline,b_optimized,c_baseline,d_optimized,frozen_relaxation}.json`. 수십 µs짜리 공유 호스트 microbenchmark를 8GiB/24h 실제 도시 성능으로 외삽하지 않는다. Build는 system `maturin 1.3.2`였으나 crate `pyproject.toml`의 현재 요구 `>=1.14`와 일치하지 않아 환경재현성 경고가 남는다. 전역 `cargo fmt --all -- --check` 실패는 이 실험과 무관한 선행 파일(`src/lib.rs`, `routing.rs`)의 포맷 차이이며 코드 오류/physics failure로 오분류하지 않는다.

## E. 결정/중단조건과 다음 1회 연구 제안

- 기존 물리 계약을 **변경하지 않는 범위**에서는 연구용 exact-frozen integrator를 T02 오라클에 추가하는 것이 낮은 위험의 검증 후보이고, 실질 V03 blocker에는 직접 효과가 없다. 주 수용 문제를 해결한 것으로 제출하면 실패다.
- 24h/10만 명 성능을 실제로 목표로 할 때는 **C2의 보존형 LTM + 개인별 route quantile**을 *별도 opt-in physical variant*로 먼저 소형 1-link, lane-drop, merge/diverge, closed-red, spillback, gridlock, 여러 차종(공통속도와 구별)에서 구현 비교하는 것이 제1 선택이다. 이는 물리 모델의 범위 변경을 필요로 하므로 기존 V03 해상도 계약을 자동 수정하지 않는다.
- 현재 packet 모델과 관측동등을 꼭 유지해야 한다면 C1의 persistent decomposition을 먼저 작은 혼잡 fixture에서 *bit 정확* checkpoint/event compare 및 peak RSS와 tick cost로 평가한다. 큰 도시에 무제한 확장하는 조건부 승인으로 취급하지 않는다.
- C3 근사를 허용할 경우 mass 보존만이 아니라 cumulative throughput at cut times, route/class totals, first arrival, finished/unreleased/pending, source/queue/transfer veh·s 및 boundary-continuity와 dt refinement를 사전 고정한다. violation이 하나라도 발생하면 수용을 중단한다.
- 현 상태에서 V03: **BLOCKED**; 19/21(90.5%) 유지; 전체 3×3 실도시 하루 실험은 **NOT_RUN_DEPENDENCY_BLOCKED**. `main` 수정, PR 병합, 원격 push, 원본 root 미커밋 변경, 기존 V03 acceptance gate 수정은 모두 수행하지 않는다.

## F. 명령·재현·파일 신원

```sh
# Isolated worktree
cd /home/cosmosapjw/worktrees/urban-traffic-v1-audit-20261118
.venv/bin/python -m pytest -q tests/v1/test_kinetic_closure.py tests/v1/test_exact_reductions.py tests/v1/test_native_packed_intervals.py tests/v1/test_native_retained_accounting.py tests/v1/test_native_queue_lifecycle.py tests/v1/test_native_road.py tests/v1/test_native_event_resolution.py tests/v1/test_native_history.py tests/v1/test_native_storage_policy.py
RUSTFLAGS="-C link-arg=-lpython3.12" cargo test --workspace --lib
cargo check --workspace --tests
.venv/bin/python tools/research/frozen_relaxation_oracle.py artifacts/v1_research_20261118/frozen_relaxation.json
git diff --check
```

이 문서의 Status는 관측/원래 보고, 새 수학 유도, 현재 Python/Rust 검증, 연구상 가설을 명시적으로 구분한다. 미실행 문턱을 PASS로 승격하지 않는다.

## G. 2026-11-18 중단 복구 후 추가 검증

- GitHub PR #41 최신 HEAD `0b9caa8cc60a3ba087722e0360b997c5dfb61d62` 불변, 미병합으로 재확인했다. 평가 대상 source는 이 immutable commit, 연구 스크립트와 문서는 별도 worktree 신규 파일이다.
- **[NUMERICALLY-CHECKED]** `tests/research/test_urban_v1_model_20261118.py`에 deterministic seed의 24개 1~3-class ODE fixture를 마련했다. `gamma=lambda_c`, `gamma≈lambda_c`, `lambda_c=0`을 포함하여 RK4 2400 step과 local exact frozen reference를 비교한다. 질량·출생 1차모멘트가 같아도 시각 누적곡선이 다르다는 counterexample와 Jensen hazard, 희소 slow class의 min closure 불연속을 검증한다. 3 passed (0.39s).
- **[IMPLEMENTATION-VERIFIED]** 현재 worktree에서 선별 Python 물리/CTM/native/research 결합 시험 **111 passed (1.66s)**. Rust `RUSTFLAGS="-C link-arg=-lpython3.12" cargo test --workspace --lib`: **58 passed**. `cargo check --workspace --tests` 완료. 별도 Python extension은 `maturin develop --release`로 빌드했다. repo-wide CI, 실제 3개 도시 3회×24h, 별도 PR CI는 시행하지 않았다.
- **[NUMERICALLY-CHECKED, NEGATIVE RESULT]** 동일 crate lock과 동일 benchmark fixture에서 A/B/A/B의 처리시간 중심값은 32.018/31.906/31.675/32.366 μs였고, 개선판의 안정적인 속도 향상은 입증되지 않았다(기하평균 비 0.991). 모든 trial의 published state hash `4026b582ee4f053683897a378ee526328701006f9f29f9157ff9ef3dc63eccb1` 동일. 후보 diff는 `artifacts/v1_research_20261118/SPLIT_PORTIONS_REJECTED.patch`에 역사적 반례로만 남겼고 **생산용 Rust 파일은 기준 SHA의 원본 바이트로 되돌렸다.**
- **[EVIDENCE / LITERATURE]** 공식 원전 확인: Daganzo (1995), *TR-B* 29(2), 79–93, DOI `10.1016/0191-2615(94)00022-R` (https://its.berkeley.edu/publications/cell-transmission-model-part-ii-network-traffic); Jin (2015), *TR-B* 74, 88–103, DOI `10.1016/j.trb.2014.12.006`; de Souza et al. (2025), *Simulation Modelling Practice and Theory*, article 103088, DOI `10.1016/j.simpat.2025.103088`. 세 번째 연구는 누적유량 기반 LTM에 개별 차량 추적을 실제로 구축한 문헌상 구현 사례다. 문헌상 모델 가능성을 현 V03의 통과와 혼동하지 않는다.
- **[HOST CAPABILITY]** 현재 대화에서 native subagent spawn/wait는 제공되지 않아 `native_subagent: NOT_RUN`이다. 직접 소스 조사, CAS 대조, 실제 독립 실행 코드와 serial fallback로 연구를 진행했다. `superpowers` 등 지시를 받았다는 이유만으로 native delegation이 실행되었다고 주장하지 않는다.
- **[REMAINING OBLIGATION]** 다음 결정은 기존 packet 모델의 정확한 causal semantics를 유지하면서 DAG공유 표현을 시험할지, 별도 승인된 보존형 LTM-vehicle tracking 실험 branch를 열지, 정량오차를 동반한 bounded interval 축약을 승인할지에 관한 물리 모형·관측량 범위의 선택이다. 이번 실행의 생산 solver 변경은 없다.
