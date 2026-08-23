# MetroFlow Morphology Failure Inventory

Scope: all morphology/evidence failures supplied in the audit sequence, the current seed-held-out result, the prior bounded traffic-functional attempt, and directly relevant canonical ledgers reviewed through 2026-08-23.

This is a failure-preservation ledger, not a statement that every item is still open. CLOSED means the identified path was directly repaired. NEGATIVE_RESULT means an unfavorable experiment is retained without repair or reinterpretation.

| State | Count |
| --- | ---: |
| CLOSED | 15 |
| PARTIALLY_CLOSED | 1 |
| OPEN | 12 |
| NEGATIVE_RESULT | 4 |
| NOT_EVALUATED | 3 |
| CONTESTED | 1 |

## Complete inventory

### MF-001 - Legacy gallery used the wrong generator/provenance label

- Domain: evidence identity
- First observed: 2026-08-20 audit of main 77060e1
- Original severity: P1
- Current state: **CLOSED**
- Impact: A visually plausible image could be attributed to a generator that did not produce it.
- Evidence: Initial external audit supplied by the user; current scalable gallery manifest and renderer provenance checks.
- Resolution/current handling: The scalable gallery now declares topology mode, schemas, source fingerprints, counts, and file digests per style.
- Remaining gate: Preserve exact provenance checks whenever a gallery schema changes.
- Claim effect: Current six-map sample identity is admissible; legacy gallery claims remain historical only.

### MF-002 - Gallery accepted score and geometry with a plus/minus ten-node mismatch

- Domain: evidence identity
- First observed: 2026-08-20 audit of main 77060e1
- Original severity: P1
- Current state: **CLOSED**
- Impact: Historical scores could be displayed beside a different topology.
- Evidence: Initial audit and PR #17 source-topology fingerprint regression tests.
- Resolution/current handling: Exact node equality and SHA-256 source-topology fingerprint equality are now required before rendering.
- Remaining gate: Retain exact binding in all future renderers and artifact migrations.
- Claim effect: The former score-to-shape false-pass path is closed for current artifacts.

### MF-003 - CI dependencies and tool versions were not frozen

- Domain: reproducibility
- First observed: 2026-08-20 audit of main 77060e1
- Original severity: P1
- Current state: **PARTIALLY_CLOSED**
- Impact: A frozen candidate could resolve a different Python dependency environment on each run.
- Evidence: PR #17 workflow and ci-constraints.txt; exact-head runs 32564391135 and 32564393072.
- Resolution/current handling: Ubuntu version, Python 3.12.14, action commit SHAs, and exact Python package versions are pinned.
- Remaining gate: Wheel hashes and a runner-image digest remain outside the current closure.
- Claim effect: Resolver/toolchain reproducibility is supported, but whole-image bit hermeticity is not.

### MF-004 - GitHub-hosted runner and wheels are not bit-hermetic

- Domain: reproducibility
- First observed: 2026-08-22 adversarial review of c9985ce
- Original severity: P2
- Current state: **OPEN**
- Impact: The Ubuntu 24.04 hosted image and downloaded wheels may change beneath version constraints.
- Evidence: GitHub Actions workflow uses ubuntu-24.04 and ci-constraints.txt without image or wheel hashes.
- Resolution/current handling: No change was made in this report-only work unit.
- Remaining gate: Record runner image identity or adopt a digest-pinned container and require-hashes if bit reproduction becomes a release requirement.
- Claim effect: CI evidence is exact-head functional evidence, not a bit-hermetic build claim.

### MF-005 - Node-to-TAZ assignment allowed float-to-millimetre reconstruction

- Domain: geometry contract
- First observed: 2026-08-20 audit of main 77060e1
- Original severity: P2
- Current state: **CLOSED**
- Impact: Sub-metre coordinates or coercion could change deterministic ownership.
- Evidence: PR #17 exact-mm ownership implementation and regression coverage.
- Resolution/current handling: Built-in integer x_mm/y_mm pairs are now the single authority and squared integer distance is used.
- Remaining gate: Keep coordinate-unit validation at public boundaries.
- Claim effect: The current Node-to-TAZ internal exact-mm contract is closed.

### MF-006 - Project-state documentation was stale

