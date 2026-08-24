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


def _rebuild_network_identity(
    network: object,
    *,
    node_changes: dict[int, dict[str, object]] | None = None,
    road_changes: dict[int, dict[str, object]] | None = None,
    drop_road_ids: frozenset[int] = frozenset(),
    duplicate_road_id: int | None = None,
    network_changes: dict[str, object] | None = None,
) -> object:
    """Re-key every public identity after an adversarial record change."""
    import metroflow.city.scalable_topology as kernel

    node_changes = node_changes or {}
    road_changes = road_changes or {}
    network_changes = network_changes or {}
    seed = network_changes.get("seed", network.seed)
    style_id = network_changes.get("style_id", network.style_id)
    terrain = network_changes.get("terrain", network.terrain)

    pending_nodes = []
    for node in network.nodes:
        candidate = replace(node, **node_changes.get(node.node_id, {}))
        semantic_id = kernel._semantic_id(
            (
                kernel.SCHEMA_VERSION,
                "node",
                seed,
                style_id,
                candidate.semantic_role,
                (candidate.x_mm, candidate.y_mm, candidate.layer),
            )
        )
        pending_nodes.append((node.node_id, replace(candidate, semantic_id=semantic_id)))
    pending_nodes.sort(key=lambda item: item[1].semantic_id)
    nodes = tuple(
        replace(candidate, node_id=index)
        for index, (_old_id, candidate) in enumerate(pending_nodes)
    )
    by_old_id = {old_id: rebuilt for rebuilt, (old_id, _candidate) in zip(nodes, pending_nodes)}

    pending_roads = []
    source_roads = [road for road in network.roads if road.road_id not in drop_road_ids]
    if duplicate_road_id is not None:
        source_roads.append(network.roads[duplicate_road_id])
    for road in source_roads:
        candidate = replace(road, **road_changes.get(road.road_id, {}))
        start = by_old_id[candidate.start_node_id]
        end = by_old_id[candidate.end_node_id]
        directions = tuple(sorted(candidate.access_directions))
        swapped_directions = tuple(
            sorted(
                "reverse"
                if direction == "forward"
                else "forward"
                if direction == "reverse"
                else direction
                for direction in directions
            )
        )
        orientation = min(
            (start.semantic_id, end.semantic_id, candidate.points_mm, directions),
            (
                end.semantic_id,
                start.semantic_id,
                tuple(reversed(candidate.points_mm)),
                swapped_directions,
            ),
        )
        semantic_id = kernel._semantic_id(
            (
                kernel.SCHEMA_VERSION,
                "road",
                seed,
                style_id,
                candidate.semantic_role,
                orientation,
                candidate.hierarchy.value,
                candidate.facility.value,
                candidate.layer,
                candidate.layer_transition,
                candidate.structure_group,
                candidate.failure_group,
                candidate.profile_id,
                candidate.provenance,
                kernel._row_interval_content(candidate.row_interval),
                (
                    None
                    if candidate.ramp_purpose is None
                    else candidate.ramp_purpose.value
                ),
            )
        )
        pending_roads.append(
            replace(
                candidate,
                start_node_id=start.node_id,
                end_node_id=end.node_id,
                semantic_id=semantic_id,
            )
        )
    pending_roads.sort(key=lambda road: road.semantic_id)
    roads = tuple(replace(road, road_id=index) for index, road in enumerate(pending_roads))
    incidence = kernel._endpoint_incidence(nodes, roads)
    requested_gateways = network_changes.get("gateway_node_ids", network.gateway_node_ids)
    gateway_node_ids = tuple(by_old_id[node_id].node_id for node_id in requested_gateways)
    centers = network_changes.get("centers", network.centers)
    diagnostics = kernel._computed_seam_diagnostics(
        network.extent_mm, nodes, terrain, network.tile_coordinates
    )
    style_fingerprint = kernel._style_fingerprint(style_id, seed, centers, nodes, roads)
    fingerprint = kernel._network_fingerprint(
        network.scale_spec,
        style_id,
        seed,
        network.extent_mm,
        centers,
        gateway_node_ids,
        nodes,
        roads,
        incidence,
        terrain,
        network.tile_coordinates,
        diagnostics,
        network.hidden_repair_count,
    )
    return replace(
        network,
        seed=seed,
        style_id=style_id,
        nodes=nodes,
        roads=roads,
        gateway_node_ids=gateway_node_ids,
        endpoint_incidence=incidence,
        seam_diagnostics=diagnostics,
        centers=centers,
        terrain=terrain,
        style_fingerprint=style_fingerprint,
        fingerprint=fingerprint,
    )


def _copy_as_subclass(record: object, subclass: type) -> object:
    return subclass(**{field.name: getattr(record, field.name) for field in fields(record)})


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
        RampPurpose,
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
    assert STYLE_IDS == (
        "ring_radial",
        "grid_core",
        "polycentric_tod",
        "river_constrained",
        "superblock_mixed",
        "organic",
    )
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
    assert tuple(member.value for member in RampPurpose) == ("on_ramp", "off_ramp")

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
        "ramp_purpose",
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


