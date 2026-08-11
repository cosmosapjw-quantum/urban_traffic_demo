import hashlib
import subprocess
import sys
from dataclasses import FrozenInstanceError, fields, replace

import pytest

from metroflow.city.scale import CityScaleSpec


_DIGEST = "0" * 64


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _road(
    road_id: int,
    label: str,
    start_node_id: int,
    end_node_id: int,
    points_mm: tuple[tuple[int, int], ...],
):
    from metroflow.city.scalable_topology import (
        FacilityKind,
        PhysicalRoadRecord,
        RoadHierarchy,
    )

    return PhysicalRoadRecord(
        road_id,
        _digest(label),
        start_node_id,
        end_node_id,
        points_mm,
        RoadHierarchy.LOCAL,
        FacilityKind.SURFACE,
        0,
        frozenset({"forward", "reverse"}),
        None,
        None,
        None,
        "v2:surface:local",
        "test",
    )


def test_scalable_topology_import_isolated() -> None:
    """Importing the S2 kernel must not admit downstream or simulator modules."""
    import metroflow.city.scalable_topology as topology

    assert CityScaleSpec(100_000, 40.0).target_population == 100_000
    assert topology.__doc__

    code = """
import sys
import metroflow.city.scalable_topology
for name in (
    "metroflow.sim.config",
    "metroflow.city.growth_fabric",
    "metroflow.city.growth_topology",
    "metroflow.city.scalable_blocks",
    "metroflow.city.scalable_topology_adapter",
    "metroflow.city.scalable_authority",
):
    assert name not in sys.modules, name
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def test_scalar_records_define_explicit_units_and_authority() -> None:
    """Removing the scalar record surface would erase S2's unit authority."""
    from metroflow.city.scalable_topology import (
        RoadHierarchy,
        MAX_JUNCTIONS,
        MAX_PHYSICAL_ROADS,
        MAX_SURFACE_DEGREE,
        SCHEMA_VERSION,
        STYLE_IDS,
        TERRAIN_CELL_SIZE_M,
        TILE_SIZE_M,
        FacilityKind,
        PhysicalNodeRecord,
        PhysicalRoadRecord,
        RowIntervalAuthority,
        ScalableScaleSnapshot,
    )

    assert SCHEMA_VERSION == "tmfcg_s2_v1"
    assert (TILE_SIZE_M, TERRAIN_CELL_SIZE_M) == (2_000.0, 50.0)
    assert (MAX_JUNCTIONS, MAX_PHYSICAL_ROADS, MAX_SURFACE_DEGREE) == (
        120_000,
        300_000,
        4,
    )
    assert STYLE_IDS == ("grid_core",)
    assert tuple(member.value for member in RoadHierarchy) == (
        "expressway",
        "arterial",
        "collector",
        "local",
    )
    assert tuple(member.value for member in FacilityKind) == (
        "surface",
        "mainline",
        "ramp",
        "bridge",
        "tunnel",
    )

    scale = ScalableScaleSnapshot(100_000, 40.0)
    node = PhysicalNodeRecord(0, _DIGEST, 1_000, 2_000, 0, "junction")
    row = RowIntervalAuthority(2_000, 0, 0, 4_000, (0, 0), 1_000, 1_000, False)
    road = PhysicalRoadRecord(
        0,
        "1" * 64,
        0,
        1,
        ((1_000, 2_000), (3_000, 2_000)),
        RoadHierarchy.LOCAL,
        FacilityKind.SURFACE,
        0,
        frozenset({"forward", "reverse"}),
        None,
        None,
        None,
        "v2:surface:local",
        "test",
        "surface-horizontal",
        row,
    )

    assert scale == ScalableScaleSnapshot(target_population=100_000, urbanized_area_km2=40.0)
    assert node.point_mm == (1_000, 2_000)
    assert road.canonical_key == (0, 1, ((1_000, 2_000), (3_000, 2_000)), 0)
    assert tuple(field.name for field in fields(road)) == (
        "road_id",
        "semantic_id",
        "start_node_id",
        "end_node_id",
        "points_mm",
        "hierarchy",
        "facility",
        "layer",
        "access_directions",
        "layer_transition",
        "structure_group",
        "failure_group",
        "profile_id",
        "provenance",
        "semantic_role",
        "row_interval",
    )
    assert not hasattr(road, "__dict__")
    with pytest.raises(FrozenInstanceError):
        node.x_mm = 0


