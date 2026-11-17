# V03 서비스 접근법칙의 정확한 재사용

2026-11-16, 기준 커밋 `b41f807c490dda12e036bcb40d9c13370f04223e`.

`compile_service_plan`은 같은 origin/destination 활동측도를 사용하는 각 버스
leg마다 `activity_access`를 다시 계산했다. 서로 다른 100개 cohort가 같은 두
측도를 참조하는 회귀 입력에서 실제 기하 계산은 200회였다. 계산 횟수를 2회로
제한하면서 100개 passenger ID와 2,500 person 및 원래 birth moment를 유지하는
테스트가 수정 전 `200 != 2`로 실패했고, 수정 후 통과했다.

변경은 한 번의 서비스 계획 컴파일에 수명이 한정된 256-entry LRU 접근법칙
캐시다. 키는 전체 불변 `ActivityMeasure`이며 block ID만 사용하지 않는다.
활동량·patch geometry·prior가 다른 측도는 분리된다. 출입구 registry와 depth는
호출 안에서 고정되어 있고, 새 호출은 빈 캐시에서 시작한다. eviction은 같은
입력의 재계산만 일으키며 반환값을 변경하지 않는다. 경로 질의 계측 wrapper는
기존 경로 캐시 바깥에 있어 cache hit를 포함한 실제 질의 시간을 측정한다.

수요·정원·운행계획·미배정 장부는 유지했다. 동일 block의 문에서 14 m 떨어진
활동측도는 1.4 m/s 접근에 10 s가 필요하므로, 문 위의 측도가 탈 수 있는 t=3 s
버스를 놓친다. 이 경우 두 측도의 50 person 중 25 person만 배정되고 나머지
25 person은 pending으로 남는 회귀 테스트가 통과했다. 257개 origin을 순회한 뒤
첫 origin을 다시 요청하는 사례에서는 256-entry 한도를 넘은 값의 실제 재계산과
동일 접근법칙을 확인했다.

Python 3.12와 3.13에서 서비스 관련 8개 테스트가 각각 통과했다. 메모이제이션만
해제한 경로와 전체 `ReleaseServicePlan`이 정확히 같고, 같은 계획으로 180 s를
실행한 물리 상태·identity·report가 정확히 같음을 검사했다. Ruff도 통과했다.

`artifacts/v1_v03_service_cost_20261116/benchmark.py`는 기준 커밋의 원래
`compile_service_plan` 함수와 현재 함수를 번갈아 먼저 실행한다. 작은 두 블록
도시의 균일 면적측도 두 개, 1,000개 서로 다른 bus leg를 사용한 5회 paired
실행에서 모든 전체 계획이 정확히 같았다. 평균 준비 wall time은
4.675069769 s에서 0.013178541 s로 감소했다. 원자료·환경·두 소스 SHA256은
동일 디렉터리의 `RESULT.json`에 있다. 이는 반복되는 두 측도가 cache에 모두
들어가는 한정 입력의 측정이며, 실제 도시의 cache hit율·RSS·24h 성능을
추정하는 값으로 사용하지 않는다.

전체 calendar materialization 한도는 그대로다. V03의 100k 주민 실제 로컬
캠페인은 이 수정의 완료 조건과 구분하며, 전체 노드 진행률은 19/21(90.5%)를
유지한다.
