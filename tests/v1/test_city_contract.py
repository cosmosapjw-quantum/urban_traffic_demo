"""M02 observable contracts; engineering priors inherited, no new flow solver."""

from dataclasses import asdict, replace
import json
import math

import pytest

from metroflow.environment.terrain import Terrain
from metroflow.restored_city import Junction, RoadMap, Section
from metroflow.restored_traffic import compile_traffic
from metroflow.terrain_city.landscape import Landscape, Polygon
from metroflow.v1.city import CityContractError, PortalRef, compile_city, load_city


def section(key, a, b, facility="surface", lanes=(1, 1), group=None, role=None):
    return Section(
        key,
        a.id,
        b.id,
        (a.xyz, b.xyz),
        "expressway" if facility == "mainline" else "local",
        facility,
        *lanes,
        math.dist(a.xyz, b.xyz),
        abs(a.xyz[2] - b.xyz[2]) / math.dist(a.xyz[:2], b.xyz[:2]),
        group,
        role,
    )


def bridge_city():
    a, b, c = (
        Junction(k, p)
        for k, p in [("a", (10.0, 20.0, 0.0)), ("b", (110.0, 20.0, 0.0)), ("c", (210.0, 20.0, 0.0))]
    )
    return RoadMap(
        "bridge",
        Terrain(1, 1000.0, (0.0,) * 4),
        (a, b, c),
        (section("ab", a, b), section("bc", b, c, "bridge", group="physical-bridge")),
    )


def test_snapshot_preserves_compiler_and_closes_both_bridge_directions():
    city = compile_city(bridge_city())
    assert city.transport_graph == compile_traffic(city.roadmap, signals=False)
    assert set(city.closure_links("physical-bridge")) == {"bc|0", "bc|1"}
    assert city.reachable("a") == {"a", "b", "c"}
    assert city.reachable("a", ("physical-bridge",)) == {"a", "b"}
    assert city.reachable("c", ("physical-bridge",)) == {"c"}
    assert city.report()["bridge_closures"][0]["reachable_after"] < 3
    with pytest.raises(CityContractError, match="unknown structure"):
        city.reachable("a", ("not-a-bridge",))


def test_json_roundtrip_and_registry_permutation_are_exact():
    c = bridge_city()
    a = compile_city(c)
    b = compile_city(replace(c, nodes=c.nodes[::-1], sections=c.sections[::-1]))
    assert a.identity == b.identity
    assert load_city(json.loads(json.dumps(a.to_dict()))).identity == a.identity
    data = a.to_dict()
    data["roadmap"]["sections"][0]["forward_lanes"] = 2
    with pytest.raises(CityContractError, match="identity"):
        load_city(data)


def test_inconsistent_length_and_grade_are_rejected():
    c = bridge_city()
    for change in ({"length_m": 1000.0}, {"max_grade": 0.1}):
        bad = replace(c, sections=(replace(c.sections[0], **change), c.sections[1]))
        with pytest.raises(CityContractError, match="inconsistent"):
            compile_city(bad)


def test_ground_crossing_rejected_while_elevated_projection_has_no_turn():
    a, b, x, y = (
        Junction(k, p, layer)
        for k, p, layer in [
            ("a", (10.0, 50.0, 0.0), 0),
            ("b", (110.0, 50.0, 0.0), 0),
            ("x", (60.0, 10.0, 10.0), 1),
            ("y", (60.0, 110.0, 10.0), 1),
        ]
    )
    road = RoadMap(
        "cross",
        Terrain(1, 1000.0, (0.0,) * 4),
        (a, b, x, y),
        (section("ground", a, b), section("upper", x, y, "mainline", (2, 0), "deck")),
    )
    s = compile_city(road)
    assert not any(
        b.startswith("upper") for a, b in s.transport_graph.allowed_turns if a.startswith("ground")
    )
    assert [e[0] for e in s.face_graph.edges] == ["ground"]
    assert "y" not in s.reachable("a")
    bad = replace(
        road,
        nodes=(
            a,
            b,
            replace(x, xyz=(60.0, 10.0, 0.0), layer=0),
            replace(y, xyz=(60.0, 110.0, 0.0), layer=0),
        ),
    )
    bad = replace(bad, sections=(road.sections[0], section("cross", bad.nodes[2], bad.nodes[3])))
    with pytest.raises(CityContractError, match="illegal crossing"):
        compile_city(bad)


def test_unregistered_same_xy_is_not_a_junction():
    c = bridge_city()
    node = Junction("other", c.nodes[1].xyz)
    d = Junction("d", (110.0, 120.0, 0.0))
    bad = replace(c, nodes=c.nodes + (node, d), sections=c.sections + (section("alien", node, d),))
    with pytest.raises(CityContractError, match="illegal crossing"):
        compile_city(bad)


def test_polygon_authority_is_not_replaced_by_empty_legacy_rectangles():
    c = bridge_city()
    mask = Polygon("water", ((40.0, 10.0), (60.0, 10.0), (60.0, 30.0), (40.0, 30.0)))
    assert not c.terrain.water
    with pytest.raises(CityContractError, match="PHYSICAL_INFEASIBLE.*water"):
        compile_city(c, Landscape("typed", 7, c.terrain, (mask,), ()))


def test_budget_is_explicit_and_not_silently_truncated():
    with pytest.raises(CityContractError, match="BLOCKED_RESOURCE"):
        compile_city(bridge_city(), group_budget=3)
    for v in (0, True, 10001):
        with pytest.raises(CityContractError):
            compile_city(bridge_city(), group_budget=v)