@pytest.mark.parametrize("value", [True, 0.0, "0"])
def test_scalar_records_reject_coercive_integer_authority(value: object) -> None:
    from metroflow.city.scalable_topology import PhysicalNodeRecord

    with pytest.raises(TypeError, match="integer"):
        PhysicalNodeRecord(value, _DIGEST, 0, 0, 0)


def test_scalar_records_validate_digests_geometry_directions_and_profiles() -> None:
    from metroflow.city.scalable_topology import (
        FacilityKind,
        PhysicalNodeRecord,
        PhysicalRoadRecord,
        RoadHierarchy,
    )

    with pytest.raises(ValueError, match="SHA-256"):
        PhysicalNodeRecord(0, "not-a-digest", 0, 0, 0)

    common = dict(
        road_id=0,
        semantic_id=_DIGEST,
        start_node_id=0,
        end_node_id=1,
        hierarchy=RoadHierarchy.LOCAL,
        facility=FacilityKind.SURFACE,
        layer=0,
        access_directions=frozenset({"forward", "reverse"}),
        layer_transition=None,
        structure_group=None,
        failure_group=None,
        profile_id="v2:surface:local",
        provenance="test",
    )
    for points in (((0, 0),), ((0, 0), (0, 0)), ((0, 0), (1, 0), (1, 0))):
        with pytest.raises(ValueError, match="points_mm"):
            PhysicalRoadRecord(points_mm=points, **common)
    with pytest.raises(TypeError, match="integer"):
        PhysicalRoadRecord(points_mm=((0, 0.5), (1, 0)), **common)
    with pytest.raises(ValueError, match="access_directions"):
        PhysicalRoadRecord(
            points_mm=((0, 0), (1, 0)), **(common | {"access_directions": frozenset()})
        )
    with pytest.raises(ValueError, match="profile_id"):
        PhysicalRoadRecord(points_mm=((0, 0), (1, 0)), **(common | {"profile_id": "unknown"}))


def test_ramp_records_require_explicit_two_layer_transition() -> None:
    from metroflow.city.scalable_topology import PhysicalRoadRecord, RoadHierarchy

    common = dict(
        road_id=0,
        semantic_id=_DIGEST,
        start_node_id=0,
        end_node_id=1,
        points_mm=((0, 0), (1, 0)),
        hierarchy=RoadHierarchy.ARTERIAL,
        facility="ramp",
        layer=1,
        access_directions=frozenset({"forward"}),
        structure_group=None,
        failure_group=None,
        profile_id="v2:ramp",
        provenance="test",
    )
    with pytest.raises(ValueError, match="ramps require"):
        PhysicalRoadRecord(layer_transition=None, **common)
    with pytest.raises(ValueError, match="exactly two"):
        PhysicalRoadRecord(layer_transition=(0, 1, 2), **common)
    ramp = PhysicalRoadRecord(layer_transition=(0, 1), **common)
    assert ramp.layer_transition == (0, 1)
    assert ramp.facility.value == "ramp"