def test_only_typed_interchange_ramps_require_layer_one() -> None:
    from metroflow.city.scalable_topology import PhysicalRoadRecord, RampPurpose, RoadHierarchy

    common = dict(
        road_id=0,
        semantic_id=_DIGEST,
        start_node_id=0,
        end_node_id=1,
        points_mm=((0, 0), (1, 0)),
        hierarchy=RoadHierarchy.ARTERIAL,
        facility="ramp",
        layer=0,
        layer_transition=(0, 1),
        structure_group=None,
        failure_group=None,
        profile_id="v2:ramp",
        provenance="legacy-test",
    )

    legacy = PhysicalRoadRecord(
        access_directions=frozenset({"forward", "reverse"}),
        **common,
    )
    assert legacy.layer == 0
    assert legacy.ramp_purpose is None
    with pytest.raises(ValueError, match="typed ramps require layer 1"):
        PhysicalRoadRecord(
            access_directions=frozenset({"forward"}),
            ramp_purpose=RampPurpose.ON_RAMP,
            **common,
        )


def test_generated_ramps_have_explicit_one_way_interchange_purposes() -> None:
    """A bidirectional connector cannot stand in for a merge and diverge pair."""
    from metroflow.city.scalable_topology import (
        FacilityKind,
        RampPurpose,
        build_scalable_street_network,
    )

    network = build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", 17)
    ramps = tuple(road for road in network.roads if road.facility is FacilityKind.RAMP)

    assert len(ramps) == 16
    assert {ramp.ramp_purpose for ramp in ramps} == {RampPurpose.ON_RAMP, RampPurpose.OFF_RAMP}
    assert all(ramp.access_directions == frozenset({"forward"}) for ramp in ramps)
    assert all(
        network.nodes[ramp.start_node_id].layer == 0
        and network.nodes[ramp.end_node_id].layer == 1
        for ramp in ramps
        if ramp.ramp_purpose is RampPurpose.ON_RAMP
    )
    assert all(
        network.nodes[ramp.start_node_id].layer == 1
        and network.nodes[ramp.end_node_id].layer == 0
        for ramp in ramps
        if ramp.ramp_purpose is RampPurpose.OFF_RAMP
    )
    assert all(
        sum(
            ramp.ramp_purpose is RampPurpose.ON_RAMP
            for ramp in ramps
            if gateway_id in {ramp.start_node_id, ramp.end_node_id}
        )
        == 1
        and sum(
            ramp.ramp_purpose is RampPurpose.OFF_RAMP
            for ramp in ramps
            if gateway_id in {ramp.start_node_id, ramp.end_node_id}
        )
        == 1
        for gateway_id in network.gateway_node_ids
    )


@pytest.mark.parametrize(
    ("population", "area_km2"),
    (
        (100_000, 25.0),
        (160_000, 40.0),
        (400_000, 100.0),
        (1_000_000, 250.0),
    ),
)
def test_river_directional_ramps_remain_free_of_same_layer_crossings(
    population: int, area_km2: float
) -> None:
    """Off-ramp curves must not cross the perimeter's other directed connectors."""
    from metroflow.city.scalable_topology import (
        audit_physical_records,
        build_scalable_street_network,
    )

    network = build_scalable_street_network(
        CityScaleSpec(population, area_km2), "river_constrained", 17
    )
    audit = audit_physical_records(network.nodes, network.roads)
    assert (
        audit.same_layer_proper_crossing_count,
        audit.t_touch_count,
        audit.collinear_overlap_count,
    ) == (0, 0, 0)


@pytest.mark.parametrize(
    ("population", "area_km2"),
    (
        (100_000, 25.0),
        (160_000, 40.0),
        (400_000, 100.0),
        (1_000_000, 250.0),
    ),
)
def test_river_scales_replay_under_reversed_tile_order_and_keep_crossbank_paths(
    population: int, area_km2: float
) -> None:
    """Area controls immutable topology; population must not hide a scale failure."""
    from metroflow.city.scalable_topology import (
        _river_bridge_groups,
        _surface_cross_bank_connected,
        build_scalable_street_network,
    )

    scale = CityScaleSpec(population, area_km2)
    first = build_scalable_street_network(scale, "river_constrained", 17)
    replay = build_scalable_street_network(
        scale,
        "river_constrained",
        17,
        tile_order=tuple(reversed(first.tile_coordinates)),
    )

    assert replay == first
    groups = _river_bridge_groups(first)
    assert len(groups) >= 3
    assert all(_surface_cross_bank_connected(first, excluded_group=group) for group in groups)


