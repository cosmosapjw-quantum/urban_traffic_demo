# KCMB 코딩 연구 루프 C1–C10 · Rust opt-in 물리 구현 및 독립 검증

2026-11-19 (Asia/Seoul). **대상은 새로운 조건부 kinetic–conservative 근사 연구 경로이며 기존 V1의 교통모형 대체가 아니다.**

**계보/고정 authority:** `cosmosapjw-quantum/urban_traffic_demo`, V03 draft PR #41 HEAD `0b9caa8cc60a3ba087722e0360b997c5dfb61d62`; 직전 이론 연구 R1–R10 `23b200d636ca9465942baacb2287ccb2830047bf`의 `docs/research/KCMB_MICRO_KINETIC_MACRO_THEORY_R1_R10_20261118_KO.md`. 독립 worktree `/home/cosmosapjw/worktrees/urban-traffic-kcmb-coding-20261118`, branch `research/kcmb-coding-c1-c10-20261118`.

## 결론과 admission 기준

- **[IMPLEMENTATION-VERIFIED; SCOPED]** 독립 `metroflow.v1.kcmb` Python reference와 PyO3 Rust `NativeKCMBCorridor`의 opt-in 단일 corridor 구현. 다차종의 microscopic Markov 6-moment propagator, bounded metres/vehicle sending/receiving, red gate, pending/source/completion, checkpoint와 model ID를 갖춘다.
- **[DERIVED; NUMERICALLY CHECKED]** 유한 고정 셀·class의 순간량 `6*N*K+3*K` 스칼라로 표현되며, packet이 계속 분할되더라도 도로 내 상태 객체 수가 그 횟수에 비례하여 증가하지 않는다. 절대 차량량이나 원래 도시 OD leg의 수와 무관한 정적 *상태 차원* 주장이다. 물리적 근사법을 바꾼 것이므로 기존 `PacketNetwork`의 모든 route/arrival/FIFO 이력과의 값·bit 동치는 주장하지 않는다.
- **[NUMERICALLY CHECKED]** 외부 데이터를 사용하지 않은 한정 물리·회귀 Python **155 passed**, Rust lib **59 passed**, `cargo check --workspace --tests --offline` 및 새 Rust 파일 rustfmt, Python 변경모듈 compile 통과. 전체 repo CI와 100k×24h V03 3×3은 별도 수용계약에 따라 NOT_RUN.
- **[MEASURED, NOT EXTRAPOLATED]** 같은 KCMB 모델의 Python/Rust 4회 순차 A/B/B/A의 64 cells·2 classes·600 steps에서 중앙 Python/Rust `2.849×`. 이것은 **기존 V1 대비 성능 개선이 아니라 동일 새 근사의 코드 backend 비교**다. Rust 전체 프로세스 RSS는 오히려 조금 더 컸다.
- **[UNRESOLVED]** 도시 교차로 네트워크·class/turn FIFO, 차량별 정확 출생-도착 분포, 상호작용으로부터 자발적 stop-and-go 파동, micro pair 안전, field realism, 기존 V03 8GiB/7200s gate.

## C1. baseline·목적·원래 수용 계약

선택된 연구 단위는 **opt-in physical variant**를 코드와 독립적인 과학 oracle이 대조할 수 있도록 구현하고, 원래 전일 V03 source/clock/route와 혼동하지 않는 것이다. `docs/v1/PLAN.json`(v1.1.26)의 기존 물리·수치 허용오차·V03 19/21 BLOCKED·24h 완료 0/9 상태를 변경하지 않았다. 실제 저장소 `main`과 진행 중인 PR #41은 원래대로 보존했다. 원본 `crates/metroflow-rust/src/v1_road.rs`와 `src/metroflow/packet_network.py`의 바이트를 변경하지 않았다.

## C2. 수학·데이터·코드의 정확한 대응

각 homogeneous class `a`의 내부 제어 `sigma=0,1`, 실제 속도 `v=U_a u`에서 `u∈[0,1]`를 사용한다. 단위는 `M,P` vehicles; `J=∫u dmu` vehicles; `Z=∫u² dmu` vehicles이며 실제 속도1차 모멘트는 `U_a (j0+j1) [veh m/s]`이다. **이 구현의 j/z는 무차원속도 `u`로 정규화한 모멘트**라는 점이 이론 보고서의 물리단위 `V,H,Z`와의 필수 차이이다.

