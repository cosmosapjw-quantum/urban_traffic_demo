# MetroFlow 도시 교통지도 생성 적대적 재감사 및 수정 전략

**작성일:** 2026-08-24  
**대상 저장소:** `cosmosapjw-quantum/urban_traffic_demo`  
**대상 브랜치:** `audit/heldout-morphology-adversarial-report-20260823`  
**기준 소스 증거:** `main@e1979df281ac25a24a82fdea725422310f7c6807`, source tree `622dbe37790c5414141cd5d5531a2158aa56f7e5`  
**연결된 동결 증거:** `artifacts/heldout_morphology_adversarial_audit_20260823/`  
**문서 역할:** 기존 held-out 감사 산출물을 대체하지 않고, 현재 결함을 개발 가능한 순서로 재분류하는 remediation report

---

## 0. 감사 원칙과 범위

이 저장소는 단일 개발자가 직접 사용하는 개인 연구 코드다. 따라서 본 감사는 보안, 악의적 위변조, 다중 사용자 권한관리, 공급망 공격, 기업형 release governance를 threat model로 삼지 않는다. SHA-256, manifest, CI, replay는 오직 다음 목적으로만 평가한다.

1. 계산과 산출물의 재현성,
2. 코드 변경에 따른 회귀 검출,
3. 잘못된 과학적 주장의 조기 차단,
4. 장시간 연구 중 canonical state의 유실 방지.

추가 assurance가 실제 연구 결함을 줄이지 못하면 도입하지 않는다. 이번 보고서는 도시지도 **생성 알고리즘, 형태학적 의미, 외부 대조, 교통기능**에 집중하며 CAPR·신경망 경로선택 연구는 범위 밖이다.

---

## 1. 집행 요약

### 1.1 최종 판정

현재 `scalable_synthetic_v2`는 다음을 제공하는 강한 연구 substrate다.

- mm 정수좌표 기반의 결정론적 physical topology,
- surface/mainline/ramp/bridge/tunnel layer 구분,
- explicit DCEL과 bounded-face authority,
- bridge failure-group과 일부 구조적 redundancy,
- ring-radial·river-constrained 등에서 관측 가능한 구조적 grammar,
- source-to-artifact 재현성과 replay-friendly identity.

그러나 현 단계에서 **실제 도시 교통지도 생성기로 승격할 근거는 부족하다.**

\[
\boxed{
\text{정확한 구조적 substrate}
\;\not\Rightarrow\;
\text{현실적인 도시형태}
\;\not\Rightarrow\;
\text{좋은 교통기능}
}
\]

현재 판정은 다음과 같다.

| 판단 대상 | 판정 |
|---|---|
| topology/DCEL/static authority kernel | **보존** |
| `ring_radial` structural grammar | **보존·확장** |
| `river_constrained` bridge/barrier grammar | **보존·확장** |
| `grid_core` public semantics | **수정 필수** |
| `polycentric_tod` | **구조적 다핵성만 인정, TOD 기능은 미검증** |
| `superblock_mixed` | **macroblock 구조는 인정, 내부 접근·교통기능은 미검증** |
| `organic` compatibility ID | **curvilinear warped grid로만 인정** |
| v4 7-metric control table | **legacy/control diagnostic 전용** |
| `scalable_synthetic_v2` empirical morphology | **미검증** |
| traffic-functional validity | **미검증** |
| runtime/default promotion | **BLOCK** |

### 1.2 가장 중요한 결함

1. **`grid_core` 의미–기하 불일치:** held-out seeds `503,701,907`에서 모두 실패한다. semantic `surface-vertical` road의 약 8%만 실제 수직이고, 나머지는 row별 독립 x-axis와 monotone partial matching 때문에 대각선이 된다.
2. **새 generator에 대한 외부 holdout 부재:** v4 control table은 `scalable_synthetic_v2`를 측정하지 않는다. 기존 OSM extracts는 과거 calibration에 노출됐고 core bounding box와 municipality population이 섞여 있다.
3. **교통기능 검증 부재:** 구조적 모양이 달라졌다는 사실은 detour, 대체경로, 취약성, queue/spillback, travel-time을 보장하지 않는다.
4. **측정기의 범위 부족:** 7개 scalar street metric은 block area/shape, barrier connectivity, limited-access semantics, functional bypass, topology consistency를 충분히 식별하지 못한다.
5. **일부 public style 명칭이 구현보다 강함:** `polycentric_tod`, `superblock_mixed`, `organic`은 현재 검증된 구조적 범위를 넘어서는 기능적 인상을 줄 수 있다.

