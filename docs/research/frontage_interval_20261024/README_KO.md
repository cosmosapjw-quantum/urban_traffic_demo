# 재현

번들의 code/에서 실행한다. 원격 repo의 전체suite가 아니라 아래 집중scope를 뜻한다. 별도설치가필요한것은pytest(시험),matplotlib(그림)뿐이다.

```bash
# 샌드박스의45초호출한도때문에두묶음으로나눈다.
PYTHONPATH=src python -m pytest -q tests/test_environment_*.py tests/test_active_suffix.py tests/test_restored_traffic.py tests/test_interval_traffic.py tests/test_packed_traffic.py
PYTHONPATH=src python -m pytest -q tests/test_restored_map.py tests/test_frontage_growth.py tests/test_restored_visual.py
# 위79+23=102. 원격checkout에는parent-reference test_active_suffix.py가없다.
# 원격에서는첫명령에서그파일을제외하면67+23=90이다.

PYTHONPATH=src python -S tools/run_frontage_research.py
PYTHONPATH=src python -S tools/run_access_transport.py
PYTHONPATH=src python -S tools/run_packed_research.py
# 실제입력고정도시실험. 번들에는부모의입력JSON이있다.
PYTHONPATH=src python -S tools/run_packed_research.py --input artifacts/restored_layers_20261024/resume/input_grid_core_baseline_300s.json --dt 2 --horizon 300
PYTHONPATH=src python -S tools/check_packed_compression.py artifacts/restored_layers_20261024/resume/input_grid_core_baseline_300s.json artifacts/frontage_interval_20261024/packed/compression_ablation.json
python tools/plot_frontage_interval.py
```

원격checkout에서입력JSON이없으면부모실행기로재생성한다:
`PYTHONPATH=src python -S tools/run_restored_research.py --part traffic --style grid_core --horizon 300`.

Interval reference의도시400substepstop재현:
`PYTHONPATH=src python -S tools/run_interval_research.py --part city --input artifacts/restored_layers_20261024/resume/input_grid_core_baseline_300s.json --horizon 150 --max-steps 400 --wall-limit 20 --out artifacts/interval_stress`.
이는성공적인150초완료명령이아니라계산예산중단을기록한다.

그래프입력·물리계수·수요와신호를고정해비교한다. 신규접근로두site의희박운송은전체구역수요실험이아니다. 모든code는연구용이며기본Model을대체하지않는다. REPORT/HANDOFF와실제JSON에수치오차·실패·sourceidentity가있다.