- Domain: governance
- First observed: 2026-08-20 audit of main 77060e1
- Original severity: P3
- Current state: **CLOSED**
- Impact: Reviewers could mistake an older candidate receipt for current state.
- Evidence: Updated morphology closure ledgers and PR #17 receipt separation.
- Resolution/current handling: The active claim ledger was updated and remote receipts are kept separate from self-referential commits.
- Remaining gate: Continue labelling every receipt with its exact commit/tree.
- Claim effect: Current report does not inherit a predecessor receipt without an explicit identity link.

### MF-007 - Ring-radial style was a grid with a central cross

- Domain: morphology grammar
- First observed: 2026-08-20 audit of main 77060e1
- Original severity: P1
- Current state: **CLOSED**
- Impact: The label claimed ring-radial structure without closed orbital rings.
- Evidence: PR #17 nested orbital implementation and winding/radial-CV tests; held-out cases 503, 701, 907.
- Resolution/current handling: The generator now emits closed concentric cycles, radial spokes, and a peripheral mainline.
- Remaining gate: Calibrate ring segmentation and compare against independent empirical distributions before realism claims.
- Claim effect: Structural ring-radial differentiation is validated; empirical realism is not.

### MF-008 - Polycentric centres were collinear

- Domain: morphology grammar
- First observed: 2026-08-20 audit of main 77060e1
- Original severity: P1
- Current state: **CLOSED**
- Impact: A one-dimensional chain was presented as a two-dimensional polycentric layout.
- Evidence: PR #17 non-collinearity, catchment, and hierarchy-path tests; held-out cases 503, 701, 907.
- Resolution/current handling: Three non-collinear centres, nonempty geometric catchments, and centre-pair hierarchy paths are now required.
- Remaining gate: Validate independent activity basins and transit/service concentration separately.
- Claim effect: Geometric polycentricity is validated, not functional TOD behaviour.

### MF-009 - Polycentric functional independence and transit concentration are untested

- Domain: traffic-function science
- First observed: 2026-08-20 audit of 2d99f80
- Original severity: P1 scientific
- Current state: **NOT_EVALUATED**
- Impact: Geometric centres can exist without distinct accessibility basins or TOD-like transport function.
- Evidence: No completed functional-centre or transit-service experiment is present in this evidence package.
- Resolution/current handling: No claim was promoted; the limitation is explicit.
- Remaining gate: Run preregistered centre-level demand, accessibility, transit concentration, and route substitution tests.
- Claim effect: Functional polycentricity remains NOT_EVALUATED.

### MF-010 - Superblock implementation produced one-axis elongated strips

- Domain: morphology grammar
- First observed: 2026-08-20 audit of 2d99f80
- Original severity: P1
- Current state: **CLOSED**
- Impact: A large-area outlier could pass while remaining a thin strip rather than a two-dimensional macroblock.
- Evidence: PR #17 two-axis removal, aspect-ratio, minimum-axis, count, and hierarchy-perimeter tests; held-out cases.
- Resolution/current handling: Current grammar requires multiple bounded two-dimensional macrocells with hierarchy-qualified perimeters.
- Remaining gate: Retain the two-axis structural tests and evaluate internal access separately.
- Claim effect: The structural macroblock claim is closed within the current deterministic grammar.

### MF-011 - Superblock access, circulation, and mode function are unvalidated

- Domain: traffic-function science
- First observed: 2026-08-20 audit of 2d99f80
- Original severity: P1 scientific
- Current state: **NOT_EVALUATED**
- Impact: Removing motorized carriers can create a geometric macroblock without usable internal circulation or access.
- Evidence: No completed motorized-access, pedestrian-layer, travel-time, or circulation experiment is in scope.
- Resolution/current handling: No functional superblock claim was made.
- Remaining gate: Define typed internal access and test mode-specific reachability and performance.
- Claim effect: Functional superblock validity remains NOT_EVALUATED.

### MF-012 - Organic topology claim exceeded a warped-grid implementation