def test_terrain_and_lattice_are_coordinate_keyed_and_seam_exact() -> None:
    """Removing terrain ownership would make the lattice traversal-dependent."""
    from metroflow.city.scalable_topology import (
        ScalableTerrainField,
        _extent_mm,
        _local_axis,
        _monotone_partial_match,
        _seam_coordinates,
        _terrain_fingerprint,
        _tile_domain,
        _validate_tile_order,
    )

    assert _extent_mm(40.0) == (7_171_372, 5_577_734)
    extent = (-2_100_000, 2_100_000, -1_000, 1_000)
    tiles = _tile_domain(extent)
    assert tiles == (
        (-2, -1),
        (-1, -1),
        (0, -1),
        (1, -1),
        (-2, 0),
        (-1, 0),
        (0, 0),
        (1, 0),
    )
    _validate_tile_order(tiles, tuple(reversed(tiles)))
    with pytest.raises(ValueError, match="exact permutation"):
        _validate_tile_order(tiles, tiles[:-1])

    fingerprint = _terrain_fingerprint(7_171.372, 5_577.734, 17, "grid_core", None)
    terrain = ScalableTerrainField(
        7_171.372,
        5_577.734,
        50.0,
        2_000.0,
        17,
        "grid_core",
        None,
        fingerprint,
    )
    assert terrain.cell_key_at(1.0, 1.0) == (0, 0)
    assert terrain.cell_key_at(-0.001, -50.001) == (-1, -2)
    assert terrain.intensity_at(1.0, 1.0) == terrain.intensity_at(49.999, 49.999)
    assert terrain.intensity_at(1.0, 1.0) != terrain.intensity_at(51.0, 1.0)
    intensity = terrain.intensity_at(123.0, 456.0)
    assert terrain.spacing_at(123.0, 456.0) == pytest.approx(
        max(80.0, min(220.0, 220.0 - 140.0 * intensity**0.5))
    )

    assert _seam_coordinates(-4_500_000, 4_500_000) == (
        -4_000_000,
        -2_000_000,
        0,
        2_000_000,
        4_000_000,
    )
    axis = _local_axis(0, 4_500_000, terrain, "x", fixed_mm=75_000)
    assert axis[0] == 0 and axis[-1] == 4_500_000
    assert {2_000_000, 4_000_000} < set(axis)
    assert all(left < right for left, right in zip(axis, axis[1:]))
    assert _monotone_partial_match((10, 20, 30), (1, 2, 3, 4, 5)) == (
        (0, 0),
        (1, 2),
        (2, 4),
    )


def test_terrain_grammar_and_barrier_authority_fail_closed() -> None:
    from metroflow.city.scalable_topology import ScalableTerrainField, _terrain_fingerprint

    fingerprint = _terrain_fingerprint(1.0, 1.0, 17, "grid_core", None)
    common = dict(
        width_m=1.0,
        height_m=1.0,
        cell_size_m=50.0,
        tile_size_m=2_000.0,
        seed=17,
        style_id="grid_core",
        barrier_seam_x_mm=None,
        fingerprint=fingerprint,
    )
    for changes in (
        {"width_m": float("nan")},
        {"height_m": 0.0},
        {"cell_size_m": 50.1},
        {"tile_size_m": 1_999.0},
    ):
        with pytest.raises(ValueError, match="terrain|finite|cell|tile"):
            ScalableTerrainField(**(common | changes))
    with pytest.raises(TypeError, match="seed"):
        ScalableTerrainField(**(common | {"seed": True}))
    with pytest.raises(ValueError, match="barrier"):
        ScalableTerrainField(**(common | {"barrier_seam_x_mm": 0}))