---

## 2. 동결 held-out 결과의 재해석

기존 audit package는 개발 seed와 분리된 `503,701,907`을 사용했고, 총 18개의 style-seed case 중 15개가 structural contract를 통과했으며 `grid_core` 세 건이 모두 실패했다. 이 결과는 단순 seed fluctuation보다 **grammar-level defect**를 가리킨다.

### 2.1 수치

| seed | core roads | axis-aligned | 전체 정렬률 | semantic horizontal | semantic vertical | 실제 수직 semantic vertical |
|---:|---:|---:|---:|---:|---:|---:|
| 503 | 3167 | 1724 | 0.5444 | 1600 | 1567 | 124 / 1567 = 0.0791 |
| 701 | 3178 | 1740 | 0.5475 | 1604 | 1574 | 136 / 1574 = 0.0864 |
| 907 | 3081 | 1681 | 0.5456 | 1556 | 1525 | 125 / 1525 = 0.0820 |

horizontal roads는 본질적으로 수평이므로 전체 axis-aligned 수에서 horizontal road 수를 빼면 실제 수직 connector 수를 얻을 수 있다. 세 seed에서 semantic vertical road의 약 91–92%가 대각선이다.

### 2.2 source-traceable root cause

현재 `scalable_topology.py`는 style별로 y-axis를 만들고, `superblock_mixed`를 제외한 대부분의 style에서 각 row마다 다른 x-axis를 만든다. `grid_core`도 각 row의 y좌표를 `fixed_mm`로 넣어 새로운 x-axis를 생성한다. 이후 인접 row 사이의 `surface-vertical` road는 동일 x-index를 잇지 않고 `_monotone_partial_match(lower_bank, upper_bank)`로 연결된다.

그 결과:

\[
x_i^{(j)} \neq x_k^{(j+1)}
\quad\Longrightarrow\quad
\text{semantic vertical connector가 대각선}
\]

이 된다.

따라서 실패 원인을 “held-out classifier가 지나치게 엄격하다”로 처리하면 안 된다. public label이 `Grid Core (Standard Uniform Lattice)`인 이상, shared x-axis와 정확한 직교 connector는 합리적인 최소조건이다.

### 2.3 정책 결정

- seed `503,701,907`은 이번 진단으로 소비됐다. 이후 **회귀셋**으로만 사용하고 새 holdout이라고 부르지 않는다.
- 수정은 threshold 완화가 아니라 shared coordinate authority 도입으로 한다.
- grid의 지역적 불균일성을 유지하고 싶다면 rowwise x-coordinate jitter가 아니라 block spacing field 또는 구역별 shared axis family로 표현한다.
- grid semantics를 포기하려면 style ID와 public label을 먼저 변경해야 한다.

---

## 3. 강점: 갈아엎지 말아야 할 것

### 3.1 exact topology substrate

다음은 이미 높은 비용으로 구축됐고, 현재 문제의 원인도 아니다.

- stable physical node/road identity,
- mm 정수좌표,
- explicit layer와 infrastructure type,
- exact same-layer crossing rules,
- DCEL face extraction과 area conservation,
- compiled/static authority cross-binding,
- deterministic seed/replay surface.

이 계층은 보존한다.

### 3.2 ring-radial과 river grammar

`ring_radial`은 multiple closed orbitals, winding-one cycles, spokes를 구조적으로 검증한다. `river_constrained`는 barrier와 bridge failure group을 1급 객체로 둔다. 둘은 새 generator가 단순 label variation을 넘어섰다는 강한 증거다.

수정의 방향은 이 grammar를 제거하는 것이 아니라, **scale-aware count, connectivity, 교통기능**을 추가하는 것이다.

### 3.3 honest compatibility boundary

`organic`을 “validated organic topology”가 아니라 “curvilinear warped grid compatibility ID”로 낮춘 것은 올바르다. 비슷하게 `polycentric_tod`와 `superblock_mixed`도 구조적 주장과 기능적 주장을 분리해야 한다.