- Domain: claim accuracy
- First observed: 2026-08-20 audit of 2d99f80
- Original severity: P1
- Current state: **CLOSED**
- Impact: Smooth displacement changed embedding but not branching, dead ends, degree structure, or accretion grammar.
- Evidence: Current public label is 'Curvilinear Warped Grid (organic compatibility ID)' and held-out bent-connector checks.
- Resolution/current handling: The claim was narrowed to deterministic curvilinear embedding while retaining the compatibility identifier.
- Remaining gate: A future organic-topology claim needs branching, angle, degree, dead-end, and block-shape tests.
- Claim effect: Curvilinear geometry is validated; organic street-network topology is not claimed.

### MF-013 - Morphology semantic tests used weak proxy statistics

- Domain: test validity
- First observed: 2026-08-20 audit of 2d99f80
- Original severity: P1
- Current state: **CLOSED**
- Impact: Orientation entropy or coordinate inequality could pass networks lacking the named structure.
- Evidence: PR #17 structural falsifiers for cycles, winding, catchments, hierarchy paths, macroblocks, and curvilinear connectors.
- Resolution/current handling: Proxy-only assertions were replaced or bounded by direct structural witnesses.
- Remaining gate: Future morphology claims require claim-specific falsifiers, not reuse of unrelated summary metrics.
- Claim effect: The six current structural labels have direct tests at their stated claim level.

### MF-014 - The v4 control table does not score scalable_synthetic_v2

- Domain: scientific evidence
- First observed: 2026-08-20 audit of 2d99f80
- Original severity: P1 scientific
- Current state: **OPEN**
- Impact: A valid historical/sidecar table cannot establish empirical validity for the newly changed scalable generator.
- Evidence: morphology-control-table-v4 arm inventory and its explicit diagnostic-only claim boundary.
- Resolution/current handling: No silent inference is made from v4 to scalable_synthetic_v2.
- Remaining gate: Build a preregistered held-out OSM morphology table whose treatment arm is scalable_synthetic_v2.
- Claim effect: The present 15/18 seed result is structural only and not empirical control-table validation.

### MF-015 - Full v4 artifact and manifest were not rederived in CI

- Domain: reproducibility
- First observed: 2026-08-20 audit of 2d99f80
- Original severity: P1
- Current state: **CLOSED**
- Impact: Selected gallery checks could pass while the 135-score table or manifest fields drifted.
- Evidence: PR #17 audit-gallery job in runs 32564391135 and 32564393072.
- Resolution/current handling: CI now rederives the full v4 JSON/Markdown and verifies schema, table fingerprint, file hashes, and bytes.
- Remaining gate: Keep the full matrix command explicit and exact in CI.
- Claim effect: Same-head v4 artifact reproducibility is closed for the PR #17 tree.

### MF-016 - Score identity omitted or made optional source/spec fields

- Domain: scientific identity
- First observed: 2026-08-20 audit of 2d99f80
- Original severity: P2
- Current state: **CLOSED**
- Impact: Equal metric values could hide different source topology or measurement definitions.
- Evidence: Current v4 score payload and constructor tests.
- Resolution/current handling: source_topology_fingerprint and measurement_spec are mandatory for current-schema scores and fingerprinted.
- Remaining gate: Reject unknown schemas as tracked separately in MF-022.
- Claim effect: Current v4 score identity binds both source topology and measurement specification.

### MF-017 - PNG previews are digest-bound but not source-rerendered

- Domain: visual evidence
- First observed: 2026-08-20 audit of 2d99f80
- Original severity: P2
- Current state: **OPEN**
- Impact: A committed PNG can match its recorded digest without proving that a current renderer reproduced it.
- Evidence: Scalable gallery checker and README distinguish SVG authority from PNG preview.
- Resolution/current handling: Success wording now states SVG rederivation and PNG digest comparison separately.
- Remaining gate: Rerender PNGs in a pinned raster stack if preview-byte reproduction becomes an acceptance requirement.
- Claim effect: PNG maps in this package are navigational previews; SVG/source fingerprints carry scientific identity.

### MF-018 - Exact branch-head external CI was initially unavailable

- Domain: remote verification
- First observed: 2026-08-20 audit of 2d99f80
- Original severity: P1
- Current state: **CLOSED**
- Impact: Local evidence alone could not establish that the proposed merge tree passed protected CI.
- Evidence: PR #17 push run 32564391135 and pull-request run 32564393072; both ci gate jobs succeeded.
- Resolution/current handling: Exact head 6d6e056 and synthetic merge were tested and shared tree 622dbe3779; PR #17 merged as e1979df.
- Remaining gate: Obtain new exact-head evidence for any future source change.
- Claim effect: PR #17 remote implementation evidence is closed; it does not validate this later report branch remotely.

