# Research Notes — 001 MetroFlow

## Adopted conclusions
- shape-only map generation is insufficient
- pure shortest-path world is insufficient
- mesoscopic core is the right backbone
- lagged LUTI feedback is required
- CSUR contributes lane grammar + interface synthesis + node connector logic
- WorldState + multirate scheduler must come first

## Key risks
- stale cache
- time-scale mismatch
- same-tick positive feedback
- wrong realism expectation
- logging-driven false confidence