---

## 4. 우선순위별 findings

## P0 — 과학적·runtime promotion blocker

### P0-1. `scalable_synthetic_v2`를 측정하는 독립 외부 benchmark가 없다

v4 morphology control table은 legacy/control/growth/OSM arms를 측정하지만 `scalable_synthetic_v2`를 포함하지 않는다. 따라서 v4 table의 재현성이 아무리 강해도 새 generator의 empirical validity가 되지 않는다.

또한 기존 OSM extracts는 과거 `spacing_scale` calibration에 사용됐고, core bounding box와 municipality 전체의 morphology를 혼용했다. 이는 새로운 holdout으로 재사용할 수 없다.

**필요 조치:** fresh OSM evaluation corpus와 sample-boundary policy를 별도 PR에서 고정하고, 새 generator 전용 benchmark를 만든다.

### P0-2. traffic-functional validation이 없다

현재 구조적 contract는 다음을 보장하지 않는다.

- OD reachability와 detour,
- 대체경로 수,
- articulation/bridge-edge 취약성,
- bridge/mainline closure 후 회복력,
- p95/p99 trip time,
- queue/spillback,
- route failure,
- conservation/replay under load.

**필요 조치:** morphology benchmark와 분리된 static-function 및 dynamic-traffic benchmark를 만든다. CAPR·NN은 제외하고 기존 baseline routing/flow만 사용한다.

---

## P1 — 생성기 수정

### P1-1. `grid_core` coordinate authority 결함

앞서 설명한 rowwise x-axis와 monotone matching을 shared x-axis로 교체한다. 이 수정은 surgical하다.

### P1-2. non-grid heterogeneity field가 물리적으로 거칠다

현재 development/terrain intensity는 50 m cell별 hash noise에 가깝다. 공간 상관길이와 gradient continuity가 없어 “terrain” 또는 “urban development field”로 해석하기 어렵다.

**필요 조치:** grid를 제외한 style에 deterministic multiscale correlated field v2를 추가한다. correlation length를 m 단위로 명시하고 동일 seed replay를 보장한다.

### P1-3. ramp 방향 의미론이 단순하다

generated road의 access direction이 기본적으로 양방향이면 하나의 ramp가 on-ramp와 off-ramp를 동시에 수행할 수 있다. topology correctness와 motorway traffic semantics는 다른 문제다.

**필요 조치:** ON_RAMP/OFF_RAMP 또는 one-way access contract, legal merge/diverge movements, at-grade mainline crossing 금지.

### P1-4. infrastructure count가 scale에 충분히 결합됐는지 미확인

gateway, ring, centre, bridge 수가 도시 면적 변화에 따라 어떻게 변하는지 명시적 budget이 필요하다. 25 km²에서 통과한 grammar가 250 km²에서도 같은 기능을 유지한다고 볼 수 없다.

**필요 조치:** area와 barrier geometry에 따른 bounded deterministic budget, 25/40/100/250 km² scale tests.

### P1-5. style별 기능 claim이 구조적 evidence보다 강하다

- `polycentric_tod`: centre와 hierarchy path는 있지만 transit service와 activity distribution은 없다.
- `superblock_mixed`: macroblock perimeter는 있으나 내부 motorized access, pedestrian/service layer, emergency access는 검증하지 않았다.
- `organic`: topology는 warped grid에 가깝다.

**필요 조치:** public capability registry와 display label을 한 SSOT에서 관리하고, style별 “implemented / not claimed” contract를 테스트한다.

---

## P1 — 측정과 외부 대조

### P1-6. 7개 metric은 block morphology를 보지 못한다

도로 길이밀도 \(\rho_L\)는 block area와 aspect ratio를 식별하지 못한다. 예를 들어 직교 block에서

\[
\rho_L = \frac{1}{s_x}+\frac{1}{s_y},
\qquad
A_b=s_xs_y
\]

이므로 같은 \(\rho_L\)에서도 서로 다른 \(s_x/s_y\)가 가능하다.

**필요 조치:** DCEL에서 다음을 측정한다.

\[
A_F,\quad P_F,\quad
\phi_F=\frac{4\pi A_F}{P_F^2},\quad
r_F,\quad
\rho_{\rm block},\quad
\text{perimeter hierarchy}.
\]

