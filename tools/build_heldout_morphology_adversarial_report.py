#!/usr/bin/env python3
"""Build and verify the held-out morphology adversarial-audit package.

The package is deliberately report-only.  It consumes already-frozen evidence;
it does not regenerate maps, change a scientific threshold, or run traffic.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
import struct
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "artifacts" / "heldout_morphology_adversarial_audit_20260823"
EVIDENCE = PACKAGE / "evidence"
MAPS = PACKAGE / "maps"
PDF_NAME = "metroflow-heldout-morphology-adversarial-audit-20260823.pdf"
PDF_COPY = ROOT / "output" / "pdf" / PDF_NAME
SOURCE_COMMIT = "e1979df281ac25a24a82fdea725422310f7c6807"
SOURCE_TREE = "622dbe37790c5414141cd5d5531a2158aa56f7e5"
SCIENTIFIC_FINGERPRINT = (
    "84b2f3657b21c9cedd9fe7723b4edf99ac3f7514cf7128aff6c994ff9da253f1"
)
STYLE_ORDER = (
    "grid_core",
    "ring_radial",
    "river_constrained",
    "polycentric_tod",
    "superblock_mixed",
    "organic",
)
STYLE_LABELS = {
    "grid_core": "Grid Core",
    "ring_radial": "Ring-Radial",
    "river_constrained": "River-Constrained",
    "polycentric_tod": "Polycentric TOD",
    "superblock_mixed": "Superblock Mixed",
    "organic": "Curvilinear Warped Grid (organic compatibility ID)",
}
ROOT_FILES = {
    "AUDITOR_README.md",
    "CLAIM_EVIDENCE_LEDGER.md",
    "EVIDENCE_MANIFEST.json",
    "FAILURE_INVENTORY.json",
    "FAILURE_INVENTORY.md",
    "INDEPENDENT_REVIEW.md",
    "REPORT.md",
    PDF_NAME,
}
EVIDENCE_FILES = {
    "harness_receipt.json",
    "heldout_morphology_results.json",
    "heldout_morphology_validator.py",
    "pr17_remote_receipt.json",
    "sample_manifest.json",
    "source_receipt.json",
}


def _failure(
    identifier: str,
    title: str,
    domain: str,
    first_observed: str,
    original_severity: str,
    current_state: str,
    impact: str,
    evidence: str,
    resolution: str,
    remaining_gate: str,
    claim_effect: str,
) -> dict[str, str]:
    return {
        "id": identifier,
        "title": title,
        "domain": domain,
        "first_observed": first_observed,
        "original_severity": original_severity,
        "current_state": current_state,
        "impact": impact,
        "evidence": evidence,
        "resolution": resolution,
        "remaining_gate": remaining_gate,
        "claim_effect": claim_effect,
    }


def failure_inventory() -> list[dict[str, str]]:
    """Return the fixed, scoped history reviewed for this package."""
    return [
        _failure(
            "MF-001",
            "Legacy gallery used the wrong generator/provenance label",
            "evidence identity",
            "2026-08-20 audit of main 77060e1",
            "P1",
            "CLOSED",
            "A visually plausible image could be attributed to a generator that did not produce it.",
            "Initial external audit supplied by the user; current scalable gallery manifest and renderer provenance checks.",
            "The scalable gallery now declares topology mode, schemas, source fingerprints, counts, and file digests per style.",
            "Preserve exact provenance checks whenever a gallery schema changes.",
            "Current six-map sample identity is admissible; legacy gallery claims remain historical only.",
        ),
        _failure(
            "MF-002",
            "Gallery accepted score and geometry with a plus/minus ten-node mismatch",
            "evidence identity",
            "2026-08-20 audit of main 77060e1",
            "P1",
            "CLOSED",
            "Historical scores could be displayed beside a different topology.",
            "Initial audit and PR #17 source-topology fingerprint regression tests.",
            "Exact node equality and SHA-256 source-topology fingerprint equality are now required before rendering.",
            "Retain exact binding in all future renderers and artifact migrations.",
            "The former score-to-shape false-pass path is closed for current artifacts.",
        ),
        _failure(
            "MF-003",
            "CI dependencies and tool versions were not frozen",
            "reproducibility",
            "2026-08-20 audit of main 77060e1",
            "P1",
            "PARTIALLY_CLOSED",
            "A frozen candidate could resolve a different Python dependency environment on each run.",
            "PR #17 workflow and ci-constraints.txt; exact-head runs 32564391135 and 32564393072.",
            "Ubuntu version, Python 3.12.14, action commit SHAs, and exact Python package versions are pinned.",
            "Wheel hashes and a runner-image digest remain outside the current closure.",
            "Resolver/toolchain reproducibility is supported, but whole-image bit hermeticity is not.",
        ),
        _failure(
            "MF-004",
            "GitHub-hosted runner and wheels are not bit-hermetic",
            "reproducibility",
            "2026-08-22 adversarial review of c9985ce",
            "P2",
            "OPEN",
            "The Ubuntu 24.04 hosted image and downloaded wheels may change beneath version constraints.",
            "GitHub Actions workflow uses ubuntu-24.04 and ci-constraints.txt without image or wheel hashes.",
            "No change was made in this report-only work unit.",
            "Record runner image identity or adopt a digest-pinned container and require-hashes if bit reproduction becomes a release requirement.",
            "CI evidence is exact-head functional evidence, not a bit-hermetic build claim.",
        ),
        _failure(
            "MF-005",
            "Node-to-TAZ assignment allowed float-to-millimetre reconstruction",
            "geometry contract",
            "2026-08-20 audit of main 77060e1",
            "P2",
            "CLOSED",
            "Sub-metre coordinates or coercion could change deterministic ownership.",
            "PR #17 exact-mm ownership implementation and regression coverage.",
            "Built-in integer x_mm/y_mm pairs are now the single authority and squared integer distance is used.",
            "Keep coordinate-unit validation at public boundaries.",
            "The current Node-to-TAZ internal exact-mm contract is closed.",
        ),
        _failure(
            "MF-006",
            "Project-state documentation was stale",
            "governance",
            "2026-08-20 audit of main 77060e1",
            "P3",
            "CLOSED",
            "Reviewers could mistake an older candidate receipt for current state.",
            "Updated morphology closure ledgers and PR #17 receipt separation.",
            "The active claim ledger was updated and remote receipts are kept separate from self-referential commits.",
            "Continue labelling every receipt with its exact commit/tree.",
            "Current report does not inherit a predecessor receipt without an explicit identity link.",
        ),
        _failure(
            "MF-007",
            "Ring-radial style was a grid with a central cross",
            "morphology grammar",
            "2026-08-20 audit of main 77060e1",
            "P1",
            "CLOSED",
            "The label claimed ring-radial structure without closed orbital rings.",
            "PR #17 nested orbital implementation and winding/radial-CV tests; held-out cases 503, 701, 907.",
            "The generator now emits closed concentric cycles, radial spokes, and a peripheral mainline.",
            "Calibrate ring segmentation and compare against independent empirical distributions before realism claims.",
            "Structural ring-radial differentiation is validated; empirical realism is not.",
        ),
        _failure(
            "MF-008",
            "Polycentric centres were collinear",
            "morphology grammar",
            "2026-08-20 audit of main 77060e1",
            "P1",
            "CLOSED",
            "A one-dimensional chain was presented as a two-dimensional polycentric layout.",
            "PR #17 non-collinearity, catchment, and hierarchy-path tests; held-out cases 503, 701, 907.",
            "Three non-collinear centres, nonempty geometric catchments, and centre-pair hierarchy paths are now required.",
            "Validate independent activity basins and transit/service concentration separately.",
            "Geometric polycentricity is validated, not functional TOD behaviour.",
        ),
        _failure(
            "MF-009",
            "Polycentric functional independence and transit concentration are untested",
            "traffic-function science",
            "2026-08-20 audit of 2d99f80",
            "P1 scientific",
            "NOT_EVALUATED",
            "Geometric centres can exist without distinct accessibility basins or TOD-like transport function.",
            "No completed functional-centre or transit-service experiment is present in this evidence package.",
            "No claim was promoted; the limitation is explicit.",
            "Run preregistered centre-level demand, accessibility, transit concentration, and route substitution tests.",
            "Functional polycentricity remains NOT_EVALUATED.",
        ),
        _failure(
            "MF-010",
            "Superblock implementation produced one-axis elongated strips",
            "morphology grammar",
            "2026-08-20 audit of 2d99f80",
            "P1",
            "CLOSED",
            "A large-area outlier could pass while remaining a thin strip rather than a two-dimensional macroblock.",
            "PR #17 two-axis removal, aspect-ratio, minimum-axis, count, and hierarchy-perimeter tests; held-out cases.",
            "Current grammar requires multiple bounded two-dimensional macrocells with hierarchy-qualified perimeters.",
            "Retain the two-axis structural tests and evaluate internal access separately.",
            "The structural macroblock claim is closed within the current deterministic grammar.",
        ),
        _failure(
            "MF-011",
            "Superblock access, circulation, and mode function are unvalidated",
            "traffic-function science",
            "2026-08-20 audit of 2d99f80",
            "P1 scientific",
            "NOT_EVALUATED",
            "Removing motorized carriers can create a geometric macroblock without usable internal circulation or access.",
            "No completed motorized-access, pedestrian-layer, travel-time, or circulation experiment is in scope.",
            "No functional superblock claim was made.",
            "Define typed internal access and test mode-specific reachability and performance.",
            "Functional superblock validity remains NOT_EVALUATED.",
        ),
        _failure(
            "MF-012",
            "Organic topology claim exceeded a warped-grid implementation",
            "claim accuracy",
            "2026-08-20 audit of 2d99f80",
            "P1",
            "CLOSED",
            "Smooth displacement changed embedding but not branching, dead ends, degree structure, or accretion grammar.",
            "Current public label is 'Curvilinear Warped Grid (organic compatibility ID)' and held-out bent-connector checks.",
            "The claim was narrowed to deterministic curvilinear embedding while retaining the compatibility identifier.",
            "A future organic-topology claim needs branching, angle, degree, dead-end, and block-shape tests.",
            "Curvilinear geometry is validated; organic street-network topology is not claimed.",
        ),
        _failure(
            "MF-013",
            "Morphology semantic tests used weak proxy statistics",
            "test validity",
            "2026-08-20 audit of 2d99f80",
            "P1",
            "CLOSED",
            "Orientation entropy or coordinate inequality could pass networks lacking the named structure.",
            "PR #17 structural falsifiers for cycles, winding, catchments, hierarchy paths, macroblocks, and curvilinear connectors.",
            "Proxy-only assertions were replaced or bounded by direct structural witnesses.",
            "Future morphology claims require claim-specific falsifiers, not reuse of unrelated summary metrics.",
            "The six current structural labels have direct tests at their stated claim level.",
        ),
        _failure(
            "MF-014",
            "The v4 control table does not score scalable_synthetic_v2",
            "scientific evidence",
            "2026-08-20 audit of 2d99f80",
            "P1 scientific",
            "OPEN",
            "A valid historical/sidecar table cannot establish empirical validity for the newly changed scalable generator.",
            "morphology-control-table-v4 arm inventory and its explicit diagnostic-only claim boundary.",
            "No silent inference is made from v4 to scalable_synthetic_v2.",
            "Build a preregistered held-out OSM morphology table whose treatment arm is scalable_synthetic_v2.",
            "The present 15/18 seed result is structural only and not empirical control-table validation.",
        ),
        _failure(
            "MF-015",
            "Full v4 artifact and manifest were not rederived in CI",
            "reproducibility",
            "2026-08-20 audit of 2d99f80",
            "P1",
            "CLOSED",
            "Selected gallery checks could pass while the 135-score table or manifest fields drifted.",
            "PR #17 audit-gallery job in runs 32564391135 and 32564393072.",
            "CI now rederives the full v4 JSON/Markdown and verifies schema, table fingerprint, file hashes, and bytes.",
            "Keep the full matrix command explicit and exact in CI.",
            "Same-head v4 artifact reproducibility is closed for the PR #17 tree.",
        ),
        _failure(
            "MF-016",
            "Score identity omitted or made optional source/spec fields",
            "scientific identity",
            "2026-08-20 audit of 2d99f80",
            "P2",
            "CLOSED",
            "Equal metric values could hide different source topology or measurement definitions.",
            "Current v4 score payload and constructor tests.",
            "source_topology_fingerprint and measurement_spec are mandatory for current-schema scores and fingerprinted.",
            "Reject unknown schemas as tracked separately in MF-022.",
            "Current v4 score identity binds both source topology and measurement specification.",
        ),
        _failure(
            "MF-017",
            "PNG previews are digest-bound but not source-rerendered",
            "visual evidence",
            "2026-08-20 audit of 2d99f80",
            "P2",
            "OPEN",
            "A committed PNG can match its recorded digest without proving that a current renderer reproduced it.",
            "Scalable gallery checker and README distinguish SVG authority from PNG preview.",
            "Success wording now states SVG rederivation and PNG digest comparison separately.",
            "Rerender PNGs in a pinned raster stack if preview-byte reproduction becomes an acceptance requirement.",
            "PNG maps in this package are navigational previews; SVG/source fingerprints carry scientific identity.",
        ),
        _failure(
            "MF-018",
            "Exact branch-head external CI was initially unavailable",
            "remote verification",
            "2026-08-20 audit of 2d99f80",
            "P1",
            "CLOSED",
            "Local evidence alone could not establish that the proposed merge tree passed protected CI.",
            "PR #17 push run 32564391135 and pull-request run 32564393072; both ci gate jobs succeeded.",
            "Exact head 6d6e056 and synthetic merge were tested and shared tree 622dbe3779; PR #17 merged as e1979df.",
            "Obtain new exact-head evidence for any future source change.",
            "PR #17 remote implementation evidence is closed; it does not validate this later report branch remotely.",
        ),
        _failure(
            "MF-019",
            "Duplicate score keys could inflate summaries and overwrite diagnostics",
            "artifact schema",
            "2026-08-22 audit of c9985ce",
            "P1",
            "CLOSED",
            "Two records with one (arm, case) identity could count twice in summaries but collapse in dictionaries.",
            "Current MorphologyControlTable constructor and renderer duplicate-key regression tests.",
            "Both the table and renderer reject duplicate (arm, case) keys before aggregation.",
            "Retain uniqueness as a schema invariant.",
            "The duplicate-key evidence-normalization path is closed.",
        ),
        _failure(
            "MF-020",
            "Catch-all exceptions could be normalized as skipped cases",
            "artifact collection",
            "2026-08-22 audit of c9985ce",
            "P1",
            "CLOSED",
            "Programming or schema failures could be committed as apparently legitimate missing data.",
            "Current typed SkippedCase collection and exact 135 score plus 22 skip partition tests.",
            "Unsupported standard styles are classified before generation; only UnsupportedOSMTagError is converted; all other exceptions abort.",
            "Keep exact score/skip/attempt partition equality and typed exceptions.",
            "Unexpected program failures can no longer silently become normal skips in this collector.",
        ),
        _failure(
            "MF-021",
            "Validation ledger contradicted live remote verification",
            "governance",
            "2026-08-22 audit of c9985ce",
            "P1 governance",
            "CLOSED",
            "The canonical ledger said no push or PR existed after exact-head CI had succeeded.",
            "Updated validation ledger plus PR #17 remote receipt in this package.",
            "The predecessor receipt and later review-fix receipt are explicitly separated by commit identity.",
            "Keep live external receipts outside self-referential commit content and bind them by SHA/tree.",
            "The PR #17 ledger contradiction is closed.",
        ),
        _failure(
            "MF-022",
            "Unknown control-table schema names bypass current identity guards",
            "artifact schema",
            "2026-08-22 audit of c9985ce",
            "P2",
            "OPEN",
            "A typo schema string can avoid v4 source/spec requirements because enforcement is equality-gated.",
            "src/metroflow/city/morphology_control_table.py current-schema conditional.",
            "No source change was authorized in this report work unit.",
            "Reject schemas outside an explicit supported-version set or split legacy readers from the current writer.",
            "Unknown-schema inputs are not covered by the v4 identity claim.",
        ),
        _failure(
            "MF-023",
            "Standard supported-style capability has a duplicated source of truth",
            "maintainability",
            "2026-08-22 audit of 6d6e056",
            "P2",
            "OPEN",
            "The benchmark can keep skipping a style after the standard generator gains support.",
            "STANDARD_SUPPORTED_STYLES in the control-table benchmark versus generator capability.",
            "No source change was authorized in this report work unit.",
            "Export a generator capability registry or assert equality in a focused invariant test.",
            "The current matrix is correct, but future capability drift remains possible.",
        ),
        _failure(
            "MF-024",
            "SkippedCase reason_code remains a free string",
            "artifact schema",
            "2026-08-22 audit of 6d6e056",
            "P2",
            "OPEN",
            "A new typo or undeclared reason can enter code even though the committed artifact is exact-tested.",
            "SkippedCase declaration and current artifact reason distribution.",
            "Current production paths emit exactly three reviewed codes and artifact bytes pin their distribution.",
            "Use a SkipReason enum or enforce an allowlist at construction.",
            "Current receipts are trustworthy; the type-level future extension boundary remains open.",
        ),
        _failure(
            "MF-025",
            "Validation ledger local test count labels a predecessor head",
            "governance",
            "2026-08-22 audit of 6d6e056",
            "P2",
            "OPEN",
            "Readers can misread 1,473 passed as the latest head result rather than the predecessor candidate.",
            "VALIDATION_LEDGER.md predecessor receipt and PR #17 review summary reporting 1,483 passed.",
            "Commit identity makes the older number technically scoped, but the prose has not been relabelled in this work unit.",
            "Label initial-candidate and review-fix local results on separate lines.",
            "Do not use the 1,473 count as a current-tree full-suite receipt.",
        ),
        _failure(
            "MF-026",
            "Seven-metric envelope admits a morphology null operator",
            "scientific validity",
            "2026-08-09 G0 map-evidence recovery",
            "P1 scientific",
            "OPEN",
            "A sidecar local-fabric control can pass all seven empirical metrics while remaining visibly non-city-like.",
            "artifacts/external_audit_2_maps and morphology-control-table-v4 diagnostic results.",
            "The result is disclosed as a falsifier of sufficiency; no realism promotion is made.",
            "Add independently justified discriminators and held-out controls before empirical morphology claims.",
            "Passing the v4 metric envelope is not sufficient evidence of urban realism.",
        ),
        _failure(
            "MF-027",
            "orientation_order is vacuous in the current empirical envelope",
            "measurement validity",
            "2026-08-07 plausibility audit repair",
            "P2 scientific",
            "OPEN",
            "Near-universal coverage makes the metric unable to falsify treatment maps.",
            "CLAIM_LEDGER.md and morphology-control-table-v4 diagnostics report 0.998 coverage.",
            "The metric is reported rather than counted as silent passing evidence.",
            "Recalibrate, replace, or preregister a non-vacuous threshold on independent data.",
            "orientation_order does not support a morphology-validity claim.",
        ),
        _failure(
            "MF-028",
            "Geometry/topology diagnostics are reported but not gated",
            "measurement validity",
            "2026-08-20 audit of 2d99f80",
            "P2 scientific",
            "OPEN",
            "Unregistered geometry touches and other diagnostics can coexist with a nominal table pass.",
            "v4 diagnostics, including growth_fabric_v1 cases with up to 23 unregistered touches.",
            "Diagnostics are disclosed and not misrepresented as acceptance gates.",
            "Define justified thresholds and ownership semantics before gating them.",
            "Reported diagnostics cannot be treated as passed scientific criteria.",
        ),
        _failure(
            "MF-029",
            "realistic_synthetic_v1 passed zero of 30 morphology cases",
            "negative scientific result",
            "2026-07 PR62 plausibility audit",
            "P0 promotion blocker",
            "NEGATIVE_RESULT",
            "The proposed realistic generator was too highly connected and had too few dead ends across the fixed matrix.",
            "artifacts/runtime_spine_review/realistic-city-pr62-plausibility and CLAIM_LEDGER.md.",
            "The negative result was preserved and default promotion remained blocked.",
            "A new generator revision needs a preregistered, independent empirical protocol; do not tune against this failed holdout.",
            "The PR62 empirical morphology promotion claim is rejected.",
        ),
        _failure(
            "MF-030",
            "realistic_synthetic_v1 failed 100k generation and throughput gates",
            "negative runtime result",
            "2026-07 PR63 scale/product gate",
            "P0 promotion blocker",
            "NEGATIVE_RESULT",
            "All three seeds missed generation wall, realized population, and paired throughput requirements.",
            "PR63 canonical runtime artifacts summarized in CLAIM_LEDGER.md.",
            "The negative result was preserved; standard remained the runtime default.",
            "Rework and remeasure using a new versioned protocol rather than weakening the failed gate.",
            "Runtime-default promotion remains blocked.",
        ),
        _failure(
            "MF-031",
            "spacing_scale 3.0 was fitted to a repaired bug rather than rederived",
            "calibration debt",
            "2026-08 external map audit",
            "P2 scientific",
            "OPEN",
            "A parameter calibrated against defective measurements may encode the defect rather than urban morphology.",
            "artifacts/external_audit_2_maps/README.md calibration caveat.",
            "The parameter is disclosed as historical debt, not empirical validation.",
            "Rederive it under a preregistered measurement specification and independent calibration set.",
            "No scientific inference may rely on spacing_scale 3.0 as a validated calibration.",
        ),
        _failure(
            "MF-032",
            "The control table lacks a block-size discriminator",
            "measurement gap",
            "2026-08 external map audit",
            "P2 scientific",
            "OPEN",
            "Networks with implausible block scale can satisfy the existing seven metrics.",
            "artifacts/external_audit_2_maps/README.md and the null-operator result.",
            "The missing dimension is disclosed; no surrogate metric is silently substituted.",
            "Add a source-compatible block/face-size statistic with held-out calibration.",
            "The present empirical envelope is incomplete for block morphology.",
        ),
        _failure(
            "MF-033",
            "Held-out grid_core failed the axis-alignment contract in all three seeds",
            "negative held-out result",
            "2026-08-22 seed-held-out run",
            "P1 scientific",
            "NEGATIVE_RESULT",
            "Only 1,724/3,167, 1,740/3,178, and 1,681/3,081 semantic carriers were counted as axis-aligned.",
            "evidence/heldout_morphology_results.json cases grid_core seeds 503, 701, and 907.",
            "The aggregate verdict is FAIL at 15/18; thresholds and results were not changed after observation.",
            "Diagnose semantics versus geometry under a new preregistered protocol before modifying implementation or criterion.",
            "The grid_core held-out structural claim is a NEGATIVE_RESULT.",
        ),
        _failure(
            "MF-034",
            "Grid-core failure has unresolved construct-validity ambiguity",
            "scientific interpretation",
            "2026-08-23 adversarial synthesis",
            "P1 scientific",
            "CONTESTED",
            "The failed ratio may indicate genuinely warped grid carriers or an over-strict classifier that excludes intended connectors.",
            "heldout validator source plus grid_core witness counts; no independent block-orientation measure was run.",
            "The failure is preserved without selecting the favorable explanation.",
            "Predeclare a diagnostic decomposition, inspect source semantics, and use an independent orientation/block witness on new seeds.",
            "Cause is CONTESTED; neither generator defect nor invalid test is established by this result alone.",
        ),
        _failure(
            "MF-035",
            "Held-out validation is seed-only, not fresh OSM or named-city validation",
            "scope limitation",
            "2026-08-22 held-out protocol",
            "P1 scientific",
            "NOT_EVALUATED",
            "Unseen pseudo-random seeds test replay and grammar generalization but not external urban realism.",
            "Result protocol declares holdout_kind seed_heldout_structural_not_fresh_osm and fresh_osm_holdout_status NOT_EVALUATED.",
            "The report names this limitation in every promotion decision.",
            "Run a leakage-controlled fresh-OSM/named-region comparison with licensed frozen extracts and preregistered metrics.",
            "This is NOT fresh-OSM empirical validation.",
        ),
        _failure(
            "MF-036",
            "Traffic-functional development probe did not reach a valid result",
            "negative traffic result",
            "2026-08-22 bounded traffic-functional attempt",
            "P1 research blocker",
            "NEGATIVE_RESULT",
            "The only durable test cache records failure of the nonvacuous-and-directional probe; no complete matrix or durable result artifact exists.",
            "/tmp/urban-traffic-heldout-functional-20260822 pytest lastfailed receipt and session record; no result JSON/Markdown was emitted.",
            "The attempt is preserved as a NEGATIVE_RESULT and was not rerun, repaired, or normalized in this report work unit.",
            "Design a new versioned functional protocol with nonvacuity, cache invalidation, conservation, deterministic replay, and baseline comparison before execution.",
            "Traffic-functional validation was not completed; traffic algorithms remain research-incomplete and no completeness claim is permitted.",
        ),
    ]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_text(path, json.dumps(payload, indent=2, sort_keys=True))


def _png_dimensions(path: Path) -> tuple[int, int]:
    raw = path.read_bytes()
    if raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
        raise ValueError(f"not a PNG with IHDR: {path}")
    return struct.unpack(">II", raw[16:24])


def _md_escape(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _receipt_payloads() -> dict[str, dict[str, Any]]:
    return {
        "source_receipt.json": {
            "schema_version": "metroflow_report_source_receipt_v1",
            "captured_on": "2026-08-23",
            "repository": "https://github.com/cosmosapjw-quantum/urban_traffic_demo.git",
            "source_role": "map generation and held-out measurement authority",
            "commit": SOURCE_COMMIT,
            "tree": SOURCE_TREE,
            "merged_pr": 17,
            "pr_head_commit": "6d6e05630b718b50cf311aa127dfb2eeb8d8530f",
            "pr_head_tree": SOURCE_TREE,
            "worktree_policy": {
                "implementation_source_modified": False,
                "maps_regenerated_in_report_work_unit": False,
                "thresholds_or_seeds_changed": False,
                "traffic_experiment_rerun": False,
                "report_branch": "audit/heldout-morphology-adversarial-report-20260823",
            },
            "heldout_evidence": {
                "results_sha256": "f4e6a36be3d700369cca8d2aaaecc2ef0a88bd6afa30e1927c1f47f00c9057fd",
                "sample_manifest_sha256": "998af7fa9539993a4e9f63df7802505ee1381e2a7b00c7ecd9dbaa58a686aec3",
                "validator_sha256": "713820af5a59fa6e9cd0b0d77bd42c216a72a0ab055b277e9f48da8bfaf9d7d1",
                "scientific_fingerprint": SCIENTIFIC_FINGERPRINT,
            },
            "prior_traffic_attempt": {
                "status": "NEGATIVE_RESULT_EVIDENCE_LIMITED",
                "worktree_observed": "/tmp/urban-traffic-heldout-functional-20260822",
                "lastfailed_test": "tests/test_morphology_traffic_functional.py::test_development_seed_traffic_probe_is_nonvacuous_and_directional",
                "durable_result_artifact_present": False,
                "complete_matrix_executed": False,
                "rerun_in_this_work_unit": False,
                "interpretation": (
                    "The cache witness records an incomplete development attempt. It "
                    "does not distinguish an algorithm defect from an experiment defect."
                ),
            },
            "source_state_claim": (
                "The source commit/tree identify the already-generated maps and "
                "measurements. Report-only commits are not generator evidence."
            ),
        },
        "harness_receipt.json": {
            "schema_version": "physmath_harness_application_receipt_v1",
            "captured_on": "2026-08-23",
            "instruction_boundary": (
                "Harness documents were applied as validation methods. They did not "
                "replace or expand the user's request, authorize algorithm changes, "
                "or authorize publication, push, merge, or fresh external data."
            ),
            "installed": False,
            "repository_agents_file_overwritten": False,
            "archives": [
                {
                    "role": "coding validation harness",
                    "basename": "physmath-coding-harness-gpt56.zip",
                    "version": "3.1.0",
                    "bytes": 25533,
                    "entry_count": 46,
                    "sha256": "6e67e999a0c19f6ed9de7c339067cc11691d5cf5cb662a11756d8fc393c849b4",
                    "archive_safety": "CRC/path/duplicate/symlink inspection passed",
                    "applied_surfaces": [
                        "finite acceptance and reproduction contract",
                        "software validation",
                        "scientific and numerical claim separation",
                        "reproducibility checks",
                        "independent read-only review",
                    ],
                },
                {
                    "role": "research validation harness",
                    "basename": "physmath-research-harness-gpt56.zip",
                    "version": "3.1.0",
                    "bytes": 32648,
                    "entry_count": 59,
                    "sha256": "9adde688f8020e7feb2c1c0304b3204dbe70dd01e2d87e64a5c4eb357c019934",
                    "archive_safety": "CRC/path/duplicate/symlink inspection passed",
                    "applied_surfaces": [
                        "evidence-before-narrative ledger",
                        "claim audit",
                        "adversarial review",
                        "decision gate",
                        "negative-result preservation",
                    ],
                },
            ],
            "acceptance_boundary": {
                "map_set": "six seed-503 held-out preview/authority pairs",
                "analysis_set": "all 18 held-out cases plus MF-001 through MF-036",
                "algorithm_changes": 0,
                "fresh_osm_downloads": 0,
                "traffic_reruns": 0,
            },
        },
        "pr17_remote_receipt.json": {
            "schema_version": "github_pr_remote_evidence_receipt_v1",
            "retrieved_on": "2026-08-23",
            "repository": "cosmosapjw-quantum/urban_traffic_demo",
            "pull_request": 17,
            "url": "https://github.com/cosmosapjw-quantum/urban_traffic_demo/pull/17",
            "state": "MERGED",
            "merged_at": "2026-08-22T10:19:14Z",
            "head_commit": "6d6e05630b718b50cf311aa127dfb2eeb8d8530f",
            "merge_commit": SOURCE_COMMIT,
            "head_tree": SOURCE_TREE,
            "merge_tree": SOURCE_TREE,
            "tree_identity": "MATCH",
            "runs": [
                {
                    "id": 32564391135,
                    "event": "push",
                    "head_sha": "6d6e05630b718b50cf311aa127dfb2eeb8d8530f",
                    "conclusion": "success",
                    "url": "https://github.com/cosmosapjw-quantum/urban_traffic_demo/actions/runs/32564391135",
                    "ci_gate_job": 97013052528,
                },
                {
                    "id": 32564393072,
                    "event": "pull_request synthetic merge",
                    "head_sha": "6d6e05630b718b50cf311aa127dfb2eeb8d8530f",
                    "conclusion": "success",
                    "url": "https://github.com/cosmosapjw-quantum/urban_traffic_demo/actions/runs/32564393072",
                    "ci_gate_job": 97012753138,
                },
            ],
            "successful_surfaces": [
                "test partition",
                "five disjoint test shards",
                "Ruff",
                "OSMnx oracle parity",
                "17-case audit gallery",
                "six-case scalable gallery",
                "135-score plus 22-skip v4 control table",
                "final ci gate",
            ],
            "claim_boundary": (
                "This proves exact-tree implementation and artifact gates for PR #17. "
                "It does not prove empirical morphology, traffic validity, or this "
                "later report branch's remote CI state."
            ),
        },
    }


def _render_failure_markdown(records: list[dict[str, str]]) -> str:
    counts = Counter(record["current_state"] for record in records)
    lines = [
        "# MetroFlow Morphology Failure Inventory",
        "",
        "Scope: all morphology/evidence failures supplied in the audit sequence, "
        "the current seed-held-out result, the prior bounded traffic-functional "
        "attempt, and directly relevant canonical ledgers reviewed through 2026-08-23.",
        "",
        "This is a failure-preservation ledger, not a statement that every item is "
        "still open. CLOSED means the identified path was directly repaired. "
        "NEGATIVE_RESULT means an unfavorable experiment is retained without repair "
        "or reinterpretation.",
        "",
        "| State | Count |",
        "| --- | ---: |",
    ]
    for state in (
        "CLOSED",
        "PARTIALLY_CLOSED",
        "OPEN",
        "NEGATIVE_RESULT",
        "NOT_EVALUATED",
        "CONTESTED",
    ):
        lines.append(f"| {state} | {counts[state]} |")
    lines.extend(["", "## Complete inventory", ""])
    for record in records:
        lines.extend(
            [
                f"### {record['id']} - {record['title']}",
                "",
                f"- Domain: {record['domain']}",
                f"- First observed: {record['first_observed']}",
                f"- Original severity: {record['original_severity']}",
                f"- Current state: **{record['current_state']}**",
                f"- Impact: {record['impact']}",
                f"- Evidence: {record['evidence']}",
                f"- Resolution/current handling: {record['resolution']}",
                f"- Remaining gate: {record['remaining_gate']}",
                f"- Claim effect: {record['claim_effect']}",
                "",
            ]
        )
    return "\n".join(lines)


def _claim_rows() -> list[tuple[str, str, str, str, str]]:
    return [
        (
            "C-01",
            "The six sample maps and 18 measurements bind to source tree 622dbe3779.",
            "VALIDATED",
            "source_receipt.json, sample_manifest.json, scientific fingerprint",
            "Identity/provenance only.",
        ),
        (
            "C-02",
            "The held-out inventory contains exactly 18 scored attempts and no skips.",
            "VALIDATED",
            "heldout_morphology_results.json and package checker",
            "Completeness of this fixed matrix only.",
        ),
        (
            "C-03",
            "All 18 cases reproduced their deterministic network fingerprint.",
            "VALIDATED",
            "deterministic_replay check in every result case",
            "Same-code deterministic replay; not historical environment replay.",
        ),
        (
            "C-04",
            "Five non-grid styles satisfy their stated structural checks on all three held-out seeds.",
            "VALIDATED",
            "15 passing non-grid cases and their direct witnesses",
            "Seed-held-out structural morphology only.",
        ),
        (
            "C-05",
            "grid_core satisfies its held-out axis-alignment contract.",
            "NEGATIVE_RESULT",
            "0/3 grid_core cases pass axis_aligned_grid_core",
            "Failure cause remains contested; threshold is frozen.",
        ),
        (
            "C-06",
            "The full six-style held-out protocol passes.",
            "NEGATIVE_RESULT",
            "15/18 overall, verdict FAIL",
            "Do not average away the failed style.",
        ),
        (
            "C-07",
            "The generated networks reproduce real-city morphology on fresh external cities.",
            "FORBIDDEN",
            "No fresh OSM holdout was executed; MF-014, MF-026, MF-035",
            "NOT fresh-OSM empirical validation.",
        ),
        (
            "C-08",
            "The compatibility style implements organic street-network topology.",
            "FORBIDDEN",
            "MF-012; only curvilinear connector embedding is tested",
            "Use the public warped-grid label.",
        ),
        (
            "C-09",
            "Traffic-functional validity was established.",
            "NEGATIVE_RESULT",
            "MF-036; one development probe lastfailed, no durable result matrix",
            "Traffic-functional validation was not completed.",
        ),
        (
            "C-10",
            "The traffic algorithms are complete or production-valid.",
            "FORBIDDEN",
            "User claim boundary and MF-009, MF-011, MF-030, MF-036",
            "Functionality is the next target; completeness is explicitly out of scope.",
        ),
        (
            "C-11",
            "scalable_synthetic_v2 is ready to replace the runtime default.",
            "FORBIDDEN",
            "MF-014, MF-029, MF-030, MF-033, MF-035, MF-036",
            "runtime-default promotion remains blocked.",
        ),
        (
            "C-12",
            "PR #17 exact-head and synthetic-merge implementation gates passed.",
            "VALIDATED",
            "pr17_remote_receipt.json and two successful ci gate jobs",
            "Remote software evidence; not scientific promotion.",
        ),
    ]


def _render_claim_ledger() -> str:
    lines = [
        "# Claim-Evidence Ledger",
        "",
        "Statuses are intentionally asymmetric: VALIDATED is limited to the exact "
        "evidence surface; NEGATIVE_RESULT preserves a failed or incomplete result; "
        "FORBIDDEN marks an inference the evidence cannot support.",
        "",
        "| ID | Claim | Status | Evidence | Boundary |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in _claim_rows():
        lines.append("| " + " | ".join(_md_escape(value) for value in row) + " |")
    lines.extend(
        [
            "",
            "## Promotion decision",
            "",
            "The structural milestone in merged PR #17 remains valid. The new "
            "seed-held-out experiment is a 15/18 **NEGATIVE_RESULT** because grid_core "
            "failed all three seeds. Fresh empirical morphology, traffic-functional "
            "validity, traffic-algorithm completeness, and runtime-default promotion "
            "are **FORBIDDEN** interpretations of this package.",
        ]
    )
    return "\n".join(lines)


def _result_rows(results: dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for style_id in STYLE_ORDER:
        cases = [case for case in results["cases"] if case["style_id"] == style_id]
        rows.append(
            [
                STYLE_LABELS[style_id],
                f"{sum(bool(case['passed']) for case in cases)}/{len(cases)}",
                ", ".join(str(case["seed"]) for case in cases),
                "PASS" if all(case["passed"] for case in cases) else "FAIL",
            ]
        )
    return rows


def _style_analysis(results: dict[str, Any], style_id: str) -> list[str]:
    cases = [case for case in results["cases"] if case["style_id"] == style_id]
    if style_id == "grid_core":
        ratios = [
            case["witnesses"]["axis_aligned_core_count"]
            / case["witnesses"]["core_carrier_count"]
            for case in cases
        ]
        return [
            "All generic checks passed: networks were nonempty, style identity was "
            "bound, one centre was present, two semantic carrier axes existed, and "
            "deterministic replay held.",
            "The claim-specific axis_aligned_grid_core check failed on every seed. "
            f"Observed aligned shares were {', '.join(f'{ratio:.3%}' for ratio in ratios)}.",
            "The raw witnesses are internally surprising: semantic horizontal and "
            "vertical carrier counts sum to the carrier total, yet the independent "
            "axis-aligned count is much smaller. This may expose warped geometry, a "
            "semantic-to-geometric mismatch, or an over-strict classifier. The current "
            "evidence does not choose among them.",
        ]
    if style_id == "ring_radial":
        return [
            "Every seed contains multiple closed degree-2 orbital cycles with winding "
            "magnitude one and distinct mean radii.",
            "Orbital counts are "
            + ", ".join(str(case["witnesses"]["concentric_orbital_count"]) for case in cases)
            + "; maximum radial CV across the matrix is "
            + f"{max(case['witnesses']['max_radial_cv'] for case in cases):.3e}.",
            "This falsifies the former central-cross masquerade, but does not calibrate "
            "ring spacing or traffic resilience against real cities.",
        ]
    if style_id == "river_constrained":
        return [
            "Each held-out network has two-sided centres, three bridge carriers, and "
            "three bridge failure groups.",
            "The result establishes a deterministic structural bottleneck grammar. It "
            "does not establish evacuation performance or empirical bridge density.",
        ]
    if style_id == "polycentric_tod":
        return [
            "Every case has three non-collinear centres, three nonempty geometric "
            "catchments, and all three expected centre-pair hierarchy paths.",
            "The evidence supports geometric polycentricity. It does not measure "
            "transit service, independent demand basins, or functional accessibility concentration.",
        ]
    if style_id == "superblock_mixed":
        return [
            "The three cases contain 6, 6, and 5 hierarchy-perimeter macrocells. The "
            "smallest qualifying minor axis is 968,732 mm and the largest reported "
            "aspect ratio is 1.260, defeating the former one-axis strip false positive.",
            "Mode-specific internal access, circulation, walkability, and travel time "
            "remain unmeasured.",
        ]
    return [
        "Bent-connector shares are "
        + ", ".join(f"{case['witnesses']['bent_connector_share']:.3%}" for case in cases)
        + ", all above the preregistered 90% threshold.",
        "This validates a curvilinear warped-grid embedding only. The report does not "
        "claim organic topology, branching history, or empirical urban realism.",
    ]


def _render_report(
    results: dict[str, Any],
    records: list[dict[str, str]],
    has_review: bool,
) -> str:
    counts = Counter(record["current_state"] for record in records)
    lines = [
        "# MetroFlow Held-Out Morphology Adversarial Audit",
        "",
        "**Report date:** 2026-08-23",
        "",
        f"**Map/measurement source:** `{SOURCE_COMMIT}` / tree `{SOURCE_TREE}`",
        "",
        f"**Scientific fingerprint:** `{SCIENTIFIC_FINGERPRINT}`",
        "",
        "**Primary verdict:** **FAIL - 15/18 held-out cases passed**",
        "",
        "## Executive decision",
        "",
        "This package validates a bounded **seed-held-out structural morphology** "
        "protocol, not a complete city or traffic model. Five styles passed all three "
        "unseen seeds; `grid_core` failed its axis-alignment criterion on seeds 503, "
        "701, and 907. The exact aggregate is **15/18**, with zero skipped attempts, "
        "so the protocol verdict is **FAIL**.",
        "",
        "The result is **NOT fresh-OSM empirical validation**. It does not test named "
        "cities, held-out external road data, traffic flow, route choice, travel time, "
        "resilience, or land-use interaction. **traffic-functional validation was not "
        "completed**: the earlier development probe left one lastfailed witness and no "
        "durable result matrix. Consistent with the user's boundary, traffic algorithms "
        "are treated as research-incomplete and functionality - not completeness - is "
        "the next validation target. **runtime-default promotion remains blocked**.",
        "",
        "Merged PR #17 is not invalidated: its structural implementation and evidence "
        "identity gates passed exact-head and synthetic-merge CI on the identical tree. "
        "The new failure narrows what can be said about grid_core under unseen seeds.",
        "",
        "## Scope and frozen boundaries",
        "",
        "Included: the six seed-503 sample maps below, all 18 measurements from three "
        "held-out seeds, the validator and manifests, exact source/harness/remote-CI "
        "receipts, and the complete scoped failure inventory MF-001 through MF-036.",
        "",
        "Excluded by design: morphology or traffic source changes, post-result threshold "
        "changes, alternate seeds, traffic repair/rerun, new OSM downloads, empirical "
        "promotion, runtime-default changes, push, PR, merge, and external publication.",
        "",
        "## Harness application",
        "",
        "The two supplied v3.1.0 archives were read as methods, not as user requests. "
        "The coding harness supplied the finite acceptance/reproduction contract and "
        "separation of software, scientific, numerical, and reproducibility evidence. "
        "The research harness supplied evidence-before-narrative, claim audit, decision "
        "gate, adversarial review, and negative-result preservation. Neither archive was "
        "installed and the repository AGENTS.md was not replaced.",
        "",
        "## Provenance and evidence identity",
        "",
        f"The maps and results name commit `{SOURCE_COMMIT}` and tree `{SOURCE_TREE}`. "
        "PR #17 head `6d6e05630b718b50cf311aa127dfb2eeb8d8530f` has the same tree. "
        "GitHub push run 32564391135 and pull-request run 32564393072 both ended in "
        "successful final `ci gate` jobs before merge. This package records those facts "
        "as implementation evidence, not as empirical validation.",
        "",
        "The results file has SHA-256 `f4e6a36b...c9057fd`; the sample manifest has "
        "`998af7fa...686aec3`; and the validator has `713820af...af9d7d1`. The package "
        "manifest binds complete hashes and byte sizes for every report file except itself.",
        "",
        "## Protocol",
        "",
        "The fixed matrix is 6 styles x 3 unseen seeds (503, 701, 907) at target "
        "population 100,000 and urbanized area 25.0 km2. Development seeds were 0, 1, "
        "2, 3, 4, 17, 29, 42, and 101. Each case requires nonempty output, exact style "
        "identity, deterministic replay, and a style-specific direct structural falsifier. "
        "The protocol records 18 expected, 18 attempted, 18 scored, and 0 skipped.",
        "",
        "Thresholds were frozen before observation: at least two concentric rings with "
        "radial CV below 0.01; at least three river bridges/failure groups; at least "
        "three polycentric centres; at least four superblocks with minor axis >=700,000 "
        "mm and aspect ratio <=2.5; and bent-connector share >0.9. The grid criterion "
        "is a Boolean structural classifier in the frozen validator.",
        "",
        "## Results",
        "",
        "| Style | Passed | Seeds | Verdict |",
        "| --- | ---: | --- | --- |",
    ]
    for row in _result_rows(results):
        lines.append("| " + " | ".join(_md_escape(value) for value in row) + " |")
    lines.extend(
        [
            "",
            "All 18 networks were nonempty, style-bound, and deterministic under the "
            "validator replay. That generic success cannot override the three direct "
            "grid failures.",
            "",
            "## Style-by-style adversarial analysis",
            "",
        ]
    )
    for style_id in STYLE_ORDER:
        lines.extend([f"### {STYLE_LABELS[style_id]}", ""])
        for paragraph in _style_analysis(results, style_id):
            lines.extend([paragraph, ""])
    lines.extend(["## Generated map samples", ""])
    for style_id in STYLE_ORDER:
        lines.extend(
            [
                f"### {STYLE_LABELS[style_id]} - seed 503",
                "",
                f"![{STYLE_LABELS[style_id]} seed 503](maps/map_{style_id}_s503.png)",
                "",
                f"Raster preview: `maps/map_{style_id}_s503.png`; SVG authority: "
                f"`maps/map_{style_id}_s503.svg`. PNG is digest-bound preview evidence; "
                "it was not independently rerendered in this report-only work unit.",
                "",
            ]
        )
    lines.extend(
        [
            "### Six-map contact sheet",
            "",
            "![Held-out morphology contact sheet](maps/heldout_morphology_seed503_contact_sheet.png)",
            "",
            "The visual atlas is for navigation and qualitative attack. Scientific "
            "acceptance comes from frozen source, exact fingerprints, and falsifiable "
            "measurements, not visual plausibility.",
            "",
            "## Failure history synthesis",
            "",
            f"The mechanical inventory contains 36 unique records: {counts['CLOSED']} "
            f"CLOSED, {counts['PARTIALLY_CLOSED']} PARTIALLY_CLOSED, {counts['OPEN']} OPEN, "
            f"{counts['NEGATIVE_RESULT']} NEGATIVE_RESULT, {counts['NOT_EVALUATED']} "
            f"NOT_EVALUATED, and {counts['CONTESTED']} CONTESTED. It begins with MF-001 "
            "(legacy gallery provenance) and ends with MF-036 (incomplete traffic-functional probe).",
            "",
            "Closed findings remain in the package because an external auditor must be "
            "able to reconstruct why later assurance exists. Open and negative findings "
            "are not diluted by the number of closed items. See `FAILURE_INVENTORY.md` "
            "and machine-readable `FAILURE_INVENTORY.json` for every impact, evidence "
            "source, resolution, remaining gate, and claim effect.",
            "",
            "The most important retained blockers are MF-014 (no scalable_v2 arm in the "
            "v4 empirical table), MF-026/MF-032 (metric-envelope insufficiency), MF-033 "
            "and MF-034 (grid failure and unresolved cause), MF-035 (no fresh external "
            "holdout), and MF-036 (traffic-functional validation not completed).",
            "",
            "## Traffic-functional negative result",
            "",
            "The prior bounded traffic worktree contains draft source/test files and a "
            "pytest `lastfailed` key for `test_development_seed_traffic_probe_is_nonvacuous_and_directional`. "
            "There is no durable JSON/Markdown result, no complete fixed matrix, and no "
            "accepted cache-invalidation witness. This report therefore records a "
            "NEGATIVE_RESULT, not an algorithm diagnosis and not a validation result. "
            "The experiment was deliberately not rerun or repaired after the user narrowed "
            "this deliverable to held-out morphology reporting.",
            "",
            "A future functional protocol should test nonvacuity, conservation, explicit "
            "units, immutable state transition, deterministic replay, cache invalidation, "
            "baseline fallback, directional response, and bounded performance. Passing "
            "those probes would establish bounded functionality only, not completeness.",
            "",
            "## Scientific claim ceiling",
            "",
            "Supported: source-bound deterministic generation; direct structural "
            "differentiation for five styles across three unseen seeds; exact disclosure "
            "of the grid negative result; and PR #17 implementation/CI provenance.",
            "",
            "Unsupported: real-city distributional fit, held-out OSM generalization, "
            "traffic performance, route-choice validity, resilience, accessibility or "
            "land-use validity, functional TOD/superblocks, organic topology, algorithm "
            "completeness, and runtime-default promotion.",
            "",
            "## External auditor attack plan",
            "",
            "1. Run the package checker and focused behavior test without modifying artifacts.",
            "2. Recompute every manifest hash and compare PNG dimensions and SVG digests.",
            "3. Inspect the validator before the results; confirm the frozen seed split and thresholds.",
            "4. Recalculate the 15/18 partition and attack the grid classifier construct independently.",
            "5. Verify PR #17 run IDs/tree identity without treating CI as scientific evidence.",
            "6. Search all prose for forbidden promotion language and reconcile every MF identifier.",
            "7. Treat the contact sheet as navigation only; use source/fingerprint evidence for identity.",
            "",
            "## Decision gate",
            "",
            "**Artifact/report package:** admissible when its checker, focused tests, PDF "
            "text extraction, rendered-page inspection, and independent read-only review pass.",
            "",
            "**Held-out morphology protocol:** **FAIL (15/18)**. Five style contracts "
            "generalized across the three seeds; grid_core did not.",
            "",
            "**Empirical/scientific promotion:** **BLOCKED** pending fresh external data, "
            "non-vacuous morphology discriminators, and resolution of the grid construct.",
            "",
            "**Traffic-functional validation:** **NOT COMPLETED / NEGATIVE_RESULT**. "
            "Future work should validate bounded functionality while explicitly retaining "
            "the premise that the traffic algorithms require further change and research.",
            "",
            "**Runtime-default promotion:** **BLOCKED**.",
        ]
    )
    lines.extend(
        [
            "",
            "## Appendix A - complete failure index",
            "",
            "Every scoped failure appears below; `FAILURE_INVENTORY.md` supplies the "
            "full impact, evidence, resolution, and remaining-gate narrative.",
            "",
            "| ID | State | Finding | Claim effect |",
            "| --- | --- | --- | --- |",
        ]
    )
    for record in records:
        lines.append(
            "| "
            + " | ".join(
                _md_escape(value)
                for value in (
                    record["id"],
                    record["current_state"],
                    record["title"],
                    record["claim_effect"],
                )
            )
            + " |"
        )
    if has_review:
        lines.extend(
            [
                "",
                "## Independent adversarial review",
                "",
                "A separate read-only reviewer examined the frozen report candidate. Its "
                "verbatim verdict, severity counts, tested surfaces, and residual limitations "
                "are preserved in `INDEPENDENT_REVIEW.md` and bound by the evidence manifest.",
            ]
        )
    return "\n".join(lines)


def _render_auditor_readme(has_review: bool) -> str:
    review_line = ""
    if has_review:
        review_line = (
            "- `INDEPENDENT_REVIEW.md`: independent frozen-candidate review receipt.\n"
        )
    return f"""# External Auditor Entry Point