### MF-019 - Duplicate score keys could inflate summaries and overwrite diagnostics

- Domain: artifact schema
- First observed: 2026-08-22 audit of c9985ce
- Original severity: P1
- Current state: **CLOSED**
- Impact: Two records with one (arm, case) identity could count twice in summaries but collapse in dictionaries.
- Evidence: Current MorphologyControlTable constructor and renderer duplicate-key regression tests.
- Resolution/current handling: Both the table and renderer reject duplicate (arm, case) keys before aggregation.
- Remaining gate: Retain uniqueness as a schema invariant.
- Claim effect: The duplicate-key evidence-normalization path is closed.

### MF-020 - Catch-all exceptions could be normalized as skipped cases

- Domain: artifact collection
- First observed: 2026-08-22 audit of c9985ce
- Original severity: P1
- Current state: **CLOSED**
- Impact: Programming or schema failures could be committed as apparently legitimate missing data.
- Evidence: Current typed SkippedCase collection and exact 135 score plus 22 skip partition tests.
- Resolution/current handling: Unsupported standard styles are classified before generation; only UnsupportedOSMTagError is converted; all other exceptions abort.
- Remaining gate: Keep exact score/skip/attempt partition equality and typed exceptions.
- Claim effect: Unexpected program failures can no longer silently become normal skips in this collector.

### MF-021 - Validation ledger contradicted live remote verification

- Domain: governance
- First observed: 2026-08-22 audit of c9985ce
- Original severity: P1 governance
- Current state: **CLOSED**
- Impact: The canonical ledger said no push or PR existed after exact-head CI had succeeded.
- Evidence: Updated validation ledger plus PR #17 remote receipt in this package.
- Resolution/current handling: The predecessor receipt and later review-fix receipt are explicitly separated by commit identity.
- Remaining gate: Keep live external receipts outside self-referential commit content and bind them by SHA/tree.
- Claim effect: The PR #17 ledger contradiction is closed.

### MF-022 - Unknown control-table schema names bypass current identity guards

- Domain: artifact schema
- First observed: 2026-08-22 audit of c9985ce
- Original severity: P2
- Current state: **OPEN**
- Impact: A typo schema string can avoid v4 source/spec requirements because enforcement is equality-gated.
- Evidence: src/metroflow/city/morphology_control_table.py current-schema conditional.
- Resolution/current handling: No source change was authorized in this report work unit.
- Remaining gate: Reject schemas outside an explicit supported-version set or split legacy readers from the current writer.
- Claim effect: Unknown-schema inputs are not covered by the v4 identity claim.

### MF-023 - Standard supported-style capability has a duplicated source of truth

- Domain: maintainability
- First observed: 2026-08-22 audit of 6d6e056
- Original severity: P2
- Current state: **OPEN**
- Impact: The benchmark can keep skipping a style after the standard generator gains support.
- Evidence: STANDARD_SUPPORTED_STYLES in the control-table benchmark versus generator capability.
- Resolution/current handling: No source change was authorized in this report work unit.
- Remaining gate: Export a generator capability registry or assert equality in a focused invariant test.
- Claim effect: The current matrix is correct, but future capability drift remains possible.

### MF-024 - SkippedCase reason_code remains a free string

- Domain: artifact schema
- First observed: 2026-08-22 audit of 6d6e056
- Original severity: P2
- Current state: **OPEN**
- Impact: A new typo or undeclared reason can enter code even though the committed artifact is exact-tested.
- Evidence: SkippedCase declaration and current artifact reason distribution.
- Resolution/current handling: Current production paths emit exactly three reviewed codes and artifact bytes pin their distribution.
- Remaining gate: Use a SkipReason enum or enforce an allowlist at construction.
- Claim effect: Current receipts are trustworthy; the type-level future extension boundary remains open.

### MF-025 - Validation ledger local test count labels a predecessor head

