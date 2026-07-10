from __future__ import annotations

from collections import defaultdict
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    ("style_id", "expected_strategy", "expected_count"),
    (
        ("ring_radial", "radial_ring_mesh", 20),
        ("grid_core", "global_orthogonal_lattice", 22),
    ),
)
def test_continuous_fabric_structured_infill_is_deterministic(
    style_id: str,
    expected_strategy: str,
    expected_count: int,
) -> None:
    from metroflow.city.continuous_fabric import build_continuous_fabric_infill
    from metroflow.city.morphology_field import build_morphology_field

    field = build_morphology_field(
        scenario_id="synthetic_smoke",
        seed=17,
        style_id=style_id,
        width=4_400,
        height=4_000,
    )

    first = build_continuous_fabric_infill(
        morphology_field=field,
        street_pattern=str(field["morphology_street_pattern"]),
    )
    second = build_continuous_fabric_infill(
        morphology_field=field,
        street_pattern=str(field["morphology_street_pattern"]),
    )

    assert first == second
    assert first["strategy"] == expected_strategy
    assert first["segment_count"] == expected_count


def test_river_continuous_fabric_requires_barrier_metadata() -> None:
    from metroflow.city.continuous_fabric import build_continuous_fabric_infill
    from metroflow.city.morphology_field import build_morphology_field

    field = build_morphology_field(
        scenario_id="synthetic_smoke",
        seed=17,
        style_id="river_constrained",
        width=4_400,
        height=4_000,
    )
    without_barrier = dict(field)
    without_barrier["barrier_polylines"] = ()

    with pytest.raises(ValueError, match="requires a valid barrier"):
        build_continuous_fabric_infill(
            morphology_field=without_barrier,
            street_pattern="corridor_constrained",
        )
    with pytest.raises(ValueError, match="unsupported continuous-fabric"):
        build_continuous_fabric_infill(
            morphology_field=field,
            street_pattern="unknown_pattern",
        )


def test_integrated_river_local_roads_do_not_cross_barrier() -> None:
    from metroflow.city.generator_v2 import GeneratorV2
    from metroflow.city.graph import RoadClass

    topology = GeneratorV2().generate_preview_topology(
        {
            "scenario_id": "synthetic_smoke",
            "seed": 17,
            "preview_mode": "sidecar_local_fabric_planar",
            "style_id": "river_constrained",
        }
    )
    barriers = tuple(
        tuple((float(point[0]), float(point[1])) for point in polyline)
        for polyline in topology.metadata["barrier_polylines"]
        if len(polyline) >= 2
    )
    assignments_by_geometry: dict[int, list[object]] = defaultdict(list)
    for assignment in topology.road_geometry.assignments:
        assignments_by_geometry[assignment.geometry_id].append(assignment)
    link_by_id = {link.link_id: link for link in topology.links}
    local_crossings = 0
    bridge_crossings = 0
    for centerline in topology.road_geometry.centerlines:
        assignment = min(
            assignments_by_geometry[centerline.geometry_id],
            key=lambda item: item.link_id,
        )
        road_class = link_by_id[assignment.link_id].road_class
        crosses = any(
            _independent_polylines_intersect(centerline.points_m, barrier)
            for barrier in barriers
        )
        local_crossings += int(crosses and road_class == RoadClass.LOCAL)
        bridge_crossings += int(crosses and road_class == RoadClass.BRIDGE)

    assert local_crossings == 0
    assert bridge_crossings > 0


def test_continuous_fabric_import_does_not_load_accelerators() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import metroflow.city.continuous_fabric; "
                "assert 'jax' not in sys.modules; "
                "assert 'torch' not in sys.modules; "
                "assert '_metroflow_rust' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def _independent_polylines_intersect(
    left: tuple[tuple[float, float], ...],
    right: tuple[tuple[float, float], ...],
) -> bool:
    return any(
        _independent_segments_intersect(a, b, c, d)
        for a, b in zip(left, left[1:])
        for c, d in zip(right, right[1:])
    )


def _independent_segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> bool:
    def cross(
        origin: tuple[float, float],
        left: tuple[float, float],
        right: tuple[float, float],
    ) -> float:
        return (left[0] - origin[0]) * (right[1] - origin[1]) - (
            left[1] - origin[1]
        ) * (right[0] - origin[0])

    values = (cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b))
    return values[0] * values[1] <= 0.0 and values[2] * values[3] <= 0.0 and (
        max(min(a[0], b[0]), min(c[0], d[0]))
        <= min(max(a[0], b[0]), max(c[0], d[0])) + 1e-9
        and max(min(a[1], b[1]), min(c[1], d[1]))
        <= min(max(a[1], b[1]), max(c[1], d[1])) + 1e-9
    )