This directory is a self-contained report/evidence package for the 2026-08-23
MetroFlow seed-held-out morphology audit. Start with `REPORT.md` or `{PDF_NAME}`.

## Fast verification

From repository root:

```bash
.venv/bin/python tools/build_heldout_morphology_adversarial_report.py --check
.venv/bin/python -m pytest tests/test_heldout_morphology_adversarial_report.py -q
sha256sum artifacts/heldout_morphology_adversarial_audit_20260823/evidence/*
pdfinfo artifacts/heldout_morphology_adversarial_audit_20260823/{PDF_NAME}
pdftotext artifacts/heldout_morphology_adversarial_audit_20260823/{PDF_NAME} - | grep -E '15/18|MF-036|runtime-default'
```

PDF rebuilding requires the pinned report-only packages and does not touch the
repository runtime environment:

```bash
python3.12 -m venv /tmp/metroflow-report-pdf-venv
/tmp/metroflow-report-pdf-venv/bin/pip install \\
  reportlab==5.0.1 pillow==12.3.0 pypdf==6.16.1 pdfplumber==0.11.10
/tmp/metroflow-report-pdf-venv/bin/python \\
  tools/build_heldout_morphology_adversarial_report.py --build
```

The PDF builder uses ReportLab invariant mode. Rebuilds with the pinned stack
must be byte-identical. `--build` consumes frozen JSON/maps; it does not generate
a city, change a threshold, fetch OSM, or execute traffic.