```text
vector Y=[m0,m1,j0,j1,z0,z1]^T,
a=alpha[1/s], b=nu[1/s], g=1/tau[1/s]

A*Y =
[-a*m0+b*m1,
 +a*m0-b*m1,
 -(g+a)*j0+b*j1,
 +g*m1+a*j0-(g+b)*j1,
 -(2g+a)*z0+b*z1,
 +2g*j1+a*z0-(2g+b)*z1].

Y_kin=exp(dt A)Y_old.
M_i,a=m0+m1 [veh]; J_i,a=j0+j1 [veh].
S_i,a=min(M_i,a,(dt/dx) U_a J_i,a) [veh].
S_i,a <- S_i,a * min(1, Cdt/sum_a S_i,a).
vacancy_i=max(0, lanes*dx-sum_a footprint_a*M_i,a) [m].
R_i_m=vacancy_i*min(1,w*dt/dx) [m].
transfer_i,a=S_i,a * min(1,Cdt/sum S_i, R_(i+1)_m/sum_a footprint_a*S_i,a).
Y_i,a_new=(1-transfer_i,a/M_i,a)*Y_i,a_kin
           +(transfer_(i-1),a/M_(i-1),a)*Y_(i-1),a_kin,
for i>0; source for i=0.
```

송출/수신은 **같은 pre-step 상태**에서 계산한다. Source량 `pending+offered`은 공통 source lane-metres와 `Cdt`에 맞게 같은 비율로 admission되고, residual은 pending에 남는다. Red gate는 하류 마지막 sink의 `S_last*green`이다. 이 정책은 실수차량량·fractional mixture를 사용한다. 특정 차종 우선권이나 차량별 FIFO 정책은 구현되어 있지 않다.

매 순간량은 `src/metroflow/v1/kcmb.py`와 `crates/metroflow-rust/src/v1_kcmb.rs`에 이식했다. Native Rust extension에 등록된 클래스는 저수준 API이므로 **Python `KCMBConfig`를 통한 validated construction**이 지원 인터페이스이다. 저수준 native 생성자가 임의의 비음수 행렬을 받는 것만으로 올바른 micro Markov 생성자라고 인증되는 것은 아니다.

## C3. 수치구성·오차

국소 운동의 `exp(dt*A)`는 uniformization `P=I+A/q ≥0`, `q≥max_i(-A_ii)` 및 Poisson weighted powers를 작은 시간구간에서 계산한 뒤 반복제곱한다. Poisson 급수는 `k≤128` 및 사전 중단 기준으로 절단하므로 **연속시간 정확한 semigroup의 수치 근사**이지 IEEE bit 정확해가 아니다. `q*dt>10^6` 또는 비유한 수치에서 예산오류로 거절한다. 양의 generator와 bounded support에 대한 수학 정리는 정확한 semigroup에 적용되며, 유한정밀 계산은 별도의 realizability/ledger 검사로 감독한다.

Space flux는 1차 positive conservative Godunov-type update, fixed cell/lanes/class parameter이고 `dt max(U_max,w)/dx≤1`. 수치/물리 오차를 구별한다: (1) Markov exponential 절단·반올림, (2) 분할(kinetic→transport) 시간오차, (3) 1차 공간 FV 수치확산, (4) 근본적 평균장/혼합 closure, (5) 실제 도시 추정·경계/OD 오류. 총질량 보존만으로 shock profile이나 관측실재성 인증 불가. 차종별 장부는 원 수요량과 미완료를 계속 유지한다.

## C4. 자원·격리 및 중단조건

고정 `N≥1`, `1≤K≤8`, `6NK+3K≤2,000,000` 스칼라 예산. `lanes*dx` metres와 class footprint in metres를 구별한다. **셀 길이가 한 차량 길이보다 작아도**, 실수밀도 셀에는 fractional vehicle mass가 있을 수 있어 부정확한 `footprint≤dx` gate를 제거했다. 다만 실제 셀 점유길이 총계는 언제나 제한한다. 잘못된 입력/체크포인트는 기존 상태를 변경하지 않고 예외 반환한다.

새로운 backend는 명시적으로 선택한다. Python은 독립 계산 기준, Rust는 정량 비교 대상이다. 필요 이상의 native thread, global engine rewrites, 기존 V1 전체 회귀·acceptance를 실행하지 않는다. Rust unit tests의 PyO3 linker 환경은 `RUSTFLAGS="-C link-arg=-lpython3.12"`로 명시했다.

## C5. 실제 산출된 구현