def test_row_interval_authority_equals_literal_geometry_and_terrain_owner() -> None:
    from metroflow.city.scalable_topology import (
        FacilityKind,
        PhysicalRoadRecord,
        RoadHierarchy,
        ScalableTerrainField,
        _row_interval_authority,
        _terrain_fingerprint,
        _validate_row_interval_authority,
    )

    terrain = ScalableTerrainField(
        4_500.0,
        1_000.0,
        50.0,
        2_000.0,
        17,
        "grid_core",
        None,
        _terrain_fingerprint(4_500.0, 1_000.0, 17, "grid_core", None),
    )
    extent = (0, 4_500_000, 0, 1_000_000)
    authority = _row_interval_authority(1_950_000, 2_000_000, 75_000, terrain, extent)
    assert authority.owner_cell == (39, 1)
    assert (authority.tile_left_mm, authority.tile_right_mm) == (0, 2_000_000)
    assert authority.realized_spacing_mm == 50_000
    assert authority.seam_truncated

    road = PhysicalRoadRecord(
        0,
        _DIGEST,
        0,
        1,
        ((1_950_000, 75_000), (2_000_000, 75_000)),
        RoadHierarchy.LOCAL,
        FacilityKind.SURFACE,
        0,
        frozenset({"forward", "reverse"}),
        None,
        None,
        None,
        "v2:surface:local",
        "test",
        "surface-horizontal",
        authority,
    )
    _validate_row_interval_authority(road, terrain, extent)
    forged = replace(authority, owner_cell=(38, 1))
    with pytest.raises(ValueError, match="row interval authority"):
        _validate_row_interval_authority(replace(road, row_interval=forged), terrain, extent)


def test_physical_record_audit_counts_exact_intersections() -> None:
    """Removing the record audit would admit unresolved same-layer crossings."""
    from metroflow.city.scalable_topology import PhysicalNodeRecord, audit_physical_records

    nodes = (
        PhysicalNodeRecord(0, _digest("west"), -10, 0, 0),
        PhysicalNodeRecord(1, _digest("east"), 10, 0, 0),
        PhysicalNodeRecord(2, _digest("south"), 0, -10, 0),
        PhysicalNodeRecord(3, _digest("north"), 0, 10, 0),
    )
    audit = audit_physical_records(
        nodes,
        (
            _road(0, "horizontal", 0, 1, ((-10, 0), (10, 0))),
            _road(1, "vertical", 2, 3, ((0, -10), (0, 10))),
        ),
    )

    assert not audit.is_connected
    assert audit.same_layer_proper_crossing_count == 1
    assert audit.t_touch_count == 0
    assert audit.collinear_overlap_count == 0
    assert audit.endpoint_anchor_mismatch_count == 0


def test_physical_record_audit_rejects_duplicate_ids_and_semantics() -> None:
    from metroflow.city.scalable_topology import PhysicalNodeRecord, audit_physical_records

    duplicate_nodes = (
        PhysicalNodeRecord(0, _digest("node-a"), 0, 0, 0),
        PhysicalNodeRecord(0, _digest("node-b"), 1, 0, 0),
    )
    with pytest.raises(ValueError, match="duplicate node"):
        audit_physical_records(duplicate_nodes, ())

    nodes = (
        PhysicalNodeRecord(0, _digest("node-a"), 0, 0, 0),
        PhysicalNodeRecord(1, _digest("node-b"), 1, 0, 0),
    )
    road = _road(0, "road", 0, 1, ((0, 0), (1, 0)))
    with pytest.raises(ValueError, match="duplicate road"):
        audit_physical_records(nodes, (road, replace(road, road_id=1)))


def test_physical_record_audit_tracks_connectivity_and_endpoint_layers() -> None:
    from metroflow.city.scalable_topology import PhysicalNodeRecord, audit_physical_records

    nodes = (
        PhysicalNodeRecord(0, _digest("layer-a"), 0, 0, 1),
        PhysicalNodeRecord(1, _digest("layer-b"), 1, 0, 0),
        PhysicalNodeRecord(2, _digest("layer-c"), 2, 0, 0),
    )
    first = _road(0, "layer-road", 0, 1, ((0, 0), (1, 0)))
    second = _road(1, "connected-road", 1, 2, ((1, 0), (2, 0)))

    audit = audit_physical_records(nodes, (first, second))

    assert audit.is_connected
    assert audit.different_layer_false_junction_count == 1