- Domain: governance
- First observed: 2026-08-22 audit of 6d6e056
- Original severity: P2
- Current state: **OPEN**
- Impact: Readers can misread 1,473 passed as the latest head result rather than the predecessor candidate.
- Evidence: VALIDATION_LEDGER.md predecessor receipt and PR #17 review summary reporting 1,483 passed.
- Resolution/current handling: Commit identity makes the older number technically scoped, but the prose has not been relabelled in this work unit.
- Remaining gate: Label initial-candidate and review-fix local results on separate lines.
- Claim effect: Do not use the 1,473 count as a current-tree full-suite receipt.

### MF-026 - Seven-metric envelope admits a morphology null operator

- Domain: scientific validity
- First observed: 2026-08-09 G0 map-evidence recovery
- Original severity: P1 scientific
- Current state: **OPEN**
- Impact: A sidecar local-fabric control can pass all seven empirical metrics while remaining visibly non-city-like.
- Evidence: artifacts/external_audit_2_maps and morphology-control-table-v4 diagnostic results.
- Resolution/current handling: The result is disclosed as a falsifier of sufficiency; no realism promotion is made.
- Remaining gate: Add independently justified discriminators and held-out controls before empirical morphology claims.
- Claim effect: Passing the v4 metric envelope is not sufficient evidence of urban realism.

### MF-027 - orientation_order is vacuous in the current empirical envelope

- Domain: measurement validity
- First observed: 2026-08-07 plausibility audit repair
- Original severity: P2 scientific
- Current state: **OPEN**
- Impact: Near-universal coverage makes the metric unable to falsify treatment maps.
- Evidence: CLAIM_LEDGER.md and morphology-control-table-v4 diagnostics report 0.998 coverage.
- Resolution/current handling: The metric is reported rather than counted as silent passing evidence.
- Remaining gate: Recalibrate, replace, or preregister a non-vacuous threshold on independent data.
- Claim effect: orientation_order does not support a morphology-validity claim.

### MF-028 - Geometry/topology diagnostics are reported but not gated

- Domain: measurement validity
- First observed: 2026-08-20 audit of 2d99f80
- Original severity: P2 scientific
- Current state: **OPEN**
- Impact: Unregistered geometry touches and other diagnostics can coexist with a nominal table pass.
- Evidence: v4 diagnostics, including growth_fabric_v1 cases with up to 23 unregistered touches.
- Resolution/current handling: Diagnostics are disclosed and not misrepresented as acceptance gates.
- Remaining gate: Define justified thresholds and ownership semantics before gating them.
- Claim effect: Reported diagnostics cannot be treated as passed scientific criteria.

### MF-029 - realistic_synthetic_v1 passed zero of 30 morphology cases

- Domain: negative scientific result
- First observed: 2026-07 PR62 plausibility audit
- Original severity: P0 promotion blocker
- Current state: **NEGATIVE_RESULT**
- Impact: The proposed realistic generator was too highly connected and had too few dead ends across the fixed matrix.
- Evidence: artifacts/runtime_spine_review/realistic-city-pr62-plausibility and CLAIM_LEDGER.md.
- Resolution/current handling: The negative result was preserved and default promotion remained blocked.
- Remaining gate: A new generator revision needs a preregistered, independent empirical protocol; do not tune against this failed holdout.
- Claim effect: The PR62 empirical morphology promotion claim is rejected.

### MF-030 - realistic_synthetic_v1 failed 100k generation and throughput gates

- Domain: negative runtime result
- First observed: 2026-07 PR63 scale/product gate
- Original severity: P0 promotion blocker
- Current state: **NEGATIVE_RESULT**
- Impact: All three seeds missed generation wall, realized population, and paired throughput requirements.
- Evidence: PR63 canonical runtime artifacts summarized in CLAIM_LEDGER.md.
- Resolution/current handling: The negative result was preserved; standard remained the runtime default.
- Remaining gate: Rework and remeasure using a new versioned protocol rather than weakening the failed gate.
- Claim effect: Runtime-default promotion remains blocked.

### MF-031 - spacing_scale 3.0 was fitted to a repaired bug rather than rederived