| 파일 | 계약 |
|---|---|
| `src/metroflow/v1/kcmb.py` | class/config/state model identity, 6-moment generator, Python kinetic+FV reference, strict state checks, JSON checkpoint |
| `crates/metroflow-rust/src/v1_kcmb.rs` | Rust bounded array update, physical metres/capacity gates, class ledger, internal Rust unit test |
| `crates/metroflow-rust/src/lib.rs` | 새로운 PyO3 class 명시적 등록만 변경; original solver/callback 유지 |
| `tests/research/test_kcmb_engine_20261118.py` | mixed class, red/spillback, restart, model identity, Riemann shock, Python/Rust |
| `tests/research/test_kcmb_generator_20261118.py` | 독립 RK4, moment cone, 정상 variance, 직접 sampled micro Markov process |
| `tests/research/test_kcmb_adversarial_20261118.py` | randomized class/clock, stiff/zero rates, huge pending, broken checkpoints |
| `tools/research/bench_kcmb_engine.py` | 동일 새 모형의 fixed workload Python/Rust 독립 프로세스 bench |
| `tools/research/kcmb_field_metrics.py` + 테스트 | GEH/flow MAE/speed RMSE paired-site/time/window scorer; calibration/holdout 분리·관측 중복 방지 |

## C6. 수정–검증 내역

- 처음 구현에서 Python 시험은 baseline 20 passed였고 새 kernel import 실패는 구현 부재를 드러내는 초기 단계였다. 이후 실제 native wheel 빌드 및 Python–Rust 일치가 확인됐다.
- 초기 점유상태가 있는 `initial_profile`에서 `released` 장부가 0인 결함을 실제 실패로 발견해 initial mass를 수량 장부에 기입했다.
- Riemann shock 시험에서 왼쪽/오른쪽 reservoir boundary 유량을 원래 해석해와 다르게 설정해 `L1` 오류가 커졌던 결함을 고정 boundary `q_L=.2veh/s`, `q_R=.25veh/s`로 정정했다. Mass-only shock shift와 실제 profile L1을 혼동하지 않는다.
- 연속 밀도 격자를 integer vehicle cell로 잘못 제한하던 `footprint>dx` 거절 조건을 제거하고 총 lane-metres 상한만 유지했다.
- Read-only scoped Python suite 155 passed, Rust lib 59 passed, `cargo check --workspace --tests --offline`, `rustfmt --check crates/metroflow-rust/src/v1_kcmb.rs`, Python compile 및 git diff check 통과. 실제 명령과 마지막 결과는 `artifacts/kcmb_coding_20261118/{SCOPED_PYTEST.txt,CARGO_CHECK.log,CARGO_TEST.log}`.

## C7. 구성한 물리적 문제를 실제로 풀었는가

- **[NUMERICALLY CHECKED]** 각각의 순간량 6개 생성자를 microscopic switch+continuous-speed law에서 별도로 유도한 `rhs`의 RK4와 48개 frozen-rate fixture에서 대조한다.
- **[STOCHASTICALLY CHECKED]** 직접 event-driven micro Markov trajectories 30,000개의 제어상태·속도1차·2차 모멘트와 kinetic propagation의 차이를 사전 고정한 표본허용치 `0.02` 아래에서 확인했다. 이는 stochastic numerical check이지 실차 현상과의 일치는 아니다.
- **[NUMERICALLY CHECKED]** 정상속도분산 `U² p*(1-p*)/(1+(alpha+nu)tau)`를 속도 2차 모멘트로 복원하고 균형식과 비교했다.
- **[NUMERICALLY CHECKED]** 1-class triangular homogeneous equilibrium Riemann 충격파 및 spatial L1, red gate, backpressure, lane-metres, 모델 ID/장부를 검증했다. 교차로 turning conflict, vehicle-level safe car following, class route FIFO는 NOT_IMPLEMENTED.
- Class별 `released=completed+pending+active`를 검증한다. Exogenous future demand를 빼먹거나 zero speed에게 허위 완주를 부여하지 않았다.

## C8. 정확도에 대응시킨 성능/재현 비교

**[MEASURED]** 같은 새 KCMB 모형, 64cells×2classes×600steps×dt1s, 동일 수요·신호, Python/Rust 각각 별도 프로세스, 순서 A/B/B/A 4회:

| backend | 4회 계산시간[s] | 중앙값[s] | 측정 RSS 범위[KiB] |
|---|---|---|---|
| Python | 0.67420,0.67815,0.69634,0.67377 | 0.67618 | 23376–24216 |
| Rust | 0.23772,0.23692,0.23775,0.23508 | 0.23732 | 24792–25520 |

측정 중앙값 속도비 Python/Rust **2.8492×**. Class별 종료 active mass Python/Rust 최대차 `3.55e-15veh`; source/complete/pending 표본 장부는 수치허용 내 일치. 각각의 Python 체크포인트 bytes와 Rust 체크포인트 bytes는 서로 다를 수 있으며 이는 rounding 순서 차이로, 같은 물리적 상태의 비교는 수치적으로 한다. 새 모형의 Rust 프로세스 RSS가 더 작다는 주장은 뒷받침되지 않았다.

