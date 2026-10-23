# 도시 형성사·블록 조밀화: 후속 이론 및 코딩 연구

기준: `29d67b2e095ebe1151e9d5a14b80fb323c1e327c`. 실행: Python 3.13.5, 표준 라이브러리 계산 코어. 기존 authoritative/default 생성기는 변경하지 않았다. 이 문서는 실제 구현과 국소 검증 범위의 명세이며 도시 현실성 인증이 아니다.

## 연구 선택과 근거

후보는 지형·수계 추가, 역사적 pruning, 기존 형성사 모형의 인과성 교정과 블록 내부 조밀화였다. 먼저 재현된 인과성·위상 결함을 해결하고, 현재 mesh에서 기존 도로를 보존하는 조밀화 연산을 채택했다. 지형을 덧붙여 잘못된 이력을 가리는 방향은 택하지 않았다. Strano 등 [1]의 탐색/조밀화 구분과 역사적 backbone 지속성은 메커니즘 재사용의 근거다. 그 논문도 지역·시대 밖의 일반화를 제한하며, 여기서 계수나 실제 도시 분포를 fitting하지 않았다.

## 기준선 반례와 수정

정사각형 하나의 내부·외부 half-edge 순환을 reversal-invariant key로 합쳐 bounded block이 0개가 됐다. 순환 방향을 보존하는 rotation-only key로 교정했다. `raw_bounded_face_count`와 면적 필터 후 block 수를 분리하고, 고립 정점을 포함해 C를 계산하여 μ=E−V+C와 raw face 수를 비교한다. 면적 필터로 제외된 면은 위상에서 사라진 것이 아니다.

미래 nucleus를 이전에 채택된 정착점에 옮기는 반사실 실험에서 탄생 이전 점 29개가 바뀌었다. 초기 최소간격 검사에 미래 nucleus가 이미 들어가 있었기 때문이다. nucleus는 birth epoch에만 삽입하고, settlement와 centre RNG stream을 분리하며, epoch별 도로 비용에는 활성 centre만 사용한다. 이 비예측성 계약은 N, T 등 전역 계획을 고정한 미래-centre 위치/방향 개입에 관한 것이다. 전역 계획을 바꿔도 과거가 불변이라는 주장은 아니다.

최종 그래프를 보고 만든 repair 도로 12개가 양 끝 node의 birth epoch로 소급 기록됐다. 실제 실행 epoch인 T−1로 교정했다. 마지막 보수 연산의 정보가 과거 역사에 들어가지 않는다.

기존 교차 판정은 proper crossing만 검사하여 unregistered T contact와 공선 overlap을 놓쳤다. bounding-box/orientation 검사와 cancellation 근방의 Fraction 부호 판정으로 보완했다. Fraction은 저장된 binary-float 좌표에 대해 정확하며 임의의 연속 실수 좌표가 정확하다는 뜻은 아니다. 같은 등록 node에서 만나는 도로는 허용하고 공유 endpoint에서 겹치는 ray는 금지한다.

## 방향 질서의 영가설

기존 best-axis 지표 A=max(|cos θ|,|sin θ|)는 A≥1/√2이며 균일한 무작위 각도에서도

    E[A] = 2√2/π = 0.900316316...

이다. 그러므로 floor 0.60은 선택력이 없고, 평균 0.9245는 강한 질서의 증거가 아니었다. 이 값은 호환용 진단으로 보존하되 gate에서 제거했다. 사전에 주어진 local survey axis α에 대해 signed fourfold order

    Q4 = (1/E) Σ_e cos[4(θ_e−α_e)]

를 추가했다. 균일 각도 null에서 평균0, 분산1/2이며 각도와 축이 독립이라는 조건이 필요하다. 축을 데이터에 맞춰 사후 선택한 fitted |Q4|와 다르다. 최종 Q4≈0.1783은 완전 격자가 아니라 약한~중간 정렬 신호다. Boeing [2]의 전역 orientation entropy는 지역별 축 혼합과 구분해 해석한다. Wolfram이 최소값·기대값·분산을 확인했다.

## 구성적 조밀화 연산

API: `insert_infill_chords(cfg, nodes, edges) -> list[FormationEdge]`.

`FormationConfig.infill_budget=0`이 기본값이다. 양수일 때 큰 bounded face부터 기존 junction 두 개를 잇는 chord를 시험한다. 중점이 내부에 있고, 모든 기존 도로와 유효하지 않은 접촉이 없으며, endpoint degree cap과 두 자식 면적 하한을 만족해야 한다. 후보 비용은

    J = max(A1,A2)/A + 0.10 l/√A.

