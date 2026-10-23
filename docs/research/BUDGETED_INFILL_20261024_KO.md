# 도로 선분 접속을 포함한 예산 제한 도시 조밀화

기준 커밋: `30b6c9bff50a62c41f1a4eb1de792be919bd4f10`. 날짜: 2026-10-24 KST.
실행 경로: `metroflow.city.formative_infill.refine_city`. 기존 기본 생성기는 변경하지 않는다.

## 연구 질문과 선택

이전 생성기는 정착점 연결과 loop 형성을 수행하지만, 새 도로를 기존 선분 중간에 접속하고 그 도로를 분할하는 연산이 없었다. 이번 질문은 기존 연결성·평면성·형성 이력을 보존하면서 유한한 추가 도로길이 안에서 큰 블록을 세분할 수 있는가다. 지형 비용, 전역 network-design 최적화, 국소 face 분할을 비교하고 세 번째를 선택했다. 지형·수계는 보류하고, 오류를 검출할 수 있는 작은 위상 연산을 완결한다.

Strano et al. [1]의 exploration/densification 구분과 역사적 주요 도로의 지속성을 개념적으로 재사용한다. 이 논문이 아래 점수나 2 km 예산을 추정해 준 것은 아니다. 외부 관측자료 학습·도시 calibration은 없다.

## 구성과 직접 유도

양의 부호 있는 면적을 갖는 단순 bounded face에서 서로 인접하지 않는 두 경계 edge를 선택한다. 각 중점에 junction을 만들고, 그 중점들을 잇는 chord를 추가한다. 두 기존 edge는 각각 두 조각으로 분할된다. 따라서 한 연산마다

    ΔV=2, ΔE=3, ΔC=0, Δ(E−V+C)=1.

원래 경계의 총 길이는 유지되므로 전체 도로길이 증가량은 chord 길이와 같다. 두 daughter polygon의 shoelace 면적 합은 parent 면적과 같다. Wolfram과 사각형 공개 API 시험으로 이를 확인했다. 면적/길이 단위는 m²/m다.

교차·T접촉·공선중첩 검사, 내부 점 검사, 두 daughter의 양의 면적을 모두 요구한다. bridge가 붙어 정점이 반복되는 face boundary는 단순 polygon인 척 처리하지 않고 후보에서 제외한다. 하나의 적격 face만 있다는 보장은 없으며 후보가 없으면 정상적으로 원본을 반환한다.

비용 예산은 **추가 중심선 길이**이지 화폐·용지보상·철거비가 아니다. 기본 후보 제한은 상위 24개 단순 face, 최대 8개 chord, 총 추가길이 2000 m, 한 chord 900 m 이하, 경계 daughter segment 40 m 이상이다. 짧은 미세 접속과 매우 얇은 daughter를 줄이기 위해 daughter 면적은 10000 m² 및 parent의 15% 이상이어야 한다. 이 수치는 미보정 연구 prior다.

## 점수와 시각 감사에 따른 수정

최초 후보는 큰 면적과 면 분할의 균형을 보상했으나 실제 출력에서 4개 도로가 북쪽 외곽에 몰렸다. 면적만으로 도시 조밀화를 대신한 편향이다. 다음 접근성 prior를 도입했다.

    A(x)=Σ_c attraction_c exp[−|x−x_c|²/(2R²)], R=1100 m.
    balance=4 A1 A2/(A1+A2)².
    alignment=(1+cos(4(θ−φ_c)))/2.
    score=area × balance × (0.25+0.75 alignment) × A(midpoint)
          / (1+length/sqrt(area)).

이는 중심지 주변을 선호하게 하는 명시적 가정이다. 실제 통행수요·지가·토지소유·개발허가의 대체물이 아니다. 같은 면적의 두 블록 중 가까운 중심지가 있는 블록이 edge ID tie-break보다 우선해야 한다는 실패 테스트를 먼저 재현하고 수정했다. 원래 외곽 집중 그림과 결과도 보존했다.

## 시간·identity 계약

조밀화는 원본 성장 종료 후의 별도 epoch다. 반환값은 불변 `before`, 새 `after`, event ledger다. ledger에는 retired edge ID/원래 birth, child ID, junction ID, chord ID, 추가길이·잔여예산·면적이 있다. 기존 도로의 primary/secondary 분류는 두 child에 계승한다.

최종 그래프에서 `birth_epoch<=t`만 필터링해서 과거를 복원하면 retired edge가 사라지는 문제가 있다. 과거 authoritative snapshot은 `before`이며, split 사건은 ledger로 해석한다. 동적 교통 실행 중인 도로 ID의 in-place 변경 또는 차량 상태 이관은 구현하지 않았다. 두 모델의 결합 시험은 지도를 먼저 고정한 뒤 시작한다.

## 실제 실행 결과

새 테스트 5개와 기존 지도 테스트 13개, 총 18개 통과. 기본 320-node 사례 및 3 seeds × 2 scales를 합친 7개 생성 사례에서 연결 성분=1, primary 성분=1, 검출 교차=0, raw bounded faces=cycle rank, 길이 ledger 오차<1e-7 m였다.

기본 실현:

| 항목 | 전 | 후 |
|---|---:|---:|
| Nodes | 320 | 328 |
| Edges | 516 | 528 |
| Cycle rank / raw bounded faces | 197 | 201 |
| 면적 필터 통과 blocks | 193 | 197 |

추가 도로 4개, junction 8개, 추가 길이 1949.133547 m. 2000 m 예산을 넘지 않았다. 최종 fingerprint는 `b00d913826690e04ed8bb0555b093bf0fefef4441bfceb73de97a35de781ce13`다. 기본 실현에서 새 junction의 최소 진입각은 약 38.87도지만, 일반 입력에 대해 이 각도를 보장하는 gate를 추가한 것은 아니다.

시각 검수: 수정 후 1개 외곽과 3개 내부 도로로 분산됐다. 다만 기존 망의 각진 선분, 삼각형, 큰 외곽 face는 남는다. 이를 숨기기 위해 색상·렌더링으로 현실성을 꾸미지 않았다. 지도 전체를 실제 도시와 동등하다고 판정하지 않는다.

## 코드와 재현

`src/metroflow/city/formative_infill.py`: 후보·분할·ledger·불변 결과.
`tests/test_formative_infill.py`: 면/길이/예산/replay/중심지 prior.
`tools/run_infill_research.py`: 7개 실제 지도와 결과 JSON.

```bash
PYTHONPATH=src python -m pytest -q tests/test_formative_growth.py tests/test_formative_history.py tests/test_formative_infill.py
PYTHONPATH=src python tools/run_infill_research.py --output-dir artifacts/infill_run
```

Cores는 stdlib-only. 검증 환경은 Python 3.13.5, 테스트만 pytest, PNG는 선택적 matplotlib다. 전체 저장소 CI와 Python 3.12는 미실행. 독립 모델 reviewer는 없었고 직렬 구현·반례·CAS·실제 생성·시각 검수로 확인했다.

판정: 유한 예산의 위상적으로 일관된 infill 연산은 구현 검증됐다. 금전적 최적화, 실제 토지이용/수요 타당성, Braess-free network design은 주장하지 않는다. 도로 추가가 사용자 통행시간을 항상 줄여야 한다는 조건을 넣지 않았다.

[1] E. Strano et al. (2012), Elementary processes governing the evolution of road networks. Scientific Reports 2, 296. DOI: 10.1038/srep00296. 원 논문 HTML의 exploration/densification 및 backbone 논의를 확인했다.