def test_interchange_uses_same_snapshot_and_compiler_without_layer_teleport():
    from test_restored_traffic import interchange

    c = compile_city(interchange())
    assert c.reachable("O") == {"O", "A", "H", "I", "B", "D"}
    assert "O" not in c.reachable("D")
    bad = interchange()
    bad = replace(
        bad,
        sections=tuple(replace(s, backward_lanes=1) if s.id == "on" else s for s in bad.sections),
    )
    with pytest.raises(CityContractError, match="ramp"):
        compile_city(bad)


def test_atlas_json_retains_faces_stocks_and_declared_portals():
    from metroflow.terrain_city.network import generate

    a = generate("polycentric", "flat", 8000.0, 12, 7, population=100000000)
    c = load_city(json.loads(json.dumps(asdict(a))))
    assert len(c.face_graph.blocks) == len(a.blocks)
    assert c.report()["status"] == "PHYSICAL_INFEASIBLE"
    assert c.requested_population == sum(b.residents for b in a.blocks) + c.unplaced_residents
    b = c.face_graph.blocks[0]
    p = compile_city(
        c.roadmap,
        c.landscape,
        c.face_graph.blocks,
        (PortalRef("gate", b.id, b.boundary[0]),),
        requested_population=c.requested_population,
        unplaced_residents=c.unplaced_residents,
    )
    assert p.portals[0].block_id == b.id
    assert p.identity != c.identity
    with pytest.raises(CityContractError, match="portal"):
        compile_city(
            c.roadmap, c.landscape, c.face_graph.blocks, (PortalRef("gate", b.id, "missing"),)
        )


def test_mutable_nested_inputs_are_rejected_before_snapshot_is_cached():
    c = bridge_city()
    with pytest.raises(CityContractError, match="immutable"):
        compile_city(replace(c, nodes=list(c.nodes)))


def test_directional_registry_has_no_id_derived_signal_phase():
    c = bridge_city()
    renamed = replace(
        c,
        nodes=tuple(replace(n, id="new:" + n.id) for n in reversed(c.nodes)),
        sections=tuple(
            replace(s, id="new:" + s.id, start="new:" + s.start, end="new:" + s.end)
            for s in reversed(c.sections)
        ),
    )
    a, b = compile_city(c), compile_city(renamed)
    assert a.identity != b.identity
    assert all(r.signal is None for r in a.transport_graph.roads + b.transport_graph.roads)
    assert {k.removeprefix("new:") for k in b.reachable("new:a")} == a.reachable("a")
    assert a.report()["storage_veh"] == b.report()["storage_veh"]


def test_cli_input_json_returns_a_typed_report(tmp_path):
    import os
    import subprocess
    import sys

    source = tmp_path / "city.json"
    source.write_text(json.dumps(compile_city(bridge_city()).to_dict()))
    result = subprocess.run(
        [sys.executable, "-m", "metroflow.v1", "validate-city", "--input", str(source)],
        env=dict(os.environ),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["cases"][0]["directed_groups"] == 4
    source.write_text("{}")
    bad = subprocess.run(
        [sys.executable, "-m", "metroflow.v1", "validate-city", "--input", str(source)],
        capture_output=True,
        text=True,
    )
    assert bad.returncode == 2
    assert json.loads(bad.stdout)["status"] == "MODEL_ERROR"


def test_overlapping_decks_check_minimum_clearance_not_midpoint_only():
    a, b, c, d = (
        Junction(k, p, 1)
        for k, p in (
            ("a", (10.0, 50.0, 10.0)),
            ("b", (210.0, 50.0, 10.0)),
            ("c", (30.0, 50.0, 10.0)),
            ("d", (230.0, 50.0, 30.0)),
        )
    )
    road = RoadMap(
        "overlap",
        Terrain(1, 1000.0, (0.0,) * 4),
        (a, b, c, d),
        (
            section("one", a, b, "mainline", (1, 0), "g1"),
            section("two", c, d, "mainline", (1, 0), "g2"),
        ),
    )
    with pytest.raises(CityContractError, match="illegal crossing"):
        compile_city(road)


def test_self_intersecting_section_and_buried_bridge_are_rejected():
    a, b = Junction("a", (10.0, 10.0, 0.0)), Junction("b", (110.0, 10.0, 0.0))
    pts = (a.xyz, (110.0, 110.0, 0.0), (10.0, 110.0, 0.0), b.xyz)
    s = Section(
        "bow",
        "a",
        "b",
        pts,
        "local",
        "bridge",
        1,
        1,
        sum(math.dist(x, y) for x, y in zip(pts, pts[1:])),
        0.0,
        "g",
    )
    road = RoadMap("bow", Terrain(1, 1000.0, (0.0,) * 4), (a, b), (s,))
    with pytest.raises(CityContractError, match="self crossing"):
        compile_city(road)
    c = bridge_city()
    lower = replace(
        c,
        nodes=tuple(replace(n, xyz=(n.xyz[0], n.xyz[1], -1.0)) for n in c.nodes),
        sections=tuple(
            replace(
                s,
                facility="bridge",
                failure_group="buried",
                points=tuple((x, y, -1.0) for x, y, z in s.points),
            )
            for s in c.sections
        ),
    )
    with pytest.raises(CityContractError, match="buried"):
        compile_city(lower)


def test_missing_cli_input_is_environment_failure(tmp_path):
    import subprocess
    import sys

    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "metroflow.v1",
            "validate-city",
            "--input",
            str(tmp_path / "missing.json"),
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 2
    assert json.loads(r.stdout)["status"] == "ENVIRONMENT_BLOCKER"