@pytest.mark.parametrize(
    ("population", "area_km2"),
    (
        (100_000, 25.0),
        (160_000, 40.0),
        (400_000, 100.0),
        (1_000_000, 250.0),
    ),
)
@pytest.mark.parametrize(
    "style_id",
    (
        "ring_radial",
        "grid_core",
        "polycentric_tod",
        "river_constrained",
        "superblock_mixed",
        "organic",
    ),
)
def test_every_style_has_connected_finite_scale_aware_surface_authority(
    style_id: str, population: int, area_km2: float
) -> None:
    """The budget must govern a whole city, never leave a fixed motif in empty area."""
    import math

    from metroflow.city.scalable_topology import (
        FacilityKind,
        audit_structural_network,
        build_scalable_street_network,
    )
    from metroflow.city.infrastructure_budget import InfrastructureBudget

    network = build_scalable_street_network(
        CityScaleSpec(population, area_km2), style_id, 17
    )
    budget = InfrastructureBudget.for_city(style_id, area_km2)
    audit = audit_structural_network(network)
    surface_length_m = sum(
        math.dist(left, right) / 1_000.0
        for road in network.roads
        if road.facility in {FacilityKind.SURFACE, FacilityKind.BRIDGE}
        for left, right in zip(road.points_mm, road.points_mm[1:])
    )

    assert audit.is_connected
    assert audit.center_disjoint_gateway_path_count == len(network.centers)
    assert len(network.gateway_node_ids) == budget.perimeter_gateway_count
    assert len(network.centers) == budget.center_count
    assert math.isfinite(surface_length_m / area_km2)
    assert surface_length_m / area_km2 > 0.0
    if style_id == "river_constrained":
        assert sum(road.facility is FacilityKind.BRIDGE for road in network.roads) == (
            budget.river_bridge_count
        )
    if style_id == "ring_radial":
        center_x, center_y = network.centers[0]
        radial_extent = max(
            max(abs(node.x_mm - center_x), abs(node.y_mm - center_y))
            for node in network.nodes
            if node.semantic_role == "ring-surface"
        )
        min_x, max_x, min_y, max_y = network.extent_mm
        available_radius = min(
            center_x - min_x,
            max_x - center_x,
            center_y - min_y,
            max_y - center_y,
        )
        assert radial_extent >= available_radius * 3 // 4 - 1


def test_population_changes_demand_scale_identity_but_not_static_topology() -> None:
    """No budget may accidentally make population a street-geometry input."""
    from metroflow.city.scalable_topology import build_scalable_street_network

    low_density = build_scalable_street_network(
        CityScaleSpec(100_000, 40.0), "polycentric_tod", 17
    )
    high_density = build_scalable_street_network(
        CityScaleSpec(160_000, 40.0), "polycentric_tod", 17
    )

    assert low_density.scale_fingerprint != high_density.scale_fingerprint
    assert low_density.style_fingerprint == high_density.style_fingerprint
    assert low_density.nodes == high_density.nodes
    assert low_density.roads == high_density.roads


def test_mainline_record_rejects_at_grade_surface_layer() -> None:
    from metroflow.city.scalable_topology import (
        FacilityKind,
        PhysicalRoadRecord,
        RoadHierarchy,
    )

    with pytest.raises(ValueError, match="mainlines require layer 1"):
        PhysicalRoadRecord(
            road_id=0,
            semantic_id=_DIGEST,
            start_node_id=0,
            end_node_id=1,
            points_mm=((0, 0), (1, 0)),
            hierarchy=RoadHierarchy.EXPRESSWAY,
            facility=FacilityKind.MAINLINE,
            layer=0,
            access_directions=frozenset({"forward", "reverse"}),
            layer_transition=None,
            structure_group=None,
            failure_group=None,
            profile_id="v2:mainline:expressway",
            provenance="test",
        )


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
    extent = (0, 4_500_000, 0, 900_000)
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


def _grid_core_horizontal_axes(network: object) -> tuple[frozenset[int], ...]:
    rows: dict[int, set[int]] = {}
    for road in network.roads:
        if road.semantic_role != "surface-horizontal":
            continue
        start, end = road.points_mm
        assert start[1] == end[1]
        rows.setdefault(start[1], set()).update((start[0], end[0]))
    return tuple(frozenset(axis) for _, axis in sorted(rows.items()))


@pytest.mark.parametrize("seed", (503, 701, 907))
def test_grid_core_uses_one_shared_x_axis_and_exact_surface_verticals(seed: int) -> None:
    """Row-local axes would turn semantic vertical roads into diagonals."""
    import metroflow.city.scalable_topology as kernel

    network = kernel.build_scalable_street_network(
        CityScaleSpec(100_000, 40.0), "grid_core", seed
    )
    axes = _grid_core_horizontal_axes(network)
    horizontals = [
        road for road in network.roads if road.semantic_role == "surface-horizontal"
    ]
    verticals = [
        road for road in network.roads if road.semantic_role == "surface-vertical"
    ]

    assert len(axes) > 1
    assert len(set(axes)) == 1
    assert horizontals
    assert all(road.row_interval is not None for road in horizontals)
    assert all(
        road.row_interval.axis_mode == "grid_core_shared_x_axis_v1"
        and road.row_interval.axis_sampling_y_mm == 0
        for road in horizontals
    )
    assert all(
        road.row_interval.seam_truncated
        or road.row_interval.realized_spacing_mm == road.row_interval.nominal_spacing_mm
        for road in horizontals
    )
    assert verticals
    assert all(road.points_mm[0][0] == road.points_mm[-1][0] for road in verticals)

    horizontal = horizontals[0]
    kernel._validate_row_interval_authority(horizontal, network.terrain, network.extent_mm)
    with pytest.raises(ValueError, match="row interval authority"):
        kernel._validate_row_interval_authority(
            replace(
                horizontal,
                row_interval=replace(
                    horizontal.row_interval,
                    axis_mode="row_local_v1",
                    axis_sampling_y_mm=None,
                ),
            ),
            network.terrain,
            network.extent_mm,
        )