초기 PR에서는 값을 기록만 하고, 데이터를 보기 전에 임의 threshold를 만들지 않는다.

### P1-7. topology consistency가 acceptance hierarchy에 통합되지 않았다

same-layer proper crossing, unregistered touch, fragments는 7개 morphology metric과 독립적이다. 다음 hard invariant가 먼저 와야 한다.

\[
N_{\rm proper\ same-layer}=0,
\qquad
N_{\rm unregistered\ touch}=0.
\]

### P1-8. external corpus의 표본정의가 불명확하다

core extract와 municipality 전체를 같은 분포로 취급하면 orientation·dead-end·block-size 차이가 sampling artifact인지 generator defect인지 분리할 수 없다.

**필요 조치:** fixed-area core, administrative polygon, density-matched crop 중 하나를 사전 선택하거나 모두 별도 strata로 보고한다.

---

## P2 — 작은 계약 정리

다음은 별도 대형 assurance framework가 아니라, 관련 PR 안에서 함께 닫을 수 있는 작은 항목이다.

- supported style capability를 generator와 benchmark가 공유하는 SSOT로 만들기,
- skip reason을 enum/typed code로 만들기,
- unknown control-table schema를 명시적으로 거부하기,
- stale narrative 숫자를 artifact에서 자동 복제하지 않기.

이 항목만을 위한 독립 장기 프로젝트는 만들지 않는다.

---

## 5. 권장 rebuild 전략

### 5.1 전면 재작성: 반대

exact topology, DCEL, multilayer infrastructure, replay를 버리고 새 generator를 만드는 것은 이미 닫힌 결함을 다시 연다.

### 5.2 파라미터 튜닝만 수행: 반대

grid 결함은 spacing 값이 아니라 coordinate authority 문제다. 외부 validation과 traffic-function 부재도 파라미터 sweep로 해결되지 않는다.

### 5.3 selective rebuild: 권장

| 계층 | 조치 |
|---|---|
| exact topology/DCEL/static authority | 보존 |
| grid coordinate construction | surgical rebuild |
| non-grid correlated field | selective replacement |
| ramp/interchange semantics | selective replacement |
| ring/river grammar | 보존 후 scale/function 확장 |
| morphology measurements | block/face layer 추가 |
| external validation | 새 benchmark |
| traffic validation | 별도 benchmark |

---

## 6. 단계별 acceptance hierarchy

상위 단계의 좋은 점수로 하위 실패를 상쇄하지 않는다.

### G0 — exact geometry/topology

- same-layer proper crossing = 0
- unregistered touch = 0
- explicit layer transition
- compiled/static identity
- deterministic replay

### G1 — style structural semantics

- grid: shared axes, exact orthogonality
- ring: concentric winding cycles와 spokes
- polycentric: non-collinear centres, nonempty catchments, hierarchy paths
- superblock: 2D macrofaces와 perimeter hierarchy
- river: typed bridge/barrier redundancy
- organic compatibility: curvilinear embedding claim까지만

### G2 — block/face morphology

- \(P(\log A_F,\phi_F,r_F)\)
- block density
- perimeter hierarchy
- service gap
- internal motorized-edge density

### G3 — fresh external evaluation

- development corpus와 evaluation corpus 분리
- sample boundary 명시
- importer policy 명시
- held-out seed와 held-out city 모두 미사용 상태로 고정

### G4 — static function and resilience

- OD reachability
- detour distribution
- edge/node-disjoint alternatives
- articulation/bridge-edge share
- targeted closure
- bank/gateway connectivity
- functional bypass

### G5 — dynamic traffic

- completion/failure
- p50/p95/p99 travel time
- queue/spillback
- closure recovery
- conservation
- deterministic replay

### G6 — promotion decision

`APPROVE`, `HOLD`, `REJECT` 중 하나를 evidence로 결정한다. PR을 merge했다고 runtime default를 자동 변경하지 않는다.

---

## 7. PR 실행 계획

상세한 machine-readable 계획은 다음 파일이 source of truth다.

`docs/audit/URBAN_MAP_GENERATION_CODEX_PR_LIST_20260824.json`

PR은 반드시 직렬로 진행한다.

