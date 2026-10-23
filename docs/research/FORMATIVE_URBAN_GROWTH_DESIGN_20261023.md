# Formative Urban Growth, pure-Python research lane

**Status:** RESEARCH-READY, NOT DEFAULT-READY  
**Base authority:** `main@01c80b432344f94209daaa198bb1eb007839fc7f`  
**Date:** 2026-10-23  
**Scientific kernel:** Python standard library only, no JAX, CUDA, GPU, NumPy, GIS or graph package

## 1. Objective and scope

This branch adds an opt-in street-network morphogenesis experiment. It does not replace `standard`, `realistic_synthetic_v1`, or `scalable_synthetic_v2`. The target is a deterministic, replay-stable generator whose geometry records a formation history rather than drawing only a finished morphology grammar.

The accepted scientific scope is structural plausibility: causal growth, a connected planar graph, progressive loop closure, an old-core-to-fringe age gradient, locally coherent but globally diverse street orientations, bounded faces, and a connected road hierarchy. Empirical realism, historical reconstruction, traffic-functional validity, parcel economics, terrain, water, demolition, grade separation and production-scale speed are explicitly unclaimed.

## 2. Reused theory and model choice

The design reuses five literature-supported mechanisms:

1. local connection efficiency and loop creation rather than one global citywide optimum [1];
2. alternating exploration of the urban front and densification around existing centres [2];
3. competition among centres and morphology changes between mono- and polycentric regimes [3];
4. growth and coalescence of settlements with persistent major roads [4]–[6];
5. a sparse high-centrality backbone followed by edge additions [7].

Three candidates were compared. A continuous field-first model gives smooth terrain coupling but weak chronology. A global energy minimizer loses path dependence and makes results depend strongly on an authored Hamiltonian. The adopted epoch model keeps each constructive mechanism visible and testable in pure Python.

## 3. Mathematical construction

For epochs `e=0,...,T-1`, exploration probability decreases linearly,

`p_explore(e)=p0+(p1-p0)e/(T-1)`, with `p1<p0`.

New nodes sample one of three modes: outward exploration, local densification, or a centre-to-centre corridor. Mature districts use partial local-axis snapping, while the oldest core mixes radial and tangential directions only inside a bounded radius. This creates local order without forcing one global grid orientation.

Epoch zero is connected by an orientation-aware planar spanning tree. Every later node `i` first chooses exactly one already active parent `j<i` by minimizing

`C_ij = l_ij [1 + 2.20(1-a_ij)] / [(1+0.055 sqrt(k_j))(1+0.035(b_i-b_j))]`,

where `l_ij` is Euclidean length, `a_ij` is alignment with the local district axes, `k_j` is current degree and `b_i-b_j` is the age gap. Future nodes therefore cannot revise past parent choices.

After causal attachment, a bounded set of loop candidates is admitted only when it satisfies a Gabriel empty-disc condition, maximum length, maturity, local density, orientation alignment, detour reduction and non-crossing tests. The target edge count is

`E_target=max(N-1, round(k_target N/2))`.

For a connected graph the cycle rank is `μ=E-N+1`. For a connected planar embedding Euler's relation gives the same number of bounded faces, up to filtered degenerate faces. Exact faces are recovered by a half-edge successor rule.

Primary roads are not simply the highest edge-load quantile. They are the union of oriented shortest paths from the old core to secondary centres and four gateways, so the primary class is connected by construction. Remaining load-bearing edges are secondary; the rest are local.

## 4. Code architecture

- `formative_growth_model.py`: immutable config, centre, node, edge, block and map records; semantic fingerprint.
- `formative_growth_sampling.py`: centre births, epoch allocation, exploration/densification/corridor sampling.
- `formative_growth_network.py`: causal parent attachment, Gabriel loops, crossing tests and bounded repairs.
- `formative_growth_hierarchy.py`: path/load calculations and connected primary/secondary classification.
- `formative_growth_analysis.py`: half-edge faces, land-use heuristic, metrics and fail-closed structural audit.
- `formative_growth.py`: public facade and end-to-end orchestration.
- `run_formative_growth_research.py`: strict JSON, SVG and optional matplotlib PNG output.
- `validate_formative_growth_research.py`: nine-case seed/scale validation matrix.

The public entry point is:

```python
from metroflow.city.formative_growth import FormationConfig, generate_formative_city
city = generate_formative_city(FormationConfig(seed=20261023))
```

## 5. Three adversarial visual repair rounds

**Round 1:** a large 64 km² prototype was too sparse, with long isolated-looking branches and ten primary components. Repair: shrink the research area, increase node count, and require chronological attachment.

**Round 2:** causal growth was connected but visually resembled a spider web and retained too many dangling stubs. Repair: partial district-grid snapping, bounded cul-de-sac closure, and a connected hierarchy path union.

**Round 3:** global orientation entropy was incorrectly interpreted as local disorder, and hierarchy routes zigzagged. Repair: add district-local orientation coherence and orientation-aware hierarchy costs. The final map can have high pooled orientation entropy and high local order simultaneously [8].

The detailed findings, observed defects, effects and minimal repairs are in `ADVERSARIAL_VISUAL_AUDIT.md`.

## 6. Fresh verification evidence

Focused commands:

```bash
PYTHONPATH=src python -m pytest -q tests/test_formative_growth.py
PYTHONPATH=src python tools/run_formative_growth_research.py \
  --output-dir artifacts/formative_growth_run --seed 20261023 \
  --node-count 320 --area-km2 25
PYTHONPATH=src python tools/validate_formative_growth_research.py \
  --output artifacts/formative_growth_multiseed.json
```

Fresh isolated result on Python 3.13.5:

- `compileall`: PASS;
- focused tests: 5 passed;
- final fingerprint: `9469afef2b40fcd3389bbc00499008747300116498ed55baf13772f5667c0ff3`;
- final audit: PASS, 0 errors, 0 warnings;
- final graph: 320 nodes, 512 edges, mean degree 3.20, cycle rank 193, 190 accepted blocks;
- dead-end share 0.06875, road density 5.684 km/km²;
- global orientation entropy 0.9944, local coherence 0.9245;
- crossings 0, graph components 1, primary components 1;
- nine seed/scale cases: all PASS; fresh maximum observed wall time 4.486 s;
- accelerator scan: no JAX/CUDA/CuPy/Torch/GPU reference in changed executable surfaces.

The repository targets Python 3.12; the isolated execution environment available for this research run was Python 3.13.5. Full repository CI is separate from this focused evidence.

## 7. Claim gate and remaining work

**Admitted:** deterministic replay, semantic identity, causal parent attachment, connected planarity for tested cases, progressive mesh formation, exact bounded-face traversal, connected primary hierarchy, strict JSON/SVG artifacts.

**Not admitted:** empirical urban realism, predictive validity, calibrated land-use or traffic behavior, historical city reconstruction, production-scale performance.

Before default/runtime promotion, the minimum next sequence is: add terrain/water and surface/grade-separated layers; define an evidence-based pruning operator; test scale convergence; compare held-out real-city distributions with a predeclared metric/tolerance contract; then run full repository tests and CI on Python 3.12.

## References

Citation metadata are stored in `FORMATIVE_URBAN_GROWTH_REFERENCES_20261023.bib`. Key sources are Barthélemy and Flammini [1], Strano et al. [2], Rui et al. [3], Beneš et al. [4], Al Sayed et al. [6], Barthélemy and Boeing [7], Boeing [8], Kruskal [9], and Guibas and Stolfi [10].
