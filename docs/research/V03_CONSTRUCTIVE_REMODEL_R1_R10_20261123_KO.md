# MetroFlow 구성적 재모델링·실행 연구 — R1–R10 / C1–C10

## R1 / C1 — 원 목적·현재 실패·새 모델링 범위 (완료)

이번 사용자는 직전10단계 종료 커밋 `90bfca2c2ddf081cbdf40d11b95ff820837d03b5` 이후의 새 이론/코딩 결합10단계를 명시적으로 요청했다. 기준 local HEAD와 원격 branch의 동일성을 확인했고, 추적 파일이 깨끗한 상태에서 `research/v03-constructive-remodel-20261123` 작업공간을 분리했다. 이전 루프의 종료는 그대로 보존하며 이번 요청을 그 루프의 미완료나 자동 재시작으로 해석하지 않는다.

현재 사용자 승인은 원 목적과 직관을 유지하면서 새 모델을 적극적으로 탐색·구현·연구 코드에 통합하는 범위까지 포함한다. 새 모델의 보존량·FIFO/인과성·관측량 대응, 실수 산술 동치와 f64/wire 동일성, 근사의 오차를 구분한다. 현 V03의 원 수요·matrix·dt·cap·수용문턱을 모르게 바꾸지 않는다. 기존 main 통합·release tag·전체 repository CI 보류는 유지한다.

### 기준 증거와 실제 열린 문제

기준 source는 `e6a49b7c0cd598ff480a1d3a421fa9e8ae57f227c311d514556a394f137b29db`,native는 `6a6d48c8986ce1ffe1108afa145707b556345f0e7572c7c4f34e7e64b19da808`이다. 원 PLAN v1.1.26과 matrix의 SHA,actual Python/RAM/disk,직전 raw 영수증의 전체 내용·SHA를 `artifacts/v03_constructive_remodel_20261123/R1_baseline.json`에 보존했다. 실제 RAM은31.25GiB이고 과거64GiB 목표를 관측값으로 쓰지 않는다.

직전 후보의25,730s checkpoint는5,523,765,378B이며 full-wire SHA `c8335535408e13266bb4b5f15b10d0854701e644421ae3e8183d7c468d9183c9`다.25,740s는 정상 반환·장부 검사를 통과했으나 저장의 `native snapshot Arc census preflight`가6,807,602,661>6,442,450,944B로 실패했다. 이 상태는 저장된 predecessor가 아니다. 원 time-zero/hourly86,400s 요청은764.18s 뒤 Journey stored/working guard와 복구 저장 census7,221,056,145>6,442,450,944B에서 실패했고,25,200s의 출발 전 all-zero 장부 상태만 durable/fresh 검증됐다. 이 정확한 실패와 그 source를 재사용하며 바뀌지 않은 긴 실패 실행을 먼저 되풀이하지 않는다.

이론의 직전 성과는 τv′=V−v의 기억과 완료된 matched passage 적분에서 미래 통과시간을 구성하는 명제다. 양의 강제력/속도 하한에 의존하므로 실제 정지·spillback으로 적용 범위를 확장하는 것은 여전히 열린 과제다. 또한 원래 mesoscopic 목적과 packet row 폭증을 함께 보아 누적 수송·mass-rank·cohort 표현을 새로 평가한다. 이미 수행한 proportional merge/Γ-envelope를 새 결과로 재명명하지 않는다.

### 이번10단계의 판별 가능한 산출물

| 단계 | 이론/코딩을 연결한 목표 | 실제 완료 근거 |
|---|---|---|
| R1/C1 | 원 동기와 새 모델링 권한,source/실패 기준 | 원 역사·current hash·실제 영수증 연결 |
| R2/C2 | 원전·과거 결과 재사용과 식–코드 대응 | 세 모델 경로의 근거,현재 census/Journey 수명 조사 |
| R3/C3 | 모델 전제·동치·알고리즘 정합성 | 계산 가능한 판별례와 유효한 production-path RED |
| R4/C4 | 발산적 구성에서 후보 선택·실행 DAG | 실제 계산에 따른 선택과 disjoint ownership,재개 admission |
| R5/C5 | 새 명제 증명·선택 모델/수정 구현 | 정의→유도→computational form→실행 코드 |
| R6/C6 | 한정 독립 이론 검증·소프트웨어 검증 | 새 범위의 독립 재유도,같은 명령 RED→GREEN,관련 gate |
| R7/C7 | 모델의 물리·관측량 대응 | 보존·FIFO·극한·반례·원 기준과의 구체적 비교 |
| R8/C8 | 원 규모에서 길이/실행시간 증가 | 실제 wall/RSS/반환·저장·fresh 결과와 원 hourly 비교 |
| R9/C9 | 독립 코드 심사 통합·최종 전제조건 | 최종 후보3도시 preparation과 source-bound 준비도 |
| R10/C10 | 증거·모델 판정·재개점 보존 |10단계 종료/push,미완료와다음최소과제 구분 |