def test_record_audit_counts_touches_overlaps_self_intersections_and_welds() -> None:
    from metroflow.city.scalable_topology import PhysicalNodeRecord, audit_physical_records

    nodes = (
        PhysicalNodeRecord(0, _digest("a"), 0, 0, 0),
        PhysicalNodeRecord(1, _digest("b"), 3_000, 0, 0),
        PhysicalNodeRecord(2, _digest("c"), 1_000, 2_000, 0),
        PhysicalNodeRecord(3, _digest("d"), 0, 1_000, 0),
    )
    overlap = _road(0, "overlap", 0, 1, ((0, 0), (2_000, 0), (1_000, 0), (3_000, 0)))
    foreign = _road(1, "touch", 2, 3, ((1_000, 2_000), (1_000, 0), (0, 1_000)))
    returned = _road(2, "returned", 0, 3, ((0, 0), (1_000, 0), (0, 0), (0, 1_000)))
    bow = _road(3, "bow", 0, 1, ((0, 0), (2_000, 2_000), (0, 2_000), (2_000, 0)))

    audit = audit_physical_records(nodes, (overlap, foreign, returned, bow))

    assert audit.t_touch_count >= 1
    assert audit.collinear_overlap_count >= 1
    assert audit.self_intersection_count >= 1
    assert audit.nonadjacent_weld_count >= 1


def test_segment_supercover_and_predicates_preserve_long_diagonal_events() -> None:
    from metroflow.city.scalable_topology import (
        _collinear_overlap,
        _point_in_open_segment,
        _proper_intersection,
        _segment_supercover_cells,
    )

    assert _proper_intersection((0, 0), (10, 10), (0, 10), (10, 0))
    assert _point_in_open_segment((5, 0), (0, 0), (10, 0))
    assert _collinear_overlap((0, 0), (10, 0), (5, 0), (15, 0))
    cells = _segment_supercover_cells((0, 0), (40_000_000, 40_000_000), 250_000)
    assert len(cells) < 1_000
    assert {(0, 0), (160, 160)} <= set(cells)


def test_record_audit_counts_more_than_six_events_without_truncation() -> None:
    from metroflow.city.scalable_topology import PhysicalNodeRecord, audit_physical_records

    nodes = tuple(
        PhysicalNodeRecord(index, _digest(f"many-node-{index}"), index * 1_000, 0, 0)
        for index in range(16)
    )
    vertical = tuple(
        _road(
            index,
            f"vertical-{index}",
            index * 2,
            index * 2 + 1,
            ((index * 1_000, -10_000), (index * 1_000, 10_000)),
        )
        for index in range(8)
    )
    horizontal = _road(8, "horizontal-many", 0, 1, ((-1_000, 0), (8_000, 0)))

    audit = audit_physical_records(nodes, vertical + (horizontal,))

    assert audit.same_layer_proper_crossing_count == 8
    assert audit.endpoint_anchor_mismatch_count == 18


def test_grid_core_builder_owns_scale_extent_and_immutable_records() -> None:
    """Removing the builder would leave Task3 without canonical physical records."""
    from metroflow.city.scalable_topology import (
        build_scalable_street_network,
        ScalableStreetNetwork,
    )

    caller_scale = CityScaleSpec(100_000, 40.0)
    network = build_scalable_street_network(caller_scale, "grid_core", 17)
    object.__setattr__(caller_scale, "target_population", 200_000)

    assert isinstance(network, ScalableStreetNetwork)
    assert network.scale_spec.target_population == 100_000
    assert network.extent_mm == (-3_585_686, 3_585_686, -2_788_867, 2_788_867)
    assert (network.width_m, network.height_m) == pytest.approx((7_171.372, 5_577.734))
    assert network.hidden_repair_count == 0
    assert len(network.gateway_node_ids) == 8
    assert isinstance(network.nodes, tuple) and isinstance(network.roads, tuple)


