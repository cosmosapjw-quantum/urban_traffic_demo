# 지형·구역·수요·집계 교통 연구 실행

Branch: research/terrain-zones-demand-20261024. 코드와 각 단계 결과가 이 branch에 순차 게시된다. production default와 기존 active_meso.py/CTM/city generator는 변경하지 않는다.

## 저장소에서

```bash
PYTHONPATH=src python -m pytest -q tests/test_environment_*.py
PYTHONPATH=src python -S tools/run_environment_map.py artifacts/terrain_zones_run
PYTHONPATH=src python -S tools/run_environment_traffic.py artifacts/terrain_zones_run
PYTHONPATH=src python -S tools/audit_environment.py artifacts/terrain_zones_run
```

첫 명령26passed. 과학실행은 모두 표준라이브러리만 쓴다. pytest는 검사에만 필요하다. 그래픽은 없다. tools의 결과 폴더는 명시 경로를 쓰며 같은 이름의 결과를 재생성한다. 기존 source나 입력은 변경하지 않는다.

## 독립 번들에서
`code/`로 이동한 뒤 위 명령을 실행한다. `PYTHONPATH=src python -m pytest -q tests`는 부모 대조12개까지 포함해38passed다. standalone `src/metroflow/__init__.py`는 import용 작은 파일이며 원격repo initializer를 덮어쓰지 않는다. GitHub branch의전체기존test는 이번38개에 포함되지 않는다.

## 경계
100000주민 stock과40000jobs를 만들지만 full-day traffic은 실행하지 않는다. 100k short probe는300s이며 전체mean=null이다. 3k주민smallcase에서는1800s 안에 선언한 interzonal road demand가clear된다. Local trips/noncar/아직未방출 수요를 완료량으로 부르지 않는다. Persistent urban economy/parcel/hydrology/실측보정/게임비교는 미구현이다.

`MAP_KO.md`, `TRAFFIC_KO.md`, `AUDIT_AND_NEXT_KO.md`에 단위·근사·증거·다음DAG가 있다. `STAGE1/2/3.json`, 최종receipt와manifest는 source와실행을 묶는다. 전체원격repo CI와local실행은 다음담당자가 별도확인한다.
