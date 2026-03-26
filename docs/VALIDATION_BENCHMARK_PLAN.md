# Validation and Benchmark Plan

## invariant tests
- queue >= 0
- stock >= 0
- capacity respect
- deterministic replay
- cache version consistency
- no same-tick feedback closure

## toy gold suite
1. monocentric city
2. bridge bottleneck
3. merge bottleneck
4. bypass addition
5. incident shock
6. lagged land-use

## integration benchmark
city100k-like synthetic benchmark:
- zone 64
- active trips peak 10k~30k
- ring/radial + bridge + industrial corridor

측정:
- step latency
- memory footprint
- mean generalized cost
- top bottleneck persistence
- cache refresh cost
- viewer overhead
