"""Report geometry-vs-topology consistency alongside the seven Boeing metrics.

The morphology envelope accepted a grown network that was missing 24.4% of its
edges, because none of its seven metrics can see whether streets that touch are
actually connected. Two counters can: proper crossings, and vertices that sit on
another street's interior with no node there.

They land here as REPORTED diagnostics, not as a gate. Nobody yet knows what
these numbers look like after PR-B, and choosing a threshold before the
measurement exists is the mistake that froze the PR53 acceptance criteria before
an algorithm existed. Report first, gate later.

Because they are diagnostics, they must stay out of the artifact fingerprint —
otherwise adding a diagnostic silently invalidates every pinned artifact, and
the pinned control table stops round-tripping.
"""

from __future__ import annotations


def _score(arm: str = "growth_fabric_v1"):
    from metroflow.benchmarks.morphology_control_table import build_arm_topology
    from metroflow.city.morphology_control_table import score_street_morphology

    topology = build_arm_topology(arm=arm, style_id="grid_core", seed=17)
    return score_street_morphology(topology, arm=arm, case="grid_core/17")


def test_a_score_reports_geometry_topology_consistency_counts() -> None:
    """The grown fabric's touching-but-unconnected streets must be countable."""

    diagnostics = _score().topology_diagnostics()

    assert diagnostics["proper_crossing_count"] == 6909
    assert diagnostics["unregistered_touch_count"] == 6261


def test_the_osm_control_shows_what_a_real_city_scores() -> None:
    """Zero on both counters is the target, and real data already achieves it."""

    from pathlib import Path

    from metroflow.benchmarks.morphology_control_table import build_osm_topology
    from metroflow.city.morphology_control_table import score_street_morphology

    topology = build_osm_topology(
        Path(__file__).parents[1] / "artifacts" / "osm_control" / "chicago.osm"
    )
    diagnostics = score_street_morphology(
        topology, arm="osm", case="chicago.osm"
    ).topology_diagnostics()

    assert diagnostics["proper_crossing_count"] == 0
    assert diagnostics["unregistered_touch_count"] == 0


def test_diagnostics_are_reported_but_never_enter_the_fingerprint() -> None:
    """Adding a diagnostic must not invalidate a pinned artifact."""

    from metroflow.city.morphology_control_table import build_morphology_control_table

    table = build_morphology_control_table([_score()])
    payload = table.as_dict()

    assert "topology_diagnostics" in payload
    assert payload["topology_diagnostics"]["growth_fabric_v1:grid_core/17"] == {
        # Which definition produced the score travels with the score. That is
        # the whole lesson of the two-measurement-paths defect.
        "measurement_spec": "BOEING_2019_HO",
        "proper_crossing_count": 6909,
        "unregistered_touch_count": 6261,
    }
    # The per-score payload the fingerprint hashes must not carry them.
    assert "proper_crossing_count" not in payload["scores"][0]
    assert "unregistered_touch_count" not in payload["scores"][0]


def test_the_pinned_control_table_fingerprint_is_unchanged() -> None:
    """The whole point of 'reported only': the frozen artifact still matches."""

    import json
    from pathlib import Path

    artifact = (
        Path(__file__).parents[1]
        / "artifacts"
        / "runtime_spine_review"
        / "morphology-control-table-20260807.json"
    )
    stored = json.loads(artifact.read_text(encoding="utf-8"))

    from metroflow.city.morphology_control_table import (
        MorphologyControlTable,
        MorphologyScore,
        build_empirical_metric_envelopes,
    )
    from metroflow.city.morphology_control_table import (
        EMPIRICAL_MORPHOLOGY_METRICS,
    )

    rebuilt = MorphologyControlTable(
        scores=tuple(
            MorphologyScore(
                arm=item["arm"],
                case=item["case"],
                metrics=item["metrics"],
                failed_metrics=tuple(item["failed_metrics"]),
                simplified=item["simplified"],
                node_count=item["node_count"],
                physical_segment_count=item["physical_segment_count"],
            )
            for item in stored["scores"]
        ),
        envelopes=tuple(
            build_empirical_metric_envelopes()[name]
            for name in EMPIRICAL_MORPHOLOGY_METRICS
        ),
    )

    assert rebuilt.fingerprint == stored["fingerprint"]