원 release 실행 조건은100,000residents/case,86,400s,3도시×3회,dt10s,별도dt5s refinement,wall7200s/process8GiB/native6GiB다. 준비도는19/21 구현·한정 검증,5/21 ACCEPTED,직접 선행3/3,최종 candidate preparation,full-day0/9를 분리한다. 아직 새 후보를 만들지 않았으므로 직전 후보의3/3 preparation을 이번 새 코드의 검증으로 선반영하지 않는다.

### 병렬 작업과 자원

Native 조사/구현은 `checkpoint_validation_bridge`가 `v1_road.rs,v1_journey.rs,v1_engine.rs`를 소유하고 초기에는 read-only로 실제 원인을 확인한다. `stop_go_model`은 정지·재출발/누적 서비스/관측 모델의 세 경로를 실제 수식·작은 계산으로 비교한다. `remodel_history`는 원 목적과 과거 표현 연구를 대조하고 mass-rank/누적 수송의 독립 대안을 구성한다. 부모는 공유 보고서·PLAN 판단·runner·통합·commit/push·실제 큰 실험을 소유한다. Cargo와 전체 규모 물리 실행은 겹치지 않게 조정한다.

첫 검증/구성 pass와 위험에 근거한 한정 독립 pass를 사용한다. 같은 근거의 감사 재귀나 의미 없는 테스트 수 증가는 하지 않는다. 모델/수치/구현/resource/환경 실패를 구분하며, 실제 새 원인이 확인된 경우에만 다음 수정을 진행한다. 문서·hash·노드 수가 과학적 진전의 대용이 되지 않도록 한다.

### 이번 턴과 R1의 drift watchdog

기준은 `METROFLOW_ORIGINAL_INTENT_WATCHDOG.md`에 연결된 최초 확인 가능 import0492364,constitution6524500,active-meso3d83db0와 현재 T02/T04/R01/R02다. 원 목표는 설명 가능한100k 도시의 mesoscopic 물리,목적지/행동/정보를 보존한 수송,혼잡에서 경로·접근성·지연 feedback으로 가는 연결이다. 이번 후보는 단순히 더 많은 guard를 통과하는 것보다 정지·재출발과 누적 수송의 새 구성으로 실제 관측/실행 문제를 바꾸는지 판별한다.

판정은 `ALIGNED_WITH_OPEN_OBLIGATION`이다. 사용자 새 모델링 승인을 과거 문구로 막지 않고, 새 모델을 기존 V03과 동일하다고 미리 선언하지 않는다. 위 모델 경로의 구체적인 성립 여부와 실제 큰 실행은 뒤 단계에서 판정한다.


## R2 / C2 — 원전 이식·새 운동 명제·실제 owner 수명 (완료)

R2_theory_portfolio.md/.py/.json에 서로 다른 세 경로의 전제, 직접 유도, 판별 계산과 원전 사전을 보존했다. 주후보 A는 clipped finite-response의 유한창 추진량, B는 운동과 분리한 FIFO 공동 서비스, C는 두 완료 운동 적분을 이용한 초기속도/상수 forcing 식별이다. C의 stationarity/관측 의무가 더 크므로 A+B를 우선한다. 기존 cumulative inverse와 network calculus 자체는 재사용이며 신규 결과로 세지 않는다.

새 운동 명제는
\[
\dot v=\operatorname{clip}((V-v)/\tau,-B,A),\quad
0\le V,v\le b,\quad A>0,\ B\ge0,\ \tau>0
\]
에서 \(\eta=\min(1,A\tau/b)\)와 \(\dot v\ge(\eta V-v)/\tau\)를 증명한 뒤, 각 선언된 \(H\)-창의 \(\int V\,dt\ge J>0\)를 적분 kernel의 최악 배치와 결합한다.
\[
L_n=\tau v_0(1-e^{-nH/\tau})
+\eta\left[nJ-b\tau(1-e^{-J/(b\tau)})
\frac{1-e^{-nH/\tau}}{1-e^{-H/\tau}}\right]
\]
는 \(nH\)의 실제 거리 하한이다. \(L_n\ge\ell\)로 유한 도달상한을 구성한다. 양의 순간 최소속도를 강요하지 않는다. 정확한 증명, 창 정렬, 유효 horizon, sharpness의 비활성 clipping 조건은 포트폴리오에 있다.

