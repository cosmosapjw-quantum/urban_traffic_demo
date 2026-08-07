"""`BOEING_2019_HO` must agree with the OSMnx it claims parity with.

The strongest statements here are the ones with no tolerance at all: the number
of dead-end nodes OSMnx finds and the number this code finds are the same
integer on every extract. Classification is exact; only the node population
differs slightly, and that difference is bounded and attributed rather than
absorbed into a percentage.

The share-level tolerances are upper bounds on a residual that has been traced
to a known cause, not a certificate of equivalence. They exist to catch
regression. Where a residual is unexplained it is named as unexplained.

Requires the `oracle` extra. Absent OSMnx these tests skip visibly; they never
fall back to some other measurement and report success.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

pytest.importorskip("osmnx", reason="oracle extra not installed")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GOLDEN = json.loads(
    (_REPO_ROOT / "tests" / "data" / "osmnx_morphology_oracle.json").read_text(
        encoding="utf-8"
    )
)

# The five extracts `osm_import` can read. paris and prague are rejected by our
# lane parser, not by OSMnx, and are covered in tests/test_osmnx_oracle.py.
IMPORTABLE = ("barcelona", "charlotte", "chicago", "seoul", "tokyo")

# Upper bounds on the residual measured after the definitional defects were
# fixed. Before the fix, chicago's entropy was 11.28% out; it is now 0.78%.
# Every bound below is above the worst observed value for that metric, and the
# cause of the residual is stated in the test that asserts it.
_SHAPE_TOLERANCE_PCT = {
    "orientation_entropy": 1.0,  # worst observed 0.85 (barcelona)
    "orientation_order": 2.5,  # worst observed 2.33; phi is quadratic in H, so it amplifies
    "median_segment_length_m": 1.0,  # worst observed 0.73
    "circuity": 2.0,  # worst observed 1.86 (chicago); see the self-loop test
    "mean_node_degree": 1.5,  # worst observed 1.20
}


def _ours(city: str):
    from metroflow.benchmarks.morphology_control_table import build_osm_topology
    from metroflow.city.morphology_metrics import (
        MeasurementSpec,
        compute_street_network_morphometrics,
    )

    topology = build_osm_topology(_REPO_ROOT / "artifacts" / "osm_control" / f"{city}.osm")
    return compute_street_network_morphometrics(topology, spec=MeasurementSpec.BOEING_2019_HO)


def _simplified_node_count(city: str) -> int:
    from metroflow.benchmarks.morphology_control_table import build_osm_topology
    from metroflow.city.morphology_metrics import _simplified_segments

    topology = build_osm_topology(_REPO_ROOT / "artifacts" / "osm_control" / f"{city}.osm")
    _segments, degree_by_node_id, _dropped = _simplified_segments(
        topology, topology.road_geometry
    )
    return len(degree_by_node_id)


# --- exact agreement, no tolerance -----------------------------------------


@pytest.mark.parametrize("city", IMPORTABLE)
def test_dead_end_nodes_are_classified_identically_to_osmnx(city: str) -> None:
    """Same integer, every extract. This is the parity claim that has teeth.

    `dead_end_share` differs from OSMnx by up to 3.24%, and the entire difference
    is the denominator: our simplified graph has slightly fewer nodes. The
    numerator -- how many nodes are dead ends -- is identical.
    """

    oracle = _GOLDEN["cities"][f"{city}.osm"]

    osmnx_count = oracle["metrics"]["dead_end_share"] * oracle["graph"]["node_count"]
    our_count = _ours(city).dead_end_share * _simplified_node_count(city)

    assert round(our_count) == round(osmnx_count)


@pytest.mark.parametrize("city", IMPORTABLE)
def test_four_way_nodes_agree_with_osmnx_to_within_one_node(city: str) -> None:
    """Exact on barcelona, charlotte and tokyo; one node out on chicago and seoul.

    Those two sit on the same graph difference as the node counts below, not on
    a disagreement about what a four-way intersection is.
    """

    oracle = _GOLDEN["cities"][f"{city}.osm"]

    osmnx_count = oracle["metrics"]["four_way_share"] * oracle["graph"]["node_count"]
    our_count = _ours(city).four_way_share * _simplified_node_count(city)

    assert abs(round(our_count) - round(osmnx_count)) <= 1


# --- the residual, bounded and attributed ----------------------------------


@pytest.mark.parametrize("city", IMPORTABLE)
def test_our_simplified_graph_is_within_a_few_nodes_of_osmnx(city: str) -> None:
    """The one real residual: `osm_import` builds a slightly smaller graph.

    Barcelona 463 nodes against OSMnx's 478, chicago 424 against 431. Nodes lost
    equals edges lost in every case, so this is whole small components going
    missing, not vertices being merged. It is an importer difference, not a
    metric difference -- the same files under the same contraction -- and it is
    bounded here so it cannot grow unnoticed.
    """

    osmnx_nodes = _GOLDEN["cities"][f"{city}.osm"]["graph"]["node_count"]

    ratio = osmnx_nodes / _simplified_node_count(city)

    assert 1.0 <= ratio <= 1.035, f"{city}: node-count ratio {ratio:.4f} drifted"


@pytest.mark.parametrize("city", IMPORTABLE)
@pytest.mark.parametrize("metric", sorted(_SHAPE_TOLERANCE_PCT))
def test_shape_metrics_track_osmnx(city: str, metric: str) -> None:
    reference = _GOLDEN["cities"][f"{city}.osm"]["metrics"][metric]

    measured = getattr(_ours(city), metric)
    deviation = abs(measured - reference) / abs(reference) * 100.0

    assert deviation <= _SHAPE_TOLERANCE_PCT[metric], (
        f"{city}.{metric}: {deviation:.2f}% from OSMnx "
        f"({measured:.4f} vs {reference:.4f})"
    )


def test_the_entropy_defect_is_actually_gone() -> None:
    """Chicago was the worst case at 11.28%; pin that it stays fixed.

    The old code fed one bearing per member edge of a contracted chain into the
    histogram while taking circuity from the chain's chord. Chicago is the most
    gridded extract, so it had the most chain structure to get wrong.
    """

    reference = _GOLDEN["cities"]["chicago.osm"]["metrics"]["orientation_entropy"]

    deviation = abs(_ours("chicago").orientation_entropy - reference) / reference * 100.0

    assert deviation < 1.0, f"chicago entropy is {deviation:.2f}% from OSMnx"


def test_our_contraction_still_manufactures_a_self_loop_osmnx_does_not() -> None:
    """An unexplained residual, recorded as unexplained rather than tolerated.

    Barcelona's simplified graph gains one 508 m self-loop that OSMnx's does not
    have (its `self_loop_proportion` is 0.0000). A self-loop adds length to the
    circuity numerator with a zero chord, which is part of barcelona's 1.53%
    circuity gap. This test states the defect exists and bounds it; it does not
    claim it is harmless.
    """

    from metroflow.benchmarks.morphology_control_table import build_osm_topology
    from metroflow.city.morphology_metrics import _simplified_segments

    topology = build_osm_topology(_REPO_ROOT / "artifacts" / "osm_control" / "barcelona.osm")
    segments, _degree, _dropped = _simplified_segments(topology, topology.road_geometry)

    loops = [item for item in segments if math.dist(item[1], item[2]) == 0.0]
    loop_share = sum(item[0] for item in loops) / sum(item[0] for item in segments)

    assert len(loops) == 1
    assert _GOLDEN["cities"]["barcelona.osm"]["graph"]["self_loop_proportion"] == 0.0
    assert loop_share < 0.01, "the unexplained self-loop must stay under 1% of length"
