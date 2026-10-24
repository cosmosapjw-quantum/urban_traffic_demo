# 지상 접근로와 interval-flow 연구: 지도 단계

Base e093ecd35e0af1bc940d3fa36ae09bd0a4a3978a와 첨부 archive SHA256 2b62fcf55c87e70849cbad99ae4fac9ab0dce3826f9d72225649562223557715를 확인했다. 기존4형태/고가/교량/active_suffix를 보존한다. 현재 실행 요청에 따라 map 이론/코딩 뒤 traffic 이론/코딩을 수행한다. native_subagent NOT_RUN; 직렬 실행/CAS/반례 검증이며 독립 모델 심사가 아니다.

지도 대안은 전체형태 재생성,메타데이터만의0비용frontage,실제지상도로 건설이었다. 마지막을 선택한다. 지형과 계층도로를 함께 컴파일하는 관점은 Galin et al.2011 doi10.1111/j.1467-8659.2011.02055.x에서 동기를 얻었지만 원 알고리즘 재현이 아니다.

선언한 활동지점에 대해 기존 local/collector surface road의 중간점으로 수직투영해 후보를 만든다. 물/보호/경사/다른도로접촉을 통과한 후보만 사용한다. 고속도로/램프/교량에는 frontage를 만들지 않는다. 기존도로를 분할하고 새 local spur를 추가하면 deltaE=deltaV=2이고 cycle rank는 보존된다. 부모의 true-terrain 적분길이 분할비를 구한 뒤 부모length를 보존하도록 비례정규화한다. 기존map은불변이다. 새 도로길이만 예산에 포함하며 weight/length의 greedy 선택은 전역최적이나 교통개선 보장이 아니다.

실제 생성에서 ring site가0.48794m connector를 만드는 반례를 발견했다. 15m 미만은 already_fronting으로 분류하고 새 도로나 완료된 교통으로 세지 않는다. 기존junction20m이내에는 junction을 재사용해2m부모조각을 막는다. 이 길이값은 연구설정이며 설계기준의 실측보정이 아니다. 이 두반례를 RED로 재현한 후 동일시험을 통과시켰다.

새시험7개 통과. 네형태 seed17에서각각4개실제접근로. 추가길이는 grid800.003655m,organic361.433371m,superblock800.003655m,ring186.813959m이며 900m예산 이내다. 비접속중심선 불법교차0,cycle rank불변,추가총길이장부잔차<1e-7m. 두최종그림을 직접 읽었으며 기존 반복격자·빈원형중심 등은 남는다. 주거stock을 바꾸거나 전체 구역접근/내부수요를 자동완료 처리하지 않는다. 이 단계는 물리접근로가 있는 실행graph를 만든 것이며 full service coverage가 아니다.

다음 traffic단계는 tick offset만수정,interval-rate calendar,fullLTM대체를 비교하고 두번째를 시험한다. Gain-loss활동도/합법turnDijkstra/committed suffix/노드allocation은 재사용한다. 동결rate의 정확한10초 freeflow,부분출발구간,신호경계,finite storage,폐쇄재개,질량보존과같은rate구간의무손실병합을 고정반례로 둔다. Signal/arrival/source event 경계로 구간을 나누고 기존코어를 대체하지않는 opt-in경로로 구현한다. 각단계expected_SHA게시;main변경없음. FullrepoCI,full-day100k,calibration,게임우월성은NOT_RUN.

실행: PYTHONPATH=src python -m pytest -q tests/test_frontage_growth.py; PYTHONPATH=src python -S tools/run_frontage_research.py. Python3.13.5. Stdlib scientific core,matplotlib그림만.
