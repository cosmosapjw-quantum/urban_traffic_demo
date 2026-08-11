import subprocess
import sys
from dataclasses import FrozenInstanceError, fields, replace

import pytest

from metroflow.city.scale import CityScaleSpec


_DIGEST = "0" * 64


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