def test_grid_core_seed_changes_spacing_without_losing_orthogonality() -> None:
    from metroflow.city.scalable_topology import build_scalable_street_network

    first = build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", 503)
    second = build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", 701)

    first_axis = _grid_core_horizontal_axes(first)[0]
    second_axis = _grid_core_horizontal_axes(second)[0]
    assert first_axis != second_axis
    for network in (first, second):
        assert len(set(_grid_core_horizontal_axes(network))) == 1
        assert all(
            road.points_mm[0][0] == road.points_mm[-1][0]
            for road in network.roads
            if road.semantic_role == "surface-vertical"
        )


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


def test_non_grid_terrain_spacing_uses_correlated_development_intensity() -> None:
    """Break caught: non-grid spacing remains independent cellwise hash noise."""
    from metroflow.city.development_field import (
        DevelopmentFieldConfig,
        DeterministicDevelopmentField,
    )
    from metroflow.city.scalable_topology import ScalableTerrainField, _terrain_fingerprint

    terrain = ScalableTerrainField(
        7_171.372,
        5_577.734,
        50.0,
        2_000.0,
        503,
        "organic",
        None,
        _terrain_fingerprint(7_171.372, 5_577.734, 503, "organic", None),
    )
    field = DeterministicDevelopmentField(
        seed=503,
        config=DevelopmentFieldConfig(correlation_length_m=400.0, amplitude=0.28),
    )

    assert terrain.intensity_at(1_225.0, -875.0) == field.intensity_at(1_225.0, -875.0)


