"""The three properties no stencil-based generator can produce.

Measured on `realistic_synthetic_v1`, which samples a fixed point set and
connects it with a local stencil: dead-end share 0.0000-0.0025 against a
reference band of 0.027-0.288, and circuity exactly 1.0 on all 30 audited maps.
Neither is reachable by tuning inside that family - dropping the diagonal
offsets fixes mean degree but drives four-way share to 0.61-0.85 against a 0.69
ceiling, and nothing in the pipeline can create a graph leaf at all.

These tests pin the mechanisms that replace it, not the tuned numbers.
"""

from __future__ import annotations

import math

import pytest


def _fields(style_id="grid_core", seed=17):
    from metroflow.city.terrain_field import build_terrain_field
    from metroflow.city.urban_form import build_urban_form_field

    terrain = build_terrain_field(width=6000, height=6000, seed=seed, style_id=style_id)
    urban_form = build_urban_form_field(terrain=terrain, style_id=style_id, seed=seed)
    return terrain, urban_form


def _topology(style_id="grid_core", seed=17):
    from metroflow.city.growth_fabric import compile_grown_network, grow_street_network

    terrain, urban_form = _fields(style_id, seed)
    network = grow_street_network(terrain=terrain, urban_form=urban_form, seed=seed)
    return compile_grown_network(network.streets)


def _degrees(topology):
    degree: dict[int, int] = {}
    seen: set[tuple[int, int]] = set()
    for link in topology.links:
        pair = (min(link.src_node_id, link.dst_node_id), max(link.src_node_id, link.dst_node_id))
        if pair in seen:
            continue
        seen.add(pair)
        for node_id in pair:
            degree[node_id] = degree.get(node_id, 0) + 1
    return degree


def test_growth_creates_dead_ends() -> None:
    """A tip that cannot legally extend terminates; a stencil has no leaves."""

    degree = _degrees(_topology())

    assert sum(1 for value in degree.values() if value == 1) > 0


def test_growth_creates_curved_streets() -> None:
    """Arc length must exceed chord length, or circuity is pinned at 1.0."""

    topology = _topology()
    curved = 0
    for centerline in topology.road_geometry.centerlines:
        chord = math.dist(centerline.points_m[0], centerline.points_m[-1])
        if chord > 0.0 and centerline.length_m / chord > 1.001:
            curved += 1

    assert curved > 0
    assert any(len(item.points_m) > 2 for item in topology.road_geometry.centerlines)


def test_growth_creates_t_junctions_not_only_crossings() -> None:
    """Snapping onto a street interior yields degree 3; a lattice cannot."""

    degree = _degrees(_topology())

    assert sum(1 for value in degree.values() if value == 3) > 0


def test_growth_assigns_hierarchy_by_construction() -> None:
    """Classes come from the seeding pass, not from relabelling a built graph."""

    from metroflow.city.graph import RoadClass

    classes = {link.road_class for link in _topology().links}

    assert RoadClass.LOCAL in classes
    assert RoadClass.COLLECTOR in classes
    assert RoadClass.ARTERIAL in classes


def test_growth_is_deterministic_for_a_seed() -> None:
    """Replay fingerprints require byte-identical output for identical input."""

    first = _topology(seed=29)
    second = _topology(seed=29)

    assert first.road_geometry.fingerprint == second.road_geometry.fingerprint


def test_different_seeds_produce_different_maps() -> None:
    """The legacy `standard` path ignores its seed entirely; this must not."""

    assert _topology(seed=17).road_geometry.fingerprint != _topology(seed=29).road_geometry.fingerprint


def test_compiled_links_carry_arc_length_not_chord_length() -> None:
    """`length_m` must be the polyline arc length the runtime will drive on."""

    topology = _topology()
    geometry = topology.road_geometry
    checked = 0
    for link in topology.links:
        centerline = geometry.centerline(geometry.assignment_for_link(link.link_id).geometry_id)
        assert link.length_m == pytest.approx(centerline.length_m, rel=1e-9)
        checked += 1
    assert checked > 0


def test_compiled_topology_has_no_duplicate_or_self_links() -> None:
    topology = _topology()
    pairs = [(link.src_node_id, link.dst_node_id) for link in topology.links]

    assert all(src != dst for src, dst in pairs)
    assert len(pairs) == len(set(pairs))
