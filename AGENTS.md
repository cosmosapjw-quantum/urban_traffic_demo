# AGENTS.md

## 최상위 규칙
- S2 before S1
- external-data learning 금지
- baseline fallback 필수
- immutable WorldState
- explicit units
- multirate scheduler
- cache invalidation rule 문서화
- deterministic replay 필수

## 지금 하지 말 것
- lane-level microscopic default
- RL/LLM-first route brain
- ECS/plugin-first architecture
- distributed multi-GPU
- full generic frameworkization

## 구현 순서
1. core/state.py
2. core/contracts.py
3. sim/scheduler.py
4. traffic/meso.py
5. traffic/routing.py
6. demand/accessibility.py
7. landuse/evolution.py
8. policy/bandit.py
9. map/lane_grammar.py
10. map/node_compiler.py

## 필수 체크
- contract 영향?
- time-scale 영향?
- cache invalidation 영향?
- replay/regression 영향?
- benchmark 영향?

## Active Technologies
- Python 3.11 + Python stdlib dataclasses + pytest; repository deps include `jax` and `jaxlib` but this feature stays in the pure baseline path (002-fast-edge-evolution)
- Python 3.11 baseline with repository-local execution via `.venv` + Python stdlib dataclasses + pytest (004-multirate-orchestration)

## Recent Changes
- 002-fast-edge-evolution: Added Python 3.11 + Python stdlib dataclasses + pytest; repository deps include `jax` and `jaxlib` but this feature stays in the pure baseline path