- Domain: calibration debt
- First observed: 2026-08 external map audit
- Original severity: P2 scientific
- Current state: **OPEN**
- Impact: A parameter calibrated against defective measurements may encode the defect rather than urban morphology.
- Evidence: artifacts/external_audit_2_maps/README.md calibration caveat.
- Resolution/current handling: The parameter is disclosed as historical debt, not empirical validation.
- Remaining gate: Rederive it under a preregistered measurement specification and independent calibration set.
- Claim effect: No scientific inference may rely on spacing_scale 3.0 as a validated calibration.

### MF-032 - The control table lacks a block-size discriminator

- Domain: measurement gap
- First observed: 2026-08 external map audit
- Original severity: P2 scientific
- Current state: **OPEN**
- Impact: Networks with implausible block scale can satisfy the existing seven metrics.
- Evidence: artifacts/external_audit_2_maps/README.md and the null-operator result.
- Resolution/current handling: The missing dimension is disclosed; no surrogate metric is silently substituted.
- Remaining gate: Add a source-compatible block/face-size statistic with held-out calibration.
- Claim effect: The present empirical envelope is incomplete for block morphology.

### MF-033 - Held-out grid_core failed the axis-alignment contract in all three seeds

- Domain: negative held-out result
- First observed: 2026-08-22 seed-held-out run
- Original severity: P1 scientific
- Current state: **NEGATIVE_RESULT**
- Impact: Only 1,724/3,167, 1,740/3,178, and 1,681/3,081 semantic carriers were counted as axis-aligned.
- Evidence: evidence/heldout_morphology_results.json cases grid_core seeds 503, 701, and 907.
- Resolution/current handling: The aggregate verdict is FAIL at 15/18; thresholds and results were not changed after observation.
- Remaining gate: Diagnose semantics versus geometry under a new preregistered protocol before modifying implementation or criterion.
- Claim effect: The grid_core held-out structural claim is a NEGATIVE_RESULT.

### MF-034 - Grid-core failure has unresolved construct-validity ambiguity

- Domain: scientific interpretation
- First observed: 2026-08-23 adversarial synthesis
- Original severity: P1 scientific
- Current state: **CONTESTED**
- Impact: The failed ratio may indicate genuinely warped grid carriers or an over-strict classifier that excludes intended connectors.
- Evidence: heldout validator source plus grid_core witness counts; no independent block-orientation measure was run.
- Resolution/current handling: The failure is preserved without selecting the favorable explanation.
- Remaining gate: Predeclare a diagnostic decomposition, inspect source semantics, and use an independent orientation/block witness on new seeds.
- Claim effect: Cause is CONTESTED; neither generator defect nor invalid test is established by this result alone.

### MF-035 - Held-out validation is seed-only, not fresh OSM or named-city validation

- Domain: scope limitation
- First observed: 2026-08-22 held-out protocol
- Original severity: P1 scientific
- Current state: **NOT_EVALUATED**
- Impact: Unseen pseudo-random seeds test replay and grammar generalization but not external urban realism.
- Evidence: Result protocol declares holdout_kind seed_heldout_structural_not_fresh_osm and fresh_osm_holdout_status NOT_EVALUATED.
- Resolution/current handling: The report names this limitation in every promotion decision.
- Remaining gate: Run a leakage-controlled fresh-OSM/named-region comparison with licensed frozen extracts and preregistered metrics.
- Claim effect: This is NOT fresh-OSM empirical validation.

### MF-036 - Traffic-functional development probe did not reach a valid result

- Domain: negative traffic result
- First observed: 2026-08-22 bounded traffic-functional attempt
- Original severity: P1 research blocker
- Current state: **NEGATIVE_RESULT**
- Impact: The only durable test cache records failure of the nonvacuous-and-directional probe; no complete matrix or durable result artifact exists.
- Evidence: /tmp/urban-traffic-heldout-functional-20260822 pytest lastfailed receipt and session record; no result JSON/Markdown was emitted.
- Resolution/current handling: The attempt is preserved as a NEGATIVE_RESULT and was not rerun, repaired, or normalized in this report work unit.
- Remaining gate: Design a new versioned functional protocol with nonvacuity, cache invalidation, conservation, deterministic replay, and baseline comparison before execution.
- Claim effect: Traffic-functional validation was not completed; traffic algorithms remain research-incomplete and no completeness claim is permitted.