원본 별도 연구 fixture에서 64cells×500steps 수요 scale 1과 1e5는 모두 state 774 scalars를 보유하고, 256cells×300steps는 3078 scalars다. 이 저장량 bound는 원래 5M daily OD, full-city 24h, 8GiB threshold의 성능 PASS를 보증하지 않는다. `PERFORMANCE_REPEATED.json` 및 각 benchmark JSON은 입력·자원·출력의 실제 측정치를 수록한다.

## C9. 한 번의 적대적 검토와 최소 수선

1. **관측자료 leakage [FIXED, BEHAVIOR RED→GREEN]:** 같은 `site_id`와 시간창을 calibration/holdout 양쪽에 두면 이전 점수기가 그것을 독립 표본으로 허용했다. 이제 동일 exact window뿐 아니라 동일 검지기에서 시각상 중첩한 창도 거절한다. `site_id`는 *방향과 고정 검지기를 구별하는 정합 키*로 제공해야 하고 지리 map-match 자체는 external obligation이다.
2. **Checkpoint parse budget [FIXED, BEHAVIOR RED→GREEN]:** 큰 비정상 JSON checkpoint를 역직렬화하기 전에 `4096+64*state_scalars` byte budget을 검사한다. 기존 모델 ID/shape/realizability 및 conservation 검사도 유지한다.
3. **낮은 수준 raw native 생성자의 계약 [OPEN, DOCUMENTED]:** Rust class에 임의의 비음수 transition matrix를 직접 전달해도 그것만으로 Markov 모형의 정당성이 증명되지 않는다. `KCMBCorridor(KCMBConfig(...),backend="rust")`가 등록된 class law로 matrix를 생성하는 지원 경로다. Production 진입 경로는 이 low-level API를 직접 사용하지 않는다.
4. **Finite precision 및 완전한 스펙트럼 안정성 [OPEN, NOT A BLOCKER FOR SCOPED PROTOTYPE]:** current uniformization은 긴 시간을 squaring으로 계산하고 `qdt>1e6`은 예산 거절한다. 무한시간의 machine bit-stability나 generic velocity distribution의 exact reconstruction을 본 testing이 보증하지 않는다.

## C10. 판정·재현 계약·후속 연결

**SCOPED_CODING_IMPLEMENTED / SCIENTIFICALLY_LIMITED; NOT V03 ACCEPTED.** 이 코딩 연구 범위의 opt-in 1D multi-class kernel은 실제 입력→실제 상태→수치검증 출력의 실행 경로를 갖춘다. 기존 `main`, V03 PR #41, 기존 Rust `v1_road.rs`, 지도·수요·여정 파일을 변경하지 않았다. Source/field data/geometry의 실측 정합은 아직 불가능하므로 observation scorer는 실측용 준비도구이고 field score는 `NOT_MEASURED`이다.

```sh
cd /home/cosmosapjw/worktrees/urban-traffic-kcmb-coding-20261118
.venv/bin/python -m pytest -q \
 tests/research/test_kcmb_engine_20261118.py \
 tests/research/test_kcmb_generator_20261118.py \
 tests/research/test_kcmb_adversarial_20261118.py \
 tests/research/test_kcmb_field_metrics_20261118.py
PYO3_PYTHON=.venv/bin/python maturin develop --release \
  --manifest-path crates/metroflow-rust/Cargo.toml
RUSTFLAGS="-C link-arg=-lpython3.12" cargo test --workspace --lib --offline
cargo check --workspace --tests --offline
.venv/bin/python tools/research/bench_kcmb_engine.py \
 --backend rust --cells 64 --steps 600 --demand-scale 1 \
 --output artifacts/kcmb_coding_20261118/repro.json
```

다음 실제 과학·개발 작업은 **source/route identity와 multi-direction junction/merge–diverge 수송을 어떻게 보존할지**, 그리고 inD/UTD19/NGSIM 등의 서로 정합되는 실제 관측자료와 field calibration/holdout을 어떻게 연결할지를 별도의 모형확장 목표로 다루는 것이다. 이 범위를 이번 좁은 후보 구현에 모두 해결한 것으로 표시하지 않는다.

전제 문서: `docs/research/KCMB_MICRO_KINETIC_MACRO_THEORY_R1_R10_20261118_KO.md`. 이번 최종 `artifacts/kcmb_coding_20261118/CODING_RECEIPT.json`은 실제 코드 SHA, 한정 시험 및 수치/성능 영수증을 포함한다. Native subagent spawn 도구는 없어 `NOT_RUN`이며 단일 작업자 + 독립 수치 oracle에 의존했다. 원격 게시/PR 생성/merge/release는 `NOT_RUN`이다.
