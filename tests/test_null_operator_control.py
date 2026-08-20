"""Can the morphology envelope be passed by an operator that knows nothing?

The seven-metric envelope orders the generator arms: `growth_fabric_v1` 30/30,
`realistic_synthetic_v1` 0/30. Every argument about which generator to build
rests on that ordering meaning something.

This is the control that tests whether it does. The operator here deletes a
seeded fraction of streets and nothing else. It reads no terrain, no urban form,
no land use, no road hierarchy, no district structure -- it cannot, because it is
handed only a graph. It adds exactly zero information about cities.

If deleting streets at random moves an arm from failing to passing, then a
passing score is not evidence that a generator learned anything about cities,
and the ordering it produces cannot authorize a rebuild. The repo already owns
one false positive (`sidecar_local_fabric/superblock_mixed/17`, which passes 7/7
and is visibly not a city); this asks whether that was a single unlucky map or a
property of the instrument.

Connectivity is preserved on purpose. An operator that passes by shattering the
network into fragments would be uninteresting -- everyone already knows a
disconnected graph is not a city. The question is whether the envelope can be
satisfied while the graph stays whole.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess

import pytest


_REPO_ROOT = Path(__file__).parents[1]
_HISTORICAL_SOURCE_PATHS = {
    "src/metroflow/benchmarks/null_operator_control.py",
    "src/metroflow/city/morphology_control_table.py",
    "src/metroflow/city/morphology_metrics.py",
}
_HISTORICAL_BASE_COMMIT = "3c6a5c794ca5e06878ecb50eb935435208b8f2be"
_SOURCE_INTRODUCTION_COMMIT = "e9e4dfda1898bd0af576511e04fa4b6e92e2cede"
_ARTIFACT_INTRODUCTION_COMMIT = "5e1bb573695a2d58eb04e6689e59b6e2d98f36b7"
_NULL_OPERATOR_SOURCE = "src/metroflow/benchmarks/null_operator_control.py"
_NULL_OPERATOR_ARTIFACT = (
    "artifacts/runtime_spine_review/morphology-null-operator-control-20260808.json"
)
_NULL_OPERATOR_MANIFEST = (
    "artifacts/runtime_spine_review/"
    "morphology-null-operator-control-20260808.manifest.json"
)


def _git_bytes(*arguments: str) -> bytes:
    return subprocess.check_output(("git", *arguments), cwd=_REPO_ROOT)


def _git_returncode(*arguments: str) -> int:
    return subprocess.run(
        ("git", *arguments),
        cwd=_REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode


def _assert_historical_source_provenance(
    artifact: dict[str, object],
    manifest: dict[str, object],
) -> None:
    """Validate the historical source record used by the sealed control."""
    provenance = artifact["provenance"]
    assert isinstance(provenance, dict)
    source_digests = provenance["sources"]
    assert isinstance(source_digests, dict)
    assert set(source_digests) == _HISTORICAL_SOURCE_PATHS
    assert provenance["commit"] == _HISTORICAL_BASE_COMMIT
    assert manifest["commit"] == _HISTORICAL_BASE_COMMIT
    assert all(
        isinstance(recorded_digest, str)
        and re.fullmatch(r"[0-9a-f]{64}", recorded_digest)
        for recorded_digest in source_digests.values()
    )

    for commit in (
        _HISTORICAL_BASE_COMMIT,
        _SOURCE_INTRODUCTION_COMMIT,
        _ARTIFACT_INTRODUCTION_COMMIT,
    ):
        assert _git_bytes("cat-file", "-t", commit) == b"commit\n"
        assert _git_returncode("merge-base", "--is-ancestor", commit, "HEAD") == 0

    assert _git_returncode(
        "cat-file", "-e", f"{_HISTORICAL_BASE_COMMIT}:{_NULL_OPERATOR_SOURCE}"
    ) != 0, "the recorded commit is the experiment base, not a source snapshot"
    assert _git_returncode(
        "merge-base",
        "--is-ancestor",
        _SOURCE_INTRODUCTION_COMMIT,
        _ARTIFACT_INTRODUCTION_COMMIT,
    ) == 0

    source_additions = set(
        _git_bytes(
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            "--diff-filter=A",
            _SOURCE_INTRODUCTION_COMMIT,
        )
        .decode("utf-8")
        .splitlines()
    )
    assert _NULL_OPERATOR_SOURCE in source_additions
    artifact_additions = set(
        _git_bytes(
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            "--diff-filter=A",
            _ARTIFACT_INTRODUCTION_COMMIT,
        )
        .decode("utf-8")
        .splitlines()
    )
    assert {_NULL_OPERATOR_ARTIFACT, _NULL_OPERATOR_MANIFEST} <= artifact_additions

    for source_path, recorded_digest in source_digests.items():
        for source_commit in (
            _SOURCE_INTRODUCTION_COMMIT,
            _ARTIFACT_INTRODUCTION_COMMIT,
        ):
            historical_bytes = _git_bytes("show", f"{source_commit}:{source_path}")
            assert hashlib.sha256(historical_bytes).hexdigest() == recorded_digest

    artifact_path = _REPO_ROOT / _NULL_OPERATOR_ARTIFACT
    manifest_path = _REPO_ROOT / _NULL_OPERATOR_MANIFEST
    assert _git_bytes(
        "show", f"{_ARTIFACT_INTRODUCTION_COMMIT}:{_NULL_OPERATOR_ARTIFACT}"
    ) == artifact_path.read_bytes()
    assert _git_bytes(
        "show", f"{_ARTIFACT_INTRODUCTION_COMMIT}:{_NULL_OPERATOR_MANIFEST}"
    ) == manifest_path.read_bytes()


def _thinned(style_id: str = "grid_core", seed: int = 17, *, p: float):
    from metroflow.benchmarks.null_operator_control import thin_topology
    from metroflow.benchmarks.morphology_control_table import build_arm_topology

    base = build_arm_topology(arm="realistic_synthetic_v1", style_id=style_id, seed=seed)
    return base, thin_topology(base, removal_fraction=p, seed=seed)


def test_the_operator_removes_streets_and_keeps_the_network_whole() -> None:
    """Otherwise it is a disconnection test, which proves nothing interesting."""

    from metroflow.city.connectivity import analyze_weak_connectivity

    base, thinned = _thinned(p=0.35)

    assert len(thinned.links) < len(base.links), "nothing was removed"
    assert len(thinned.nodes) == len(base.nodes), "nodes must survive; only streets go"

    before = analyze_weak_connectivity(nodes=base.nodes, links=base.links)
    after = analyze_weak_connectivity(nodes=thinned.nodes, links=thinned.links)
    assert after.component_count == before.component_count, (
        f"thinning split the network: {before.component_count} -> {after.component_count}"
    )


def test_the_operator_is_deterministic() -> None:
    """A control whose result depends on the run cannot settle anything."""

    _, first = _thinned(p=0.35)
    _, second = _thinned(p=0.35)

    assert [link.link_id for link in first.links] == [link.link_id for link in second.links]


def test_the_operator_reads_nothing_but_the_graph() -> None:
    """Locks the claim that makes this a control rather than a generator.

    If `thin_topology` ever imports terrain, urban form, land use or morphology,
    it stops being information-free and this whole file stops being evidence.
    """

    import ast
    from pathlib import Path

    # The imports, not the prose. A first version of this test grepped the raw
    # text and failed on the module's own docstring, which names the things it
    # promises not to read. What "information-free" means is what the code can
    # reach, and that is the import list.
    source = Path("src/metroflow/benchmarks/null_operator_control.py").read_text(
        encoding="utf-8"
    )
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    forbidden = ("terrain", "urban_form", "morphology", "land_use", "district", "block")
    offending = sorted(
        name for name in imported if any(word in name for word in forbidden)
    )
    assert not offending, (
        f"the null operator imports {offending}; it is no longer information-free"
    )


def test_the_historical_null_operator_artifact_preserves_source_provenance() -> None:
    """Historical evidence stays sealed without claiming to describe current code."""

    def assert_summary_matches_rows(rows: list[dict[str, object]], summary: object) -> None:
        fractions = sorted({float(row["requested_fraction"]) for row in rows})
        derived = {
            f"p={fraction}": {
                "passed": sum(
                    bool(row["passed"])
                    for row in rows
                    if float(row["requested_fraction"]) == fraction
                ),
                "total": sum(
                    1
                    for row in rows
                    if float(row["requested_fraction"]) == fraction
                ),
            }
            for fraction in fractions
        }
        assert derived == summary

    artifact_dir = _REPO_ROOT / "artifacts/runtime_spine_review"
    artifact_path = artifact_dir / "morphology-null-operator-control-20260808.json"
    manifest_path = artifact_dir / "morphology-null-operator-control-20260808.manifest.json"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact_bytes = artifact_path.read_bytes()
    artifact = json.loads(artifact_bytes)

    assert manifest["files"] == {
        artifact_path.name: hashlib.sha256(artifact_bytes).hexdigest()
    }

    rows = artifact["rows"]
    assert len(rows) == 6 * 5 * 5
    assert {row["style_id"] for row in rows} == {
        "ring_radial",
        "grid_core",
        "polycentric_tod",
        "river_constrained",
        "superblock_mixed",
        "organic",
    }
    assert {row["seed"] for row in rows} == {17, 29, 41, 44, 53}
    assert {row["requested_fraction"] for row in rows} == {0.0, 0.2, 0.35, 0.5, 0.6}
    assert len({(row["style_id"], row["seed"], row["requested_fraction"]) for row in rows}) == len(rows)
    assert_summary_matches_rows(rows, artifact["summary"])

    mutated_summary = {
        key: dict(value) for key, value in artifact["summary"].items()
    }
    mutated_summary["p=0.35"]["passed"] = 29
    with pytest.raises(AssertionError):
        assert_summary_matches_rows(rows, mutated_summary)

    _assert_historical_source_provenance(artifact, manifest)


def test_historical_source_provenance_rejects_a_forged_digest() -> None:
    """A well-shaped digest that names no historical blob must fail closed."""
    artifact_dir = _REPO_ROOT / "artifacts/runtime_spine_review"
    artifact = json.loads(
        (artifact_dir / "morphology-null-operator-control-20260808.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads(
        (artifact_dir / "morphology-null-operator-control-20260808.manifest.json").read_text(
            encoding="utf-8"
        )
    )
    artifact["provenance"]["sources"][
        "src/metroflow/benchmarks/null_operator_control.py"
    ] = "0" * 64

    with pytest.raises(AssertionError):
        _assert_historical_source_provenance(artifact, manifest)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "MEASURED 2026-08-08 over the pinned 6 styles x 5 seeds: p=0.00 -> 0/30, "
        "p=0.20 -> 0/30, p=0.35 -> 30/30, p=0.50 -> 26/30, p=0.60 -> 0/30. "
        "`realistic_synthetic_v1` fails mean_node_degree and dead_end_share on "
        "30/30; deleting 35% of its streets at random, preserving connectivity, "
        "scores 30/30 -- the same score growth_fabric_v1 earns. The band opens "
        "between p=0.2 (deg 4.56823, dead 0.02930) and p=0.35 (3.88152, 0.11234) and "
        "closes by p=0.6 when the graph is too sparse. Recorded in "
        "artifacts/runtime_spine_review/morphology-null-operator-control-20260808.json. "
        "This xfail is the finding, not a defect awaiting a fix: it must be "
        "removed only when the envelope stops being used to order arms, or when "
        "an instrument that rejects this control replaces it (stage S3)."
    ),
)
def test_the_envelope_rejects_the_thinned_network() -> None:
    """THE EXPERIMENT. Its failure is the finding, not a bug to fix.

    A generator that passes the envelope is said to have produced a realistic
    street network. Random street deletion produces nothing of the kind. If the
    envelope accepts it anyway, the envelope is not measuring what its use
    implies, and no arm ordering derived from it can authorize a rebuild.

    Kept as a live strict xfail rather than deleted or inverted. Inverting it
    would assert that the envelope SHOULD accept random deletion, which is not a
    property anyone wants to preserve; deleting it would lose the control. Strict
    means that if the envelope ever starts rejecting this, the suite says so.
    """

    from metroflow.city.morphology_control_table import score_street_morphology

    passes = []
    for style_id in ("grid_core", "polycentric_tod", "river_constrained", "superblock_mixed"):
        for p in (0.35, 0.45):
            _, thinned = _thinned(style_id=style_id, p=p)
            score = score_street_morphology(thinned, arm="null_thinned_v1", case=f"{style_id}/{p}")
            passes.append((style_id, p, score.passed, score.failed_metrics))

    accepted = [item for item in passes if item[2]]
    assert not accepted, (
        "the envelope accepted a randomly thinned network in "
        f"{len(accepted)}/{len(passes)} cases: {accepted}"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__]))
