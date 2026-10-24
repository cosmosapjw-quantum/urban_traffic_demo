# 다음 연구 인계

저장소 `cosmosapjw-quantum/urban_traffic_demo`, 연구 브랜치 `research/axiom-gap-sight-information-20261024`.
이번 기준은 b546ba6d096ff1efabc40d44aafffb1c303db2ce, 지도 fae7ca986d0dfcffada08ff77b2c3e9472cf1d54, 교통 10737b2fb0e1396f1f8be97556cb66fdb5b6a9aa다. 최종 감사 HEAD는 실제 ref와 PUBLICATION.json을 읽어 확인한다.

먼저 AGENTS.md, 이 폴더 REPORT_KO.md, artifacts/gap_viability_20261024/FINAL_VERIFICATION.json과 RESULTS.json을 읽는다. 전체 역사·브랜치를 다시 감사하지 않고 변경 의존성만 읽는다. 원래 일곱 관찰과 순수 Python, 분포 기반 계산을 유지한다.

현재 도달점: 지도는 반응 중 순가속과 접근 시야 표본 검사를 지원한다. 개별 시선은 연속 지형 검사지만 관측 위치 전체에 대한 인증은 아니다. 교통은 x'=v,h'=w-v,v'=u,w'=aL의 질량대표점을 진화시키며 제동 전 과정의 최대 상대접근량으로 제어를 제한한다. 앞차의 aL는 여전히 외생조건이고 도시 active_suffix 10개 모듈은 바뀌지 않았다. 새 물리가 전 도시나 자기일관적 platoon에 통합됐다고 계승하지 않는다.

조건부 안전 가정: 현재 정확한 gap과 자기속도, truthful 과거 선두속도 보고, 앞차가속도>=-B, 제어의 즉시적용, 필요시 실제 full-braking fallback. gap 측정지연·잡음·actuator lag는 범위 밖이다. ViabilityError는 해당 보수적 certificate가 없다는 뜻이며 충돌불가피 정리가 아니다. 실패시 입력 checkpoint를 보존하고 위치나 질량을 조정하지 않는다.

다음 최소 구성은 선두차 가속의 조건부분포와 뒤차/선두차 주변분포의 일관성을 닫는 것이다. 현재 pair를 임의의 독립쌍으로 두고 전체차량량이나 도로길이를 이중계산하지 말라. Ring/단일도로에서 spacing 합, 유형별 질량, 속도분산, 동일 f1/다른 gap 상관을 먼저 잠근 뒤 갱신식을 선택한다. 추가로 정보지연된 gap을 다루려면 robust gap interval과 actuator 제약을 별도 유도해야 한다. 이번 안전조건에 뒤늦게 포함돼 있었다고 주장하지 않는다.

납품 격리 workspace에서 142passed, 부모참조12개 포함. full repo CI/Python3.12/native independent subagent/실측보정/전일100k는 미실행이다. 코어10개 byte identity, small actual-gap 실험과 시야 반례를 재사용한다. 기본 도시 routing 비용에 새 passage만 끼워 넣고 실제 수송은 옛 p에 남기는 비일관성을 피한다. 닫힌 단계마다 expected SHA로 연구 브랜치에 fast-forward 게시하며 main은 변경하지 않는다.