def test_grid_core_replays_and_fingerprints_seed_and_scale() -> None:
    from metroflow.city.scalable_topology import build_scalable_street_network

    first = build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", 17)
    same = build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", 17)
    changed_seed = build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", 29)
    changed_scale = build_scalable_street_network(CityScaleSpec(150_000, 50.0), "grid_core", 17)

    assert first == same
    assert len({first.fingerprint, changed_seed.fingerprint, changed_scale.fingerprint}) == 3
    assert first.scale_fingerprint != changed_scale.scale_fingerprint
    assert first.style_fingerprint != changed_seed.style_fingerprint


def test_grid_core_tile_order_is_a_permutation_not_generation_input() -> None:
    from metroflow.city.scalable_topology import build_scalable_street_network

    canonical = build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", 17)
    tiles = canonical.tile_coordinates
    reversed_network = build_scalable_street_network(
        CityScaleSpec(100_000, 40.0),
        "grid_core",
        17,
        tile_order=tuple(reversed(tiles)),
    )

    assert canonical == reversed_network
    with pytest.raises(ValueError, match="exact permutation"):
        build_scalable_street_network(
            CityScaleSpec(100_000, 40.0), "grid_core", 17, tile_order=tiles[:-1]
        )


def test_grid_core_has_dense_semantic_order_eight_ramps_and_literal_rows() -> None:
    from metroflow.city.scalable_topology import (
        FacilityKind,
        audit_physical_records,
        build_scalable_street_network,
    )

    network = build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", 17)
    ramps = [road for road in network.roads if road.facility is FacilityKind.RAMP]
    row_roads = [road for road in network.roads if road.row_interval is not None]

    assert [node.node_id for node in network.nodes] == list(range(len(network.nodes)))
    assert [road.road_id for road in network.roads] == list(range(len(network.roads)))
    assert [node.semantic_id for node in network.nodes] == sorted(
        node.semantic_id for node in network.nodes
    )
    assert [road.semantic_id for road in network.roads] == sorted(
        road.semantic_id for road in network.roads
    )
    assert len(ramps) == 8
    assert all(ramp.layer_transition == (0, 1) for ramp in ramps)
    assert all(ramp.points_mm[0] != ramp.points_mm[-1] for ramp in ramps)
    assert row_roads
    assert all(
        road.points_mm
        == (
            (road.row_interval.left_x_mm, road.row_interval.row_y_mm),
            (
                road.row_interval.left_x_mm + road.row_interval.realized_spacing_mm,
                road.row_interval.row_y_mm,
            ),
        )
        for road in row_roads
    )
    audit = audit_physical_records(network.nodes, network.roads)
    assert audit.is_connected
    assert (
        audit.same_layer_proper_crossing_count,
        audit.t_touch_count,
        audit.collinear_overlap_count,
        audit.self_intersection_count,
        audit.nonadjacent_weld_count,
        audit.different_layer_false_junction_count,
        audit.endpoint_anchor_mismatch_count,
    ) == (0, 0, 0, 0, 0, 0, 0)


def test_grid_core_exposes_tile_seams_and_fails_closed_on_budgets(monkeypatch) -> None:
    import metroflow.city.scalable_topology as kernel

    network = kernel.build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", 17)
    surface_x = {node.x_mm for node in network.nodes if node.layer == 0}
    surface_y = {node.y_mm for node in network.nodes if node.layer == 0}
    assert {-2_000_000, 0, 2_000_000} <= surface_x
    assert {-2_000_000, 0, 2_000_000} <= surface_y

    monkeypatch.setattr(kernel, "MAX_PHYSICAL_ROADS", 1)
    with pytest.raises(ValueError, match="road budget"):
        kernel.build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", 17)


def test_grid_core_rejects_non_city_scale_unknown_style_and_noninteger_seed() -> None:
    from metroflow.city.scalable_topology import build_scalable_street_network

    with pytest.raises(TypeError, match="CityScaleSpec"):
        build_scalable_street_network(object(), "grid_core", 17)
    with pytest.raises(ValueError, match="style_id"):
        build_scalable_street_network(CityScaleSpec(100_000, 40.0), "organic", 17)
    with pytest.raises(TypeError, match="seed"):
        build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", True)