## Evidence roles

- `EVIDENCE_MANIFEST.json`: hashes and byte sizes for every package file except itself.
- `evidence/heldout_morphology_results.json`: complete 18-case authority.
- `evidence/heldout_morphology_validator.py`: frozen executable measurement definition.
- `evidence/sample_manifest.json`: six map source/fingerprint/file bindings.
- `FAILURE_INVENTORY.json`: exact MF-001..MF-036 machine inventory.
- `CLAIM_EVIDENCE_LEDGER.md`: allowed and forbidden inferences.
{review_line}- `maps/*.svg`: vector authorities; `maps/*.png`: digest-bound previews.

## Non-negotiable interpretation

The result is FAIL at 15/18 because grid_core failed all three held-out seeds.
This is seed-held-out structural morphology, NOT fresh-OSM empirical validation.
Traffic-functional validation was not completed, traffic algorithms remain a
research target, and runtime-default promotion remains blocked.
"""


def _pdf_paragraph(text: str, style: Any) -> Any:
    from reportlab.platypus import Paragraph

    return Paragraph(html.escape(text).replace("\n", "<br/>"), style)


def _build_pdf(
    path: Path,
    results: dict[str, Any],
    records: list[dict[str, str]],
    has_review: bool,
) -> None:
    try:
        from reportlab import rl_config
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas
        from reportlab.platypus import (
            HRFlowable,
            Image,
            KeepTogether,
            PageBreak,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError(
            "PDF build requires reportlab==5.0.1 and pillow==12.3.0"
        ) from exc

    rl_config.invariant = True
    navy = colors.HexColor("#17324D")
    blue = colors.HexColor("#2F6B9A")
    pale_blue = colors.HexColor("#EAF2F8")
    red = colors.HexColor("#A93226")
    pale_red = colors.HexColor("#FDEDEC")
    green = colors.HexColor("#247A4A")
    amber = colors.HexColor("#9A6700")
    gray = colors.HexColor("#5F6B76")
    pale_gray = colors.HexColor("#F4F6F7")

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="AuditTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=28,
            textColor=navy,
            alignment=TA_LEFT,
            spaceAfter=14,
        )
    )
    styles.add(
        ParagraphStyle(
            name="AuditSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=15,
            textColor=gray,
            spaceAfter=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="AuditH1",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=19,
            textColor=navy,
            spaceBefore=8,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="AuditH2",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=blue,
            spaceBefore=7,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="AuditBody",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12.2,
            textColor=colors.HexColor("#202B33"),
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="AuditSmall",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=7.4,
            leading=9.2,
            textColor=colors.HexColor("#34495E"),
            spaceAfter=3,
        )
    )
    styles.add(
        ParagraphStyle(
            name="AuditMono",
            parent=styles["BodyText"],
            fontName="Courier",
            fontSize=6.5,
            leading=8.2,
            textColor=colors.HexColor("#263238"),
            wordWrap="CJK",
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="AuditCaption",
            parent=styles["BodyText"],
            fontName="Helvetica-Oblique",
            fontSize=7.8,
            leading=10,
            alignment=TA_CENTER,
            textColor=gray,
            spaceBefore=4,
            spaceAfter=6,
        )
    )

    class InvariantCanvas(canvas.Canvas):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs["invariant"] = 1
            kwargs["pageCompression"] = 1
            super().__init__(*args, **kwargs)
            self.setAuthor("MetroFlow adversarial audit")
            self.setCreator("MetroFlow deterministic ReportLab builder")
            self.setTitle("MetroFlow Held-Out Morphology Adversarial Audit")
            self.setSubject("Seed-held-out structural morphology and failure inventory")

    def on_page(pdf_canvas: Any, doc: Any) -> None:
        pdf_canvas.saveState()
        width, height = A4
        pdf_canvas.setStrokeColor(colors.HexColor("#D5D8DC"))
        pdf_canvas.line(0.58 * inch, height - 0.48 * inch, width - 0.58 * inch, height - 0.48 * inch)
        pdf_canvas.setFont("Helvetica", 7)
        pdf_canvas.setFillColor(gray)
        pdf_canvas.drawString(0.58 * inch, height - 0.39 * inch, "METROFLOW / EXTERNAL ADVERSARIAL AUDIT")
        pdf_canvas.drawRightString(width - 0.58 * inch, 0.35 * inch, f"Page {doc.page}")
        pdf_canvas.drawString(0.58 * inch, 0.35 * inch, "Source tree 622dbe3779 / report 2026-08-23")
        pdf_canvas.restoreState()

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=0.58 * inch,
        leftMargin=0.58 * inch,
        topMargin=0.68 * inch,
        bottomMargin=0.58 * inch,
        title="MetroFlow Held-Out Morphology Adversarial Audit",
        author="MetroFlow adversarial audit",
    )
    story: list[Any] = []

    story.append(Spacer(1, 0.45 * inch))
    story.append(_pdf_paragraph("MetroFlow Held-Out Morphology", styles["AuditTitle"]))
    story.append(_pdf_paragraph("External Adversarial Audit and Complete Failure History", styles["AuditTitle"]))
    story.append(HRFlowable(width="100%", thickness=2, color=blue, spaceBefore=3, spaceAfter=14))
    story.append(_pdf_paragraph("Frozen evidence report / 2026-08-23", styles["AuditSubtitle"]))
    decision_data = [
        [_pdf_paragraph("PRIMARY RESULT", styles["AuditSmall"]), _pdf_paragraph("FAIL - 15/18", styles["AuditH1"])],
        [_pdf_paragraph("CLAIM LEVEL", styles["AuditSmall"]), _pdf_paragraph("Seed-held-out structural morphology only", styles["AuditBody"])],
        [_pdf_paragraph("EMPIRICAL CITY VALIDATION", styles["AuditSmall"]), _pdf_paragraph("NOT EVALUATED", styles["AuditBody"])],
        [_pdf_paragraph("TRAFFIC FUNCTION", styles["AuditSmall"]), _pdf_paragraph("NOT COMPLETED / NEGATIVE RESULT", styles["AuditBody"])],
        [_pdf_paragraph("RUNTIME DEFAULT", styles["AuditSmall"]), _pdf_paragraph("PROMOTION BLOCKED", styles["AuditBody"])],
    ]
    decision_table = Table(decision_data, colWidths=[1.85 * inch, 4.95 * inch], hAlign="LEFT")
    decision_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), pale_red),
                ("BOX", (0, 0), (-1, -1), 1, red),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E6B0AA")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(decision_table)
    story.append(Spacer(1, 14))
    story.append(
        _pdf_paragraph(
            "This report preserves the failed grid_core result, all six generated map "
            "samples, the complete MF-001 through MF-036 history, and the distinction "
            "between implementation evidence and scientific promotion.",
            styles["AuditBody"],
        )
    )
    story.append(_pdf_paragraph(f"Source commit: {SOURCE_COMMIT}", styles["AuditMono"]))
    story.append(_pdf_paragraph(f"Source tree: {SOURCE_TREE}", styles["AuditMono"]))
    story.append(_pdf_paragraph(f"Scientific fingerprint: {SCIENTIFIC_FINGERPRINT}", styles["AuditMono"]))
    story.append(PageBreak())

    story.append(_pdf_paragraph("1. Executive decision", styles["AuditH1"]))
    for paragraph in (
        "The fixed matrix contains six styles and three unseen seeds. Exactly 15 of 18 cases passed, zero were skipped, and grid_core failed its claim-specific axis-alignment check on seeds 503, 701, and 907. The aggregate protocol verdict is FAIL.",
        "Five non-grid styles passed direct structural falsifiers plus nonempty output, exact style identity, and deterministic replay. Their success supports bounded structural differentiation only. It does not cancel the grid failure or establish empirical realism.",
        "This is NOT fresh-OSM empirical validation. Traffic-functional validation was not completed. Traffic algorithms remain research-incomplete, and runtime-default promotion remains blocked.",
        "PR #17 remains a valid structural implementation/evidence-identity milestone: exact-head push and synthetic-merge CI both passed on tree 622dbe3779. Those checks are software evidence, not a scientific promotion receipt.",
    ):
        story.append(_pdf_paragraph(paragraph, styles["AuditBody"]))

    story.append(_pdf_paragraph("2. Frozen protocol and harness boundary", styles["AuditH1"]))
    for paragraph in (
        "Included evidence is the six seed-503 map pairs, the complete 18-case result, frozen validator, source/sample/harness/remote receipts, claim ledger, and 36-record failure inventory.",
        "The supplied coding harness was applied to finite acceptance, reproduction, and independent verification. The supplied research harness was applied to evidence-before-narrative, claim audit, decision gating, and negative-result preservation. The archives were not installed and did not replace the user's request or repository instructions.",
        "No algorithm, threshold, seed split, baseline, or map was changed. No traffic experiment was rerun. No fresh OSM data was acquired. No push, PR, merge, or publication was performed by this report work unit.",
    ):
        story.append(_pdf_paragraph(paragraph, styles["AuditBody"]))

    story.append(_pdf_paragraph("3. Result matrix", styles["AuditH1"]))
    table_data: list[list[Any]] = [
        [
            _pdf_paragraph("Style", styles["AuditSmall"]),
            _pdf_paragraph("Passed", styles["AuditSmall"]),
            _pdf_paragraph("Seeds", styles["AuditSmall"]),
            _pdf_paragraph("Verdict", styles["AuditSmall"]),
        ]
    ]
    for row in _result_rows(results):
        table_data.append([_pdf_paragraph(cell, styles["AuditSmall"]) for cell in row])
    result_table = Table(table_data, colWidths=[2.7 * inch, 0.75 * inch, 1.65 * inch, 0.9 * inch], repeatRows=1)
    result_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), navy),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 1), (-1, -1), pale_gray),
                ("BACKGROUND", (0, 1), (-1, 1), pale_red),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BFC9CA")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(result_table)
    story.append(Spacer(1, 8))
    story.append(
        _pdf_paragraph(
            "All generic replay and identity checks passed. The three direct grid failures therefore remain dispositive for the aggregate verdict.",
            styles["AuditBody"],
        )
    )

    story.append(_pdf_paragraph("4. Style-level adversarial findings", styles["AuditH1"]))
    for style_id in STYLE_ORDER:
        story.append(_pdf_paragraph(STYLE_LABELS[style_id], styles["AuditH2"]))
        for paragraph in _style_analysis(results, style_id):
            story.append(_pdf_paragraph(paragraph, styles["AuditBody"]))
    story.append(PageBreak())

    story.append(_pdf_paragraph("5. Six-map overview", styles["AuditH1"]))
    contact = MAPS / "heldout_morphology_seed503_contact_sheet.png"
    contact_width = 7.0 * inch
    story.append(Image(str(contact), width=contact_width, height=contact_width * 1098 / 2172))
    story.append(
        _pdf_paragraph(
            "Seed 503 contact sheet. Top: grid, ring-radial, river-constrained. Bottom: polycentric, superblock, curvilinear warped grid. Visuals are navigation, not scientific acceptance.",
            styles["AuditCaption"],
        )
    )
    story.append(PageBreak())

    for index, style_id in enumerate(STYLE_ORDER, start=1):
        cases = [case for case in results["cases"] if case["style_id"] == style_id]
        seed_case = next(case for case in cases if case["seed"] == 503)
        story.append(_pdf_paragraph(f"Map {index}. {STYLE_LABELS[style_id]} / seed 503", styles["AuditH1"]))
        map_path = MAPS / f"map_{style_id}_s503.png"
        image_width = 6.85 * inch
        story.append(Image(str(map_path), width=image_width, height=image_width * 1050 / 1400))
        story.append(
            _pdf_paragraph(
                f"Preview {map_path.name}; SVG authority map_{style_id}_s503.svg. "
                f"Nodes {seed_case['node_count']:,}; roads {seed_case['road_count']:,}; "
                f"case verdict {'PASS' if seed_case['passed'] else 'FAIL'}.",
                styles["AuditCaption"],
            )
        )
        story.append(_pdf_paragraph("Measured interpretation", styles["AuditH2"]))
        for paragraph in _style_analysis(results, style_id):
            story.append(_pdf_paragraph(paragraph, styles["AuditBody"]))
        story.append(_pdf_paragraph("Seed-503 network fingerprint", styles["AuditH2"]))
        story.append(_pdf_paragraph(seed_case["network_fingerprint"], styles["AuditMono"]))
        story.append(PageBreak())

    story.append(_pdf_paragraph("6. Claim-evidence decision table", styles["AuditH1"]))
    claim_data: list[list[Any]] = [
        [
            _pdf_paragraph("ID", styles["AuditSmall"]),
            _pdf_paragraph("Claim", styles["AuditSmall"]),
            _pdf_paragraph("Status", styles["AuditSmall"]),
            _pdf_paragraph("Boundary", styles["AuditSmall"]),
        ]
    ]
    for identifier, claim, status, _evidence, boundary in _claim_rows():
        claim_data.append(
            [
                _pdf_paragraph(identifier, styles["AuditSmall"]),
                _pdf_paragraph(claim, styles["AuditSmall"]),
                _pdf_paragraph(status, styles["AuditSmall"]),
                _pdf_paragraph(boundary, styles["AuditSmall"]),
            ]
        )
    claim_table = Table(
        claim_data,
        colWidths=[0.45 * inch, 3.25 * inch, 1.05 * inch, 2.05 * inch],
        repeatRows=1,
    )
    claim_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), navy),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#BFC9CA")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, pale_gray]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(claim_table)
    story.append(PageBreak())

    counts = Counter(record["current_state"] for record in records)
    story.append(_pdf_paragraph("7. Complete failure inventory", styles["AuditH1"]))
    story.append(
        _pdf_paragraph(
            "This appendix mechanically preserves every scoped item, including repaired paths, open debt, unfavorable measurements, unexecuted scientific gates, and contested interpretation.",
            styles["AuditBody"],
        )
    )
    status_rows = [[_pdf_paragraph("State", styles["AuditSmall"]), _pdf_paragraph("Count", styles["AuditSmall"])]]
    for state in ("CLOSED", "PARTIALLY_CLOSED", "OPEN", "NEGATIVE_RESULT", "NOT_EVALUATED", "CONTESTED"):
        status_rows.append([_pdf_paragraph(state, styles["AuditSmall"]), _pdf_paragraph(str(counts[state]), styles["AuditSmall"])])
    status_table = Table(status_rows, colWidths=[2.0 * inch, 0.7 * inch])
    status_table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, gray), ("BACKGROUND", (0, 0), (-1, 0), pale_blue)]))
    story.append(status_table)
    story.append(Spacer(1, 10))
    for record in records:
        state_color = green if record["current_state"] == "CLOSED" else amber
        if record["current_state"] in {"NEGATIVE_RESULT", "CONTESTED"}:
            state_color = red
        heading = Table(
            [[
                _pdf_paragraph(f"{record['id']}  {record['title']}", styles["AuditH2"]),
                _pdf_paragraph(record["current_state"], styles["AuditSmall"]),
            ]],
            colWidths=[5.55 * inch, 1.2 * inch],
        )
        heading.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), pale_gray),
                    ("BOX", (0, 0), (-1, -1), 0.7, state_color),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        details = [
            heading,
            _pdf_paragraph(f"Domain / original severity: {record['domain']} / {record['original_severity']}", styles["AuditSmall"]),
            _pdf_paragraph(f"Impact: {record['impact']}", styles["AuditSmall"]),
            _pdf_paragraph(f"Evidence: {record['evidence']}", styles["AuditSmall"]),
            _pdf_paragraph(f"Resolution/current handling: {record['resolution']}", styles["AuditSmall"]),
            _pdf_paragraph(f"Remaining gate: {record['remaining_gate']}", styles["AuditSmall"]),
            _pdf_paragraph(f"Claim effect: {record['claim_effect']}", styles["AuditSmall"]),
            Spacer(1, 6),
        ]
        story.append(KeepTogether(details))

    story.append(PageBreak())
    story.append(_pdf_paragraph("8. Traffic-functional boundary and next protocol", styles["AuditH1"]))
    for paragraph in (
        "The prior bounded traffic-functional attempt did not produce an admissible result artifact. The only durable witness is a pytest lastfailed entry for the development nonvacuous-and-directional probe. It is recorded as MF-036 NEGATIVE_RESULT, not silently skipped and not promoted into an algorithm diagnosis.",
        "The user explicitly directs future work toward functionality rather than completeness because the traffic algorithms require additional change and research. A future versioned protocol should test nonvacuity, explicit units, conservation, immutable state transition, deterministic replay, cache invalidation, baseline fallback, directional response, and bounded performance.",
        "Even a passing future functional matrix would not establish universal correctness, calibration, city realism, operational safety, or runtime-default readiness without separate evidence.",
    ):
        story.append(_pdf_paragraph(paragraph, styles["AuditBody"]))

    story.append(_pdf_paragraph("9. Reproduction and adversarial attack surface", styles["AuditH1"]))
    for paragraph in (
        "The evidence manifest binds every package file except itself. The checker enforces exact directory membership, source/tree/fingerprint identity, the 18-case partition, all 36 failure identifiers and fields, map digest/dimension contracts, PDF-copy identity, link presence, and claim-ceiling phrases.",
        "The most valuable independent attack is the grid classifier construct: reproduce the raw geometry without changing the held-out verdict, decompose semantic carrier labels from coordinate orientation, and predeclare an independent block/orientation witness on new seeds. Do not tune the frozen criterion after observing these cases.",
        "A second high-value attack is external morphology: add licensed, frozen, leakage-controlled OSM extracts and metrics that defeat the known null operator. The current v4 table does not score scalable_synthetic_v2 and cannot be borrowed as its empirical validation.",
    ):
        story.append(_pdf_paragraph(paragraph, styles["AuditBody"]))

    story.append(_pdf_paragraph("10. Final gate", styles["AuditH1"]))
    final_data = [
        ["Surface", "Decision"],
        ["Report/evidence package", "Admissible only after checker, PDF QA, and independent review"],
        ["Held-out structural morphology", "FAIL - 15/18"],
        ["Fresh-OSM empirical morphology", "NOT EVALUATED / BLOCKED"],
        ["Traffic-functional validity", "NOT COMPLETED / NEGATIVE RESULT"],
        ["Traffic algorithm completeness", "NOT CLAIMED"],
        ["Runtime-default promotion", "BLOCKED"],
    ]
    final_table = Table(
        [[_pdf_paragraph(cell, styles["AuditSmall"]) for cell in row] for row in final_data],
        colWidths=[2.7 * inch, 4.05 * inch],
        repeatRows=1,
    )
    final_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), navy),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, gray),
                ("BACKGROUND", (0, 1), (-1, -1), pale_red),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(final_table)
    if has_review:
        review_text = (PACKAGE / "INDEPENDENT_REVIEW.md").read_text(encoding="utf-8")
        story.append(Spacer(1, 12))
        story.append(_pdf_paragraph("Independent review receipt", styles["AuditH2"]))
        story.append(
            _pdf_paragraph(
                "A separate read-only review is bound as INDEPENDENT_REVIEW.md. "
                "Its extracted verdict text follows.",
                styles["AuditBody"],
            )
        )
        for line in review_text.splitlines():
            stripped = line.strip().lstrip("#").strip()
            if stripped:
                story.append(_pdf_paragraph(stripped, styles["AuditSmall"]))

    doc.build(
        story,
        onFirstPage=on_page,
        onLaterPages=on_page,
        canvasmaker=InvariantCanvas,
    )


def _build_manifest() -> dict[str, Any]:
    files = []
    for path in sorted(PACKAGE.rglob("*")):
        if not path.is_file() or path.name == "EVIDENCE_MANIFEST.json":
            continue
        files.append(
            {
                "path": path.relative_to(PACKAGE).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    return {
        "schema_version": "metroflow_morphology_adversarial_audit_v1",
        "generated_on": "2026-08-23",
        "source": {"commit": SOURCE_COMMIT, "tree": SOURCE_TREE},
        "heldout_result": {
            "verdict": "FAIL",
            "passed": 15,
            "attempted": 18,
            "scientific_fingerprint": SCIENTIFIC_FINGERPRINT,
        },
        "claim_ceiling": "SEED_HELDOUT_STRUCTURAL_MORPHOLOGY_ONLY",
        "files": files,
    }


def build_package() -> None:
    results = _read_json(EVIDENCE / "heldout_morphology_results.json")
    records = failure_inventory()
    has_review = (PACKAGE / "INDEPENDENT_REVIEW.md").is_file()
    for filename, payload in _receipt_payloads().items():
        _write_json(EVIDENCE / filename, payload)
    _write_json(
        PACKAGE / "FAILURE_INVENTORY.json",
        {
            "schema_version": "metroflow_morphology_failure_inventory_v1",
            "scope_through": "2026-08-23",
            "failures": records,
        },
    )
    _write_text(PACKAGE / "FAILURE_INVENTORY.md", _render_failure_markdown(records))
    _write_text(PACKAGE / "CLAIM_EVIDENCE_LEDGER.md", _render_claim_ledger())
    _write_text(PACKAGE / "REPORT.md", _render_report(results, records, has_review))
    _write_text(PACKAGE / "AUDITOR_README.md", _render_auditor_readme(has_review))
    _build_pdf(PACKAGE / PDF_NAME, results, records, has_review)
    PDF_COPY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PACKAGE / PDF_NAME, PDF_COPY)
    _write_json(PACKAGE / "EVIDENCE_MANIFEST.json", _build_manifest())


def _expected_map_files() -> set[str]:
    files = {"heldout_morphology_seed503_contact_sheet.png"}
    for style_id in STYLE_ORDER:
        files.add(f"map_{style_id}_s503.png")
        files.add(f"map_{style_id}_s503.svg")
    return files


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def check_package(*, allow_review_missing: bool = False) -> None:
    expected_root = set(ROOT_FILES)
    if allow_review_missing:
        expected_root.discard("INDEPENDENT_REVIEW.md")
    actual_root = {path.name for path in PACKAGE.iterdir() if path.is_file()}
    _require(actual_root == expected_root, f"root membership mismatch: {actual_root ^ expected_root}")
    actual_dirs = {path.name for path in PACKAGE.iterdir() if path.is_dir()}
    _require(actual_dirs == {"evidence", "maps"}, f"directory membership mismatch: {actual_dirs}")
    _require(
        {path.name for path in EVIDENCE.iterdir() if path.is_file()} == EVIDENCE_FILES,
        "evidence membership mismatch",
    )
    _require(
        {path.name for path in MAPS.iterdir() if path.is_file()} == _expected_map_files(),
        "map membership mismatch",
    )

    results = _read_json(EVIDENCE / "heldout_morphology_results.json")
    _require(results["verdict"] == "FAIL", "held-out verdict drift")
    _require(
        results["attempt_inventory"]
        == {"attempted": 18, "expected": 18, "scored": 18, "skipped": 0},
        "held-out attempt partition drift",
    )
    _require(results["scientific_fingerprint"] == SCIENTIFIC_FINGERPRINT, "scientific fingerprint drift")
    _require(len(results["cases"]) == 18, "expected 18 result cases")
    _require(sum(bool(case["passed"]) for case in results["cases"]) == 15, "expected 15 passing cases")
    failed = {(case["style_id"], case["seed"]) for case in results["cases"] if not case["passed"]}
    _require(failed == {("grid_core", 503), ("grid_core", 701), ("grid_core", 907)}, "failed-case set drift")
    _require(all(case["checks"]["deterministic_replay"] for case in results["cases"]), "replay check drift")

    source = _read_json(EVIDENCE / "source_receipt.json")
    _require(source["commit"] == SOURCE_COMMIT and source["tree"] == SOURCE_TREE, "source receipt drift")
    _require(_sha256(EVIDENCE / "heldout_morphology_results.json") == source["heldout_evidence"]["results_sha256"], "result hash drift")
    _require(_sha256(EVIDENCE / "sample_manifest.json") == source["heldout_evidence"]["sample_manifest_sha256"], "sample-manifest hash drift")
    _require(_sha256(EVIDENCE / "heldout_morphology_validator.py") == source["heldout_evidence"]["validator_sha256"], "validator hash drift")

    sample = _read_json(EVIDENCE / "sample_manifest.json")
    _require(sample["repository_commit"] == SOURCE_COMMIT, "sample source commit drift")
    _require(sample["repository_tree"] == SOURCE_TREE, "sample source tree drift")
    _require(sample["sample_seed"] == 503, "sample seed drift")
    entries = sample["entries"]
    _require(len(entries) == 6, "expected six sample records")
    _require({entry["style_id"] for entry in entries} == set(STYLE_ORDER), "sample style inventory drift")
    for entry in entries:
        png_path = MAPS / entry["png_file"]
        svg_path = MAPS / entry["svg_file"]
        _require(_sha256(png_path) == entry["png_sha256"], f"PNG digest drift: {png_path.name}")
        _require(_sha256(svg_path) == entry["svg_sha256"], f"SVG digest drift: {svg_path.name}")
        _require(_png_dimensions(png_path) == (1400, 1050), f"PNG dimension drift: {png_path.name}")
    contact = MAPS / sample["contact_sheet_file"]
    _require(_sha256(contact) == sample["contact_sheet_sha256"], "contact sheet digest drift")
    _require(_png_dimensions(contact) == (2172, 1098), "contact sheet dimension drift")

    inventory = _read_json(PACKAGE / "FAILURE_INVENTORY.json")
    records = inventory["failures"]
    _require(inventory["schema_version"] == "metroflow_morphology_failure_inventory_v1", "failure schema drift")
    _require({record["id"] for record in records} == {f"MF-{index:03d}" for index in range(1, 37)}, "failure IDs incomplete")
    _require(len(records) == 36, "failure records not unique")
    expected_fields = {
        "claim_effect",
        "current_state",
        "domain",
        "evidence",
        "first_observed",
        "id",
        "impact",
        "original_severity",
        "remaining_gate",
        "resolution",
        "title",
    }
    _require(all(set(record) == expected_fields for record in records), "failure field drift")

    report = (PACKAGE / "REPORT.md").read_text(encoding="utf-8")
    for phrase in (
        "15/18",
        "seed-held-out structural morphology",
        "NOT fresh-OSM empirical validation",
        "runtime-default promotion remains blocked",
        "traffic-functional validation was not completed",
        "MF-001",
        "MF-036",
    ):
        _require(phrase in report, f"missing claim-boundary phrase: {phrase}")
    for style_id in STYLE_ORDER:
        _require(f"maps/map_{style_id}_s503.png" in report, f"missing map link: {style_id}")
    for path in PACKAGE.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for marker in ("[TODO]", "TBD_CONTENT", "PLACEHOLDER_TEXT", "PENDING_REVIEW"):
            _require(marker not in text, f"placeholder marker in {path.name}: {marker}")

    manifest = _read_json(PACKAGE / "EVIDENCE_MANIFEST.json")
    _require(manifest["schema_version"] == "metroflow_morphology_adversarial_audit_v1", "manifest schema drift")
    _require(manifest["source"] == {"commit": SOURCE_COMMIT, "tree": SOURCE_TREE}, "manifest source drift")
    _require(manifest["heldout_result"]["scientific_fingerprint"] == SCIENTIFIC_FINGERPRINT, "manifest scientific fingerprint drift")
    expected_paths = {
        path.relative_to(PACKAGE).as_posix()
        for path in PACKAGE.rglob("*")
        if path.is_file() and path.name != "EVIDENCE_MANIFEST.json"
    }
    manifest_records = manifest["files"]
    _require(len(manifest_records) == len({record["path"] for record in manifest_records}), "duplicate manifest path")
    _require({record["path"] for record in manifest_records} == expected_paths, "manifest file inventory drift")
    for record in manifest_records:
        path = PACKAGE / record["path"]
        _require(record["bytes"] == path.stat().st_size, f"manifest size drift: {record['path']}")
        _require(record["sha256"] == _sha256(path), f"manifest digest drift: {record['path']}")

    package_pdf = PACKAGE / PDF_NAME
    _require(package_pdf.read_bytes().startswith(b"%PDF-"), "invalid PDF header")
    _require(PDF_COPY.is_file() and PDF_COPY.read_bytes() == package_pdf.read_bytes(), "PDF copies differ")
    extracted = subprocess.run(
        ["pdftotext", str(package_pdf), "-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    for phrase in ("FAIL - 15/18", "MF-001", "MF-036", "Runtime-default promotion"):
        _require(phrase in extracted, f"PDF text missing: {phrase}")
    if not allow_review_missing:
        review = (PACKAGE / "INDEPENDENT_REVIEW.md").read_text(encoding="utf-8")
        _require("P0: 0" in review and "P1: 0" in review, "review severity gate failed")
        _require("VERDICT: PASS" in review, "independent review did not pass")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--build", action="store_true", help="build the report package")
    mode.add_argument("--check", action="store_true", help="verify the report package")
    parser.add_argument(
        "--allow-review-missing",
        action="store_true",
        help="permit the frozen pre-review candidate to omit its later review receipt",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.build:
        build_package()
        print(f"built {PACKAGE}")
        return 0
    check_package(allow_review_missing=args.allow_review_missing)
    print(f"verified {PACKAGE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
