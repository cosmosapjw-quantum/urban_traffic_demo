# Implementation Plan — 001 MetroFlow

## Survivors
- S2: WorldState contract + multirate scheduler
- S1: mesoscopic hybrid core

## Sequence
1. core/state.py
2. core/contracts.py
3. sim/scheduler.py
4. tests/test_contracts.py
5. bench/bench_replay.py
6. traffic/meso.py
7. traffic/routing.py
8. demand/accessibility.py
9. landuse/evolution.py
10. tests/test_meso_corridor.py
11. tests/test_landuse_feedback.py

## Core contracts
- state immutability
- time-scale separation
- cache versioning
- generalized cost definition
- event journal