이는 무차원 국소 heuristic이며 토지경제 평형이나 전역 최적화가 아니다. 채택된 chord는 실제 최종 epoch, hierarchy=local, role=face_infill로 기록한다. 모든 기존 node와 edge record의 prefix identity를 보존한다. 한 chord마다 ΔV=0, ΔE=1, ΔC=0이므로 Δμ=1이며 raw bounded face도 하나 증가한다. 자식 shoelace 면적의 합은 부모 면적이다.

내부 cul-de-sac 때문에 face boundary가 weakly simple하면 처음 구현은 그 면 전체를 건너뛰었다. 세 번째 보완에서는 O(V+E) low-link bridge 탐색으로 bridge를 **경계 순회에서만** 제외한다. 실제 도로는 삭제하지 않고 새 chord의 충돌 검사에도 그대로 사용한다. edge 중간 T-junction 생성, parcel subdivision, 철거는 구현하지 않았다. 후보 전수검사는 작은 연구망용이며 대규모 성능을 주장하지 않는다.

## 코드 및 실행

수정: `formative_growth.py`, `formative_growth_model.py`, `formative_growth_sampling.py`, `formative_growth_network.py`, `formative_growth_analysis.py`.
추가: `formative_growth_infill.py`, `tests/test_formative_growth_causality.py`, `tools/run_causal_map_next.py`.

```bash
PYTHONPATH=src python -m pytest -q tests/test_formative_growth.py tests/test_formative_growth_causality.py
PYTHONPATH=src python tools/run_causal_map_next.py artifacts/next_loop_20261023/map
```

동일 seed의 v1 byte/semantic identity는 유지하지 않는다. 인과성 오류와 RNG stream의 교정은 v2 모델 변경이다. v2에서 infill on/off 비교는 정착점·기존 도로를 정확히 공유한다. fingerprint에는 새 config와 실제 도로 geometry/chronology가 포함되어 cache identity가 바뀐다. 기존 runtime cache를 건드리지 않는다.

## 실행 결과와 시각 감사

최종 seed20261023, 25 km², nodes320, 기존 edges512에 chord16개를 추가했다. edges528, μ209, raw faces209, 채택 blocks208, 필터 제외1, Euler residual0, invalid contact0, graph/primary components 각1이다. 최대 face 면적은 357330.335937 → 251001.029548 m², accepted-block area CV는 약0.9071 →0.6967이다. 주도로 geometry는 그대로이며 새 local chord가 큰 내부 면을 나눈다.

최종 fingerprint: `cbfef4856d01ecd933efe10a6e5b9df9814f0650447d24415bff3b15f5d2c3b5`.

120/220/320 nodes, 12/20/25 km², seeds7/41/97의 9개 사례에서 기존 geometry 보존, Δμ=추가도로수, Euler, contact, chronology, 최대면적 비증가가 모두 통과했다. 기존5+추가11=16 tests를 실행했다. 초기8개 실패, infill2개 실패, spur1개 실패 로그를 각각 보존했다. 시각 감사는 실제 PNG를 읽은 동일 세션 검토이며 독립 reviewer가 아니다.

남는 형상 결함은 직선·다각형 느낌, 삼각형 구획, 큰 단일 land-use 영역이다. 색상은 heuristic이며 토지시장 결과가 아니다. 지형/수계, parcel, 접근성-토지이용 공진화, 관측 형태 보정, production-scale 검증은 이번에 수행하지 않았다. 지도 개선과 교통 개선은 별도 후속 브랜치이며 아직 이 생성망을 CTM에 직접 연결하지 않았다.

## 근거 상태와 다음 경계

문헌 지지: 탐색/조밀화 및 orientation 지표의 제한. 직접 유도/CAS: Euler 증분·영가설. 구현 검증: 인과성 반례, embedding/face 회귀시험. 수치 관찰: 9개 사례와 대표 지도. 미해결: 현실 도시 형태의 경험적 적합성. 상태는 `SCOPED-VERIFIED`, `NOT DEFAULT-READY`다.

[1] Strano et al. (2012), Elementary processes governing the evolution of road networks, Scientific Reports 2,296. DOI:10.1038/srep00296. Results: cell fragmentation and new-link classification; Discussion: limits of geographical generalization.
[2] Boeing (2019), Urban spatial order: street network orientation, configuration, and entropy, Applied Network Science 4,67. DOI:10.1007/s41109-019-0189-1. Orientation order quantifies a single grid, not functional or social order.
