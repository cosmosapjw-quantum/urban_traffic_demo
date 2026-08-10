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

import pytest


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