| ID | 제목 | 핵심 결과 |
|---|---|---|
| MAP-PR-001 | Grid Core Orthogonal Coordinate Authority | grid held-out failure의 root cause 수정 |
| MAP-PR-002 | Style Capability and Claim SSOT | style 이름과 구현 범위 정렬 |
| MAP-PR-003 | Correlated Development Field V2 | non-grid spatial field의 상관구조 도입 |
| MAP-PR-004 | Directed Interchange and Ramp Grammar | on/off ramp·merge/diverge semantics |
| MAP-PR-005 | Scale-Aware Infrastructure Budgets | 25–250 km² scale contract |
| MAP-PR-006 | Block/Face Morphology Measurements | DCEL 기반 block joint distribution |
| MAP-PR-007 | Fresh OSM Evaluation Corpus | calibration/holdout 분리 |
| MAP-PR-008 | Scalable V2 Empirical Benchmark | 새 generator 전용 외부 대조 |
| MAP-PR-009 | Static Function and Resilience Gates | 구조가 실제 경로대안을 제공하는지 검증 |
| MAP-PR-010 | Traffic-Functional Map Benchmark | baseline traffic에서 기능 검증 |
| MAP-PR-011 | Multiscale Freeze and Promotion Decision | 최종 승인/보류/거절 |

### 중단 규칙

- PR이 predecessor의 fail-closed invariant를 깨면 다음 PR을 시작하지 않는다.
- 결과가 부정적이면 threshold를 사후 변경하지 않고 `HOLD` 또는 `NEGATIVE_RESULT`로 기록한다.
- 새 test/manifest가 실제 defect class를 줄이지 않으면 추가하지 않는다.
- 개인 연구 코드의 생산성을 해치는 보안·기업형 governance 작업을 끼워 넣지 않는다.

---

## 8. 주장 정책

이 roadmap 완료 전 허용되는 표현:

> MetroFlow는 deterministic multilayer topology와 구조적으로 구분되는 synthetic morphology grammar를 제공한다. Held-out seed 감사에서 grid coordinate authority 결함이 발견됐으며, empirical urban realism과 traffic function은 아직 검증 중이다.

금지되는 표현:

- “실제 도시를 재현한다”
- “OSM과 동등하다”
- “traffic-optimal”
- “resilient by construction”
- “runtime production ready”
- “TOD를 구현했다” — transit/activity evidence 없이
- “organic city generator” — topology evidence 없이

---

## 9. 문헌과의 관계

외부 문헌은 구현 정답을 복사하는 용도가 아니라 측정 질문을 정교화하는 데만 사용한다.

1. G. Boeing, “Urban spatial order: street network orientation, configuration, and entropy,” *Applied Network Science* 4, 67 (2019), DOI: `10.1007/s41109-019-0189-1`.  
   방향 엔트로피와 simplified graph 정의의 기준을 제공하지만, block·traffic function의 충분조건은 아니다.

2. T. Courtat, C. Gloaguen, S. Douady, “Mathematics and Morphogenesis of the City: A Geometrical Approach,” *Physical Review E* 83, 036106 (2011), arXiv:`1010.1762`.  
   도시형태를 공간의 extension/division 과정으로 본다. 현재의 exact face authority와 향후 face subdivision 연구에 관련된다.

3. R. Louf, M. Barthelemy, “A typology of street patterns,” *Journal of the Royal Society Interface* 11, 20140924 (2014), arXiv:`1410.2094`.  
   block area와 shape의 결합분포가 street pattern의 중요한 fingerprint임을 보여준다.

이 문헌들은 MetroFlow가 empirical validity를 획득했다는 증거가 아니다.

---

## 10. 최종 조언

현재 프로젝트의 가장 큰 위험은 검증체계 부족이 아니라 **정확한 substrate 위에서 생성기의 과학적 질문을 계속 미루는 것**이다. 이제 더 많은 manifest나 generic audit framework보다 다음 세 작업이 우선이다.

1. grid coordinate authority를 실제로 고친다.
2. DCEL block distribution과 fresh OSM evaluation을 만든다.
3. 구조를 실제 traffic function으로 연결해 본다.

이 세 단계에서 부정적 결과가 나와도 프로젝트 실패가 아니다. 오히려 `scalable_synthetic_v2`의 어느 grammar가 연구도구로 유효하고 어느 grammar가 단지 시각적 variation인지 분리할 수 있게 된다.