T02/T04를 다시 읽어 연속 운동 속도와 신호·하류 수용에 따른 경계 대기를 구분했다. 별도 FIFO 단계의 실제 가용률은 같은 movement의 \(c=\min(Cg,R)\)이다. \(0\le Cg,R\le C\)와 각 창의 적분 하한으로
\[
J_s=\max(0,J_g+J_r-CH_s)
\]
를 구성한다. \(J_s>0\), 사전에 보증된 rank 질량 \(W\), 적절한 창 phase 조건에서 전체 outlet upper는 \(NH+\lceil W/J_s\rceil H_s\)다. 미래 네트워크가 이 전제를 만족한다고 가정해 버리지 않는다.

실제 Python source characteristic 비교640개와 Fraction pointwise 비교4,356개를 실행했다. \(H=8s,J=16m,b=4m/s,\tau=2s,A=B=1m/s^2,v_0=0\)인 clipped 예제에서20m 실제 운동 도달15.139484898s, 실제0-service 대기6s,5veh 마지막 rank 출구23.639484898s를 얻었고, 사전 구성 상한34s 안에 있었다. 8→16→32→64s oracle horizon도 실행했다. 이 결과는 원100k full-day 실행 증거가 아니다.

Le Boudec–Thiran 저자 배포본의 strict service/variable capacity/concatenation과 Farhi–Haj-Salem–Lebacque의 forward demand–backward supply 모델을 직접 확인했다. 원전 URL과 source→target 대응은 포트폴리오에 있다. Exa/Parallel/SciSpace를 실제 사용했고 Wolfram의 두 MCP 내부 오류는 검산 성공으로 바꾸지 않았다. 이 명제의 전 세계 최초성은 주장하지 않는다.

### C2 실제 소스의 구조적 원인

부모와 native 담당자가 독립적으로 현재 소스의 동일 수명 구간을 읽었다.

- v1_engine.rs::snapshot_source_owners: census를 할당하기 전에 event input/current를 모두 계상하지만, 뒤에서는 이미 존재하는 shares_event_arc의 allocation-free identity로 중복 backing을 제거한다. 같은 snapshot의 실제 Arc identity는 census 없이 먼저 증명할 수 있다. 이 경로의 개선은 아직 없는 미래 sharing을 선반영하는 것과 다르다.
- v1_journey.rs::advance의 prepare 전 parent reservation: 실제 input/current 두 road/event owner만 공존하는데 \(2\max(R_i,R_c)+2\max(E_i,E_c)\)를 쓴다. 실제 source 합과의 과잉분은 정확히 \(|R_i-R_c|+|E_i-E_c|\)다. 적용 가능한 수명에서 각각의 실측 합을 쓰는 후보를 구성했다.
- Journey의 local \(3\max(retained,dynamic)+scratch+65536\), decoder/validator, 원6GiB cap은 이 조사로 완화하지 않는다. 원 hourly의 실제 첫 실패 세부 subsite와 내부 clock은 미관측 상태로 보존한다.

코드의 다음 판별은 실제 capture/save/독립 event owner/다른 clock/fresh restore와 작은 예산 거부를 포함하는 behavioral RED다. 현재 단계는 원인과 구성 후보 확인이며 아직 수정 효과를 실제 큰 실행으로 주장하지 않는다.

### R2 drift watchdog

원 active-meso의 자기구동·유한 응답·정지/재출발을 명제의 직접 대상에 두고, 실제 node 대기를 별도 질량 시계로 보존했다. memory admission은 물리 법칙·장부·wire·수용문턱을 바꾸지 않고 실제 수명을 계산하는 방향이다. 판정 ALIGNED_WITH_OPEN_OBLIGATION: 새 배경 이론은 직접 유도됐고 조건부 양성 판별을 통과했지만, native의 인과적 추진량/서비스 보증과 전체 규모 효과는 다음 단계 의무다.


## R3 / C3 — 전제의 실행 계약·역사 재평가·behavioral RED (완료)

A+B 경로의 단위, 인과적 증거 제공시각, 유효 horizon, aligned/sliding 창, ahead-rank 질량의 뜻을 R3_theory_contract.md로 고정했다. 유한한 보증 창 안에서 상한을 만들지 못하면 HORIZON_UNCERTIFIED이며 물리적 도달 불가능으로 해석하지 않는다. 실수 산술 정리와 float guard-margin 계산도 구분한다. 일반 native network에 미래 J/J_s/W가 자동으로 보장된다는 주장은 하지 않는다.

### 역사에 근거한 구성적 재접근