def test_grid_core_has_dense_semantic_order_directed_ramps_and_literal_rows() -> None:
    from metroflow.city.scalable_topology import (
        FacilityKind,
        RampPurpose,
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
    assert len(ramps) == 16
    assert sum(ramp.ramp_purpose is RampPurpose.ON_RAMP for ramp in ramps) == 8
    assert sum(ramp.ramp_purpose is RampPurpose.OFF_RAMP for ramp in ramps) == 8
    assert all(ramp.layer_transition == (0, 1) for ramp in ramps)
    assert all(ramp.access_directions == frozenset({"forward"}) for ramp in ramps)
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
        build_scalable_street_network(CityScaleSpec(100_000, 40.0), "unknown_style", 17)
    with pytest.raises(TypeError, match="seed"):
        build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", True)


def test_polycentric_centers_have_distinct_public_arterial_corridors() -> None:
    """Collapsing centers onto one unnamed corridor would erase polycentric form."""
    from metroflow.city.scalable_topology import RoadHierarchy, build_scalable_street_network

    for seed in (17, 29):
        network = build_scalable_street_network(
            CityScaleSpec(100_000, 40.0), "polycentric_tod", seed
        )
        corridor_ids: list[set[str]] = []
        assert len(network.centers) >= 3
        for index, center in enumerate(network.centers):
            prefix = f"polycentric-center-{index}-"
            roads = [
                road
                for road in network.roads
                if road.hierarchy is RoadHierarchy.ARTERIAL
                and road.semantic_role.startswith(prefix)
            ]
            assert len(roads) >= 4
            assert any(center in (road.points_mm[0], road.points_mm[-1]) for road in roads)
            corridor_ids.append({road.semantic_id for road in roads})
        assert all(
            left.isdisjoint(right)
            for offset, left in enumerate(corridor_ids)
            for right in corridor_ids[offset + 1 :]
        )


def test_nonriver_style_inventory_replays_and_remains_distinct() -> None:
    from metroflow.city.scalable_topology import STYLE_IDS, build_scalable_street_network

    assert STYLE_IDS == (
        "ring_radial",
        "grid_core",
        "polycentric_tod",
        "river_constrained",
        "superblock_mixed",
        "organic",
    )
    nonriver_styles = tuple(style_id for style_id in STYLE_IDS if style_id != "river_constrained")
    fingerprints = set()
    geometries = set()
    for style_id in nonriver_styles:
        for seed in (17, 29):
            first = build_scalable_street_network(CityScaleSpec(100_000, 40.0), style_id, seed)
            second = build_scalable_street_network(CityScaleSpec(100_000, 40.0), style_id, seed)
            assert first == second
            fingerprints.add(first.fingerprint)
            geometries.add(tuple((node.x_mm, node.y_mm) for node in first.nodes if node.layer == 0))
    assert len(fingerprints) == 10
    assert len(geometries) == 10


def test_ring_radial_center_has_four_arterial_surface_arms() -> None:
    from metroflow.city.scalable_topology import (
        FacilityKind,
        RoadHierarchy,
        build_scalable_street_network,
    )

    for seed in (17, 29):
        network = build_scalable_street_network(CityScaleSpec(100_000, 40.0), "ring_radial", seed)
        center_x, center_y = network.centers[0]
        axes = [
            road
            for road in network.roads
            if road.facility is FacilityKind.SURFACE
            and (
                all(point[0] == center_x for point in road.points_mm)
                or all(point[1] == center_y for point in road.points_mm)
            )
        ]
        assert axes
        assert all(road.hierarchy is RoadHierarchy.ARTERIAL for road in axes)
        assert min(point[0] for road in axes for point in road.points_mm) < center_x
        assert max(point[0] for road in axes for point in road.points_mm) > center_x
        assert min(point[1] for road in axes for point in road.points_mm) < center_y
        assert max(point[1] for road in axes for point in road.points_mm) > center_y


def test_superblock_collectors_alternate_and_organic_connectors_are_bounded() -> None:
    from metroflow.city.scalable_topology import (
        FacilityKind,
        RoadHierarchy,
        build_scalable_street_network,
    )

    for seed in (17, 29):
        superblock = build_scalable_street_network(
            CityScaleSpec(100_000, 40.0), "superblock_mixed", seed
        )
        collector_roles = {
            road.semantic_role
            for road in superblock.roads
            if road.hierarchy is RoadHierarchy.COLLECTOR
        }
        assert any("horizontal" in role for role in collector_roles)
        assert any("vertical" in role for role in collector_roles)

        organic = build_scalable_street_network(CityScaleSpec(100_000, 40.0), "organic", seed)
        connectors = [
            road
            for road in organic.roads
            if road.facility is FacilityKind.SURFACE and road.semantic_role == "organic-connector"
        ]
        assert connectors
        min_x, max_x, min_y, max_y = organic.extent_mm
        bent_count = 0
        for road in connectors:
            assert len(road.points_mm) == 5
            start, *interior, end = road.points_mm
            dx, dy = end[0] - start[0], end[1] - start[1]
            bent_count += any(
                dx * (point[1] - start[1]) != dy * (point[0] - start[0])
                for point in interior
            )
            assert all(
                min_x <= point[0] <= max_x and min_y <= point[1] <= max_y
                for point in interior
            )
        assert bent_count / len(connectors) > 0.9


def test_nonriver_center_formula_and_mainline_access_use_bounded_400k_scale() -> None:
    from metroflow.city.scalable_topology import (
        FacilityKind,
        RoadHierarchy,
        build_scalable_street_network,
    )

    expected_centers = {
        "ring_radial": 1,
        "grid_core": 1,
        "polycentric_tod": 3,
        "superblock_mixed": 3,
        "organic": 1,
    }
    for style_id, expected in expected_centers.items():
        network = build_scalable_street_network(CityScaleSpec(400_000, 160.0), style_id, 17)
        assert len(network.centers) == expected
        mainline_nodes = {node.node_id for node in network.nodes if node.layer == 1}
        assert not any(
            road.hierarchy is RoadHierarchy.LOCAL
            and ({road.start_node_id, road.end_node_id} & mainline_nodes)
            for road in network.roads
        )
        assert all(
            road.facility is FacilityKind.RAMP and road.layer_transition == (0, 1)
            for road in network.roads
            if {road.start_node_id, road.end_node_id} & mainline_nodes
            and road.facility is not FacilityKind.MAINLINE
        )


def test_river_barrier_seam_and_ramp_triangle_are_explicit_structural_authority() -> None:
    """An implicit river crossing or ramp access would bypass physical authority."""
    from metroflow.city.scalable_topology import (
        FacilityKind,
        build_scalable_street_network,
    )

    river = build_scalable_street_network(CityScaleSpec(100_000, 40.0), "river_constrained", 17)
    assert river == build_scalable_street_network(
        CityScaleSpec(100_000, 40.0),
        "river_constrained",
        17,
        tile_order=tuple(reversed(river.tile_coordinates)),
    )
    assert river.terrain.barrier_seam_x_mm == 0
    diagnostics = dict(river.seam_diagnostics)
    assert diagnostics["barrier_seam_exception_count"] == 1
    assert diagnostics["seam_mismatch_count"] == 0
    crossings = [
        road
        for road in river.roads
        if road.layer == 0 and road.points_mm[0][0] < 0 < road.points_mm[-1][0]
    ]
    assert crossings
    assert all(road.facility is FacilityKind.BRIDGE for road in crossings)

    grid = build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", 17)
    by_id = {road.road_id: road for road in grid.roads}
    incidence = dict(grid.endpoint_incidence)
    for ramp in (road for road in grid.roads if road.facility is FacilityKind.RAMP):
        access_id = next(
            node_id
            for node_id in (ramp.start_node_id, ramp.end_node_id)
            if grid.nodes[node_id].layer == 0
        )
        surface_links = [
            by_id[road_id]
            for road_id in incidence[access_id]
            if by_id[road_id].facility is FacilityKind.SURFACE
        ]
        assert len(surface_links) == 2
        anchors = {
            road.end_node_id if road.start_node_id == access_id else road.start_node_id
            for road in surface_links
        }
        assert any({road.start_node_id, road.end_node_id} == anchors for road in grid.roads)


def test_river_failure_groups_are_complete_and_survive_each_removal() -> None:
    from metroflow.city.scalable_topology import (
        FacilityKind,
        _river_bridge_groups,
        _surface_cross_bank_connected,
        build_scalable_street_network,
    )

    for seed in (17, 29):
        network = build_scalable_street_network(
            CityScaleSpec(100_000, 40.0), "river_constrained", seed
        )
        groups = _river_bridge_groups(network)
        assert len(groups) >= 3
        assert all(
            road.failure_group in groups
            for road in network.roads
            if road.facility is FacilityKind.BRIDGE
        )
        assert all(_surface_cross_bank_connected(network, excluded_group=group) for group in groups)


@pytest.mark.parametrize("role_class", ("surface", "mainline-gateway", "ramp-access"))
def test_recomputed_authority_rejects_every_forged_node_role_class(
    role_class: str,
) -> None:
    import metroflow.city.scalable_topology as kernel

    network = kernel.build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", 17)
    node = next(
        node
        for node in network.nodes
        if node.semantic_role == role_class
        or (role_class == "ramp-access" and node.semantic_role.startswith("ramp-access-"))
    )

    with pytest.raises(ValueError, match="role|canonical"):
        _rebuild_network_identity(
            network,
            node_changes={node.node_id: {"semantic_role": f"forged-{node.semantic_role}"}},
        )


@pytest.mark.parametrize(
    ("style_id", "role_class"),
    (
        ("grid_core", "mainline"),
        ("grid_core", "ramp"),
        ("grid_core", "surface-horizontal"),
        ("grid_core", "surface-vertical"),
        ("grid_core", "surface-access-primary"),
        ("grid_core", "surface-access-secondary"),
        ("river_constrained", "river-bridge"),
        ("organic", "organic-connector"),
        ("polycentric_tod", "polycentric-row"),
        ("polycentric_tod", "polycentric-connector"),
    ),
)
def test_recomputed_authority_rejects_every_forged_road_role_class(
    style_id: str,
    role_class: str,
) -> None:
    import metroflow.city.scalable_topology as kernel

    network = kernel.build_scalable_street_network(CityScaleSpec(100_000, 40.0), style_id, 17)

    def matches(road) -> bool:
        if role_class == "mainline":
            return road.facility is kernel.FacilityKind.MAINLINE
        if role_class == "ramp":
            return road.facility is kernel.FacilityKind.RAMP
        if role_class == "polycentric-row":
            return road.semantic_role.startswith("polycentric-center-") and road.row_interval
        if role_class == "polycentric-connector":
            return road.semantic_role.startswith("polycentric-center-") and not road.row_interval
        return road.semantic_role == role_class

    road = next(road for road in network.roads if matches(road))
    with pytest.raises(ValueError, match="role|canonical"):
        _rebuild_network_identity(
            network,
            road_changes={road.road_id: {"semantic_role": f"forged-{road.semantic_role}"}},
        )


def test_recomputed_authority_rejects_one_millimeter_organic_midpoint_forgery() -> None:
    import metroflow.city.scalable_topology as kernel

    network = kernel.build_scalable_street_network(CityScaleSpec(100_000, 40.0), "organic", 17)
    road = next(road for road in network.roads if road.semantic_role == "organic-connector")
    forged_points = list(road.points_mm)
    midpoint_index = len(forged_points) // 2
    midpoint = forged_points[midpoint_index]
    forged_points[midpoint_index] = (midpoint[0] + 1, midpoint[1])
    forged = tuple(forged_points)
    with pytest.raises(ValueError, match="organic|canonical|geometry"):
        _rebuild_network_identity(network, road_changes={road.road_id: {"points_mm": forged}})


@pytest.mark.parametrize("midpoint_kind", ("off-row", "collinear", "out-of-order"))
def test_recomputed_authority_rejects_any_midpoint_on_a_row_interval(
    midpoint_kind: str,
) -> None:
    import metroflow.city.scalable_topology as kernel

    network = kernel.build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", 17)
    road = next(road for road in network.roads if road.row_interval is not None)
    start, end = road.points_mm
    if midpoint_kind == "off-row":
        midpoint = ((start[0] + end[0]) // 2, start[1] + 1)
    elif midpoint_kind == "collinear":
        midpoint = ((start[0] + end[0]) // 2, start[1])
    else:
        midpoint = (end[0] + 1, start[1])
    with pytest.raises(ValueError, match="row|horizontal|canonical"):
        _rebuild_network_identity(
            network,
            road_changes={road.road_id: {"points_mm": (start, midpoint, end)}},
        )


@pytest.mark.parametrize(
    "field_case", ("provenance", "directions", "structure-group", "failure-group")
)
def test_recomputed_authority_rejects_noncanonical_generated_road_fields(
    field_case: str,
) -> None:
    import metroflow.city.scalable_topology as kernel

    network = kernel.build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", 17)
    road = next(road for road in network.roads if road.semantic_role == "surface-vertical")
    changes = {
        "provenance": {"provenance": "forged"},
        "directions": {"access_directions": frozenset({"forward"})},
        "structure-group": {"structure_group": "forged-group"},
        "failure-group": {"failure_group": "forged-group"},
    }[field_case]
    with pytest.raises(ValueError, match="canonical|provenance|direction|group"):
        _rebuild_network_identity(network, road_changes={road.road_id: changes})


@pytest.mark.parametrize("field_case", ("hierarchy", "facility", "layer"))
def test_recomputed_authority_rejects_noncanonical_role_derived_road_shape(
    field_case: str,
) -> None:
    import metroflow.city.scalable_topology as kernel

    network = kernel.build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", 17)
    road = next(
        road
        for road in network.roads
        if road.semantic_role == "surface-vertical" and road.hierarchy is kernel.RoadHierarchy.LOCAL
    )
    if field_case == "hierarchy":
        changes = {
            "hierarchy": kernel.RoadHierarchy.ARTERIAL,
            "profile_id": "v2:surface:arterial",
        }
    elif field_case == "facility":
        changes = {
            "facility": kernel.FacilityKind.BRIDGE,
            "profile_id": f"v2:bridge:{road.hierarchy.value}",
        }
    else:
        changes = {"layer": 1}
    with pytest.raises(ValueError, match="canonical|facility|hierarchy|layer"):
        _rebuild_network_identity(network, road_changes={road.road_id: changes})


@pytest.mark.parametrize("field_case", ("centers", "gateway-order"))
def test_recomputed_authority_rejects_forged_centers_and_gateway_order(
    field_case: str,
) -> None:
    import metroflow.city.scalable_topology as kernel

    network = kernel.build_scalable_street_network(
        CityScaleSpec(100_000, 40.0), "polycentric_tod", 17
    )
    if field_case == "centers":
        changes = {
            "centers": ((network.centers[0][0] + 1, network.centers[0][1]),) + network.centers[1:]
        }
    else:
        changes = {"gateway_node_ids": tuple(reversed(network.gateway_node_ids))}
    with pytest.raises(ValueError, match="center|gateway|canonical"):
        _rebuild_network_identity(network, network_changes=changes)


def test_canonical_generated_network_survives_full_identity_round_trip() -> None:
    import metroflow.city.scalable_topology as kernel

    network = kernel.build_scalable_street_network(CityScaleSpec(100_000, 40.0), "organic", 17)
    assert _rebuild_network_identity(network) == network


def test_road_semantic_identity_has_canonical_reverse_orientation() -> None:
    import metroflow.city.scalable_topology as kernel

    network = kernel.build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", 17)
    road = network.roads[0]
    start, end = network.nodes[road.start_node_id], network.nodes[road.end_node_id]
    arguments = (
        network.seed,
        network.style_id,
        road.semantic_role,
        start.semantic_id,
        end.semantic_id,
        road.points_mm,
        road.hierarchy,
        road.facility,
        road.layer,
        road.access_directions,
        road.layer_transition,
        road.structure_group,
        road.failure_group,
        road.profile_id,
        road.provenance,
        road.row_interval,
    )
    forward = kernel._road_semantic_id(*arguments)
    reverse = kernel._road_semantic_id(
        *arguments[:3],
        arguments[4],
        arguments[3],
        tuple(reversed(road.points_mm)),
        *arguments[6:],
    )
    assert forward == reverse == road.semantic_id


@pytest.mark.parametrize(
    "semantic_role", ("surface-vertical", "surface-horizontal", "perimeter-mainline")
)
def test_fully_rekeyed_deletion_cannot_remove_a_canonical_road(
    semantic_role: str,
) -> None:
    """Deleting one member must fail exact generated-set admission."""
    import metroflow.city.scalable_topology as kernel

    network = kernel.build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", 17)
    road = next(road for road in network.roads if road.semantic_role == semantic_role)
    with pytest.raises(ValueError, match="canonical|record set|complete"):
        _rebuild_network_identity(network, drop_road_ids=frozenset({road.road_id}))


def test_count_preserving_canonical_duplicate_cannot_substitute_a_missing_road() -> None:
    import metroflow.city.scalable_topology as kernel

    network = kernel.build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", 17)
    horizontal = [road for road in network.roads if road.semantic_role == "surface-horizontal"]
    with pytest.raises(ValueError, match="canonical|record set|complete|duplicate"):
        _rebuild_network_identity(
            network,
            drop_road_ids=frozenset({horizontal[0].road_id}),
            duplicate_road_id=horizontal[1].road_id,
        )


def test_rekeyed_network_seed_must_equal_terrain_seed() -> None:
    import metroflow.city.scalable_topology as kernel

    network = kernel.build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", 17)
    with pytest.raises(ValueError, match="terrain.*seed|seed.*terrain"):
        _rebuild_network_identity(network, network_changes={"seed": 18})


@pytest.mark.parametrize("field_case", ("width", "height", "tile", "barrier", "fingerprint"))
def test_network_admission_rejects_each_nonbehavioral_terrain_mismatch(
    field_case: str,
) -> None:
    import metroflow.city.scalable_topology as kernel

    network = kernel.build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", 17)
    values = {field.name: getattr(network.terrain, field.name) for field in fields(network.terrain)}
    values.update(
        {
            "width": {"width_m": network.width_m + 1.0},
            "height": {"height_m": network.height_m + 1.0},
            "tile": {"tile_size_m": 1_500.0},
            "barrier": {"barrier_seam_x_mm": 0},
            "fingerprint": {"fingerprint": _digest("forged-terrain")},
        }[field_case]
    )
    if field_case != "fingerprint":
        values["fingerprint"] = kernel._terrain_fingerprint(
            values["width_m"],
            values["height_m"],
            values["seed"],
            values["style_id"],
            values["barrier_seam_x_mm"],
            values["cell_size_m"],
            values["tile_size_m"],
        )
    forged_terrain = object.__new__(kernel.ScalableTerrainField)
    for name, value in values.items():
        object.__setattr__(forged_terrain, name, value)
    with pytest.raises(ValueError, match="terrain|extent|fingerprint|barrier"):
        _rebuild_network_identity(network, network_changes={"terrain": forged_terrain})


def test_network_record_subclass_is_not_exact_authority() -> None:
    import metroflow.city.scalable_topology as kernel

    class NetworkProxy(kernel.ScalableStreetNetwork):
        __slots__ = ()

    network = kernel.build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", 17)
    with pytest.raises(TypeError, match="exact ScalableStreetNetwork"):
        _copy_as_subclass(network, NetworkProxy)


def test_mutable_behavior_proxy_cannot_survive_network_admission() -> None:
    import metroflow.city.scalable_topology as kernel

    class ToggleNetwork(kernel.ScalableStreetNetwork):
        __slots__ = ()
        hide_roads = False

        def __getattribute__(self, name: str):
            if name == "roads" and type(self).hide_roads:
                return ()
            return super().__getattribute__(name)

    network = kernel.build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", 17)
    with pytest.raises(TypeError, match="exact ScalableStreetNetwork"):
        _copy_as_subclass(network, ToggleNetwork)


def test_builder_performs_exactly_one_full_structural_admission_audit(monkeypatch) -> None:
    import metroflow.city.scalable_topology as kernel

    original = getattr(kernel, "audit_structural_network", lambda _network: None)
    calls = 0

    def counted(network):
        nonlocal calls
        calls += 1
        return original(network)

    monkeypatch.setattr(kernel, "audit_structural_network", counted, raising=False)
    kernel.build_scalable_street_network(CityScaleSpec(100_000, 40.0), "organic", 17)
    assert calls == 1


@pytest.mark.parametrize(
    "style_id",
    (
        "ring_radial",
        "grid_core",
        "polycentric_tod",
        "river_constrained",
        "superblock_mixed",
        "organic",
    ),
)
def test_every_style_is_connected_and_has_closed_structural_admission(
    style_id: str,
) -> None:
    import metroflow.city.scalable_topology as kernel

    network = kernel.build_scalable_street_network(CityScaleSpec(100_000, 40.0), style_id, 17)
    audit = kernel.audit_structural_network(network)
    assert {road.hierarchy for road in network.roads} == set(kernel.RoadHierarchy)
    assert audit.is_connected
    assert (
        audit.same_layer_proper_crossing_count,
        audit.t_touch_count,
        audit.collinear_overlap_count,
        audit.self_intersection_count,
        audit.nonadjacent_weld_count,
        audit.duplicate_road_count,
        audit.different_layer_false_junction_count,
        audit.endpoint_anchor_mismatch_count,
    ) == (0, 0, 0, 0, 0, 0, 0, 0)
    assert audit.center_disjoint_gateway_path_count == len(network.centers)
    assert max(len(road_ids) for _node_id, road_ids in network.endpoint_incidence) <= 4
    assert network.seam_diagnostics == kernel._computed_seam_diagnostics(
        network.extent_mm,
        network.nodes,
        network.terrain,
        network.tile_coordinates,
    )


def test_river_audit_owns_complete_groups_and_each_removal() -> None:
    import metroflow.city.scalable_topology as kernel

    network = kernel.build_scalable_street_network(
        CityScaleSpec(100_000, 40.0), "river_constrained", 17
    )
    audit = kernel.audit_structural_network(network)
    groups = kernel._river_bridge_groups(network)
    assert audit.river_cross_bank_group_count == len(groups) >= 3
    assert audit.river_group_removal_failures == ()
    assert all(
        kernel._surface_cross_bank_connected(network, excluded_group=group) for group in groups
    )


def test_final_surface_degree_cap_is_enforced_by_builder(monkeypatch) -> None:
    import metroflow.city.scalable_topology as kernel

    monkeypatch.setattr(kernel, "MAX_SURFACE_DEGREE", 0)
    with pytest.raises(ValueError, match="degree"):
        kernel.build_scalable_street_network(CityScaleSpec(100_000, 40.0), "grid_core", 17)
