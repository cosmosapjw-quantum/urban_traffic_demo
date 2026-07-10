# Research Notes — 001 MetroFlow

## Adopted conclusions
- shape-only map generation is insufficient
- pure shortest-path world is insufficient
- mesoscopic core is the right backbone
- lagged LUTI feedback is required
- modular road-asset research motivates lane-section and interface contracts;
  Metroflow owns the implementation and node-connector logic
- WorldState + multirate scheduler must come first

## Key risks
- stale cache
- time-scale mismatch
- same-tick positive feedback
- wrong realism expectation
- logging-driven false confidence