R2_model_history_map.md는 최초 확인 가능한 원 PRD/constitution/active-meso의 commit와 blob까지 추적한다. 20261117의1.01–1.08배 병합 한계는 인접한 상수 비례 조성 병합에 대한 것이고, 모든 exact 표현에 대한 불가능 정리가 아니다. 20261121/22의 단일 source prefix·inverse service·delay 적분은 이미 존재한 결과로 명시했다.

이번 추가 구성은 **내부 이질적 조성을 보존하는 같은 parent의 인접 rank view 합성**과 **다중 upstream의 보존적 merge lift**다.
\[
W(t)=\sum_j A_j(t),\qquad
C_g(t)=\sum_jF_{jg}(A_j(t)),\qquad
F^{in}_g(z)=C_g(W^{-1}(z)).
\]
출생 모멘트도 동일한 합성을 쓴다. 연속·비감소 유입과 보존된 source-law knots 아래에서 질량/출생 모멘트 보존, 각 upstream의 prefix 순서, 수치 구간 분할공변을 증명했다. W의 plateau에서는 모든 A_j도 상수여서 역함수 선택의 모호성이 측도를 바꾸지 않는다. 동시 유입의 개별 차량 순서를 새로 만들어내지 않는다.

정확 Fraction 원형은10개 서비스 창(0-service2개)의70 scalar를 mutable head-split oracle와 일치시켰다.8개 view를 한 구간으로 합쳐도 내부3개 profile은 남는다. 다중 입력은2개 실제 profile과6개 수치 세분 구간 및 직접 누적 역상을51개 rank/408 scalar에서 일치시켰다. 전체 평균 closure는 첫1veh 조성에 각각1/6veh,13/40veh 오류를 내므로 채택하지 않는다. 이것은 새 표시법만의 제안이 아니라 실행된 구성과 반례다. 다중 link의 essential-knot 증가, f64 연산순서와 native wire 동치는 아직 미증명이다.

### 실제 수정 전 실패

현재 production을 유지하고 test-only Rust fixture를 추가했다. C3_source_discovery_valid_RED.log의 동일 command는 exit101, **3 behavioral RED / 3 PASS**다.

| 경로 | 실제 RED 근거 |
|---|---|
| capture/zero-step advance | census77,123,790B > 고정cap76,959,514B |
| 실제 save | 동일 census 오류; 이미 같은 event backing328,552B는 하나만 살아 있음 |
| 실제 coupled Journey prepare | parent 중복 reservation 때문에 local unchanged3J guard 실패; 필요한 local10,882,840B와 pool11,377,428B를 기록 |

독립 동일값 event Arc는 계속 거부됐고, 수정 후 필요한 census보다1B작은 예산도 거부됐으며, 독립 fresh decode/load/restore/full-wire control은 통과했다. 첫 fixture 시도의 capture 준비단 assertion 실패는 초기 log에 보존하고 behavioral RED로 세지 않았다. 위 valid_RED만 수정 전 행동 증거다. fixture의 고정 예산·데이터·command를 그대로 두고 production만 수정해 GREEN을 확인할 예정이다.

재개 runner도 별도로 실제 RED를 확보했다: 직전 최종 후보의 정확히 저장된25,730s raw receipt만 새 native로 연결하는 허용 사례가 실패하고, 변조 receipt/저장 실패25,740s의 거부2개는 통과했다. 임의 cross-version 상태 허용으로 우회하지 않는다.

### 실제 실행 저장공간 전제

직전 루프에서 내가 만든 소비 완료 duplicate5,523,765,378B checkpoint를1,005,577,213B zstd로 보존했다. 전체 원본과 전체 압축 해제 byte count/SHA c8335535…가 일치한 뒤 raw duplicate만 제거했다. 다른 역사 worktree의 동일 full-wire seed는 그대로 있다. C3_archive_consumed_c8c40.json에 원경로/새경로/archiveSHA/full verification을 기록했다. 관측 여유 공간은13,236,031,488B가 됐다. 물리 준비도나 V03 통과 수를 이 작업으로 올리지 않는다.

### R3 drift watchdog

원 목적의 bulk mass, route/class, 실제 birth clock, FIFO/동시구간 exchangeability와 불변 상태를 유지하는 표현을 선택했다. 조성 평균화 반례를 직접 검산했으므로 원래의 관측 정보를 단순 합계로 대체하지 않는다. 판정 ALIGNED_WITH_OPEN_OBLIGATION. 주이론의 stop/restart 조건과 표현 모델의 retained profiles는 서로 다른 의무이며, 둘의 연결은 실제 후속 계산으로 판별한다.
