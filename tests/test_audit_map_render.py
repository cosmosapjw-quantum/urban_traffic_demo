"""Audit renders must show the whole graph and carry the numbers they belong to.

A picture is not evidence -- the claim ledger forbids presenting PNG or HTML
artifacts as scientific validation, and these renders are navigation aids for a
reviewer, nothing more. But an aid that quietly drops geometry, or that is
captioned with metrics measured from some other run, is worse than no picture:
it invites a conclusion the artifact does not support.

So three properties are locked here.

- **Nothing is dropped.** The count of drawn segments equals the count of links
  handed in. A renderer that skips degenerate or off-canvas geometry would make
  a severed network look whole, which is precisely the defect class this branch
  spent its length repairing.
- **The caption comes from the committed artifact**, never recomputed at render
  time. Recomputing invites a caption that disagrees with the control table
  while looking authoritative, and an absent case must raise rather than render
  an unlabelled map.
- **Byte-determinism.** The renders are committed, so a rerun that changes bytes
  without changing the graph would put noise in every future diff.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _render_module():
    spec = importlib.util.spec_from_file_location(
        "render_audit_maps_under_test", _REPO_ROOT / "tools" / "render_audit_maps.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Registered before exec: `@dataclass` resolves its own module out of
    # `sys.modules`, and a path-loaded module that never lands there fails there.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Node:
    def __init__(self, node_id: int, x: float, y: float) -> None:
        self.node_id = node_id
        self.x = x
        self.y = y


class _Link:
    def __init__(self, link_id: int, src: int, dst: int) -> None:
        self.link_id = link_id
        self.src_node_id = src
        self.dst_node_id = dst


def _square():
    nodes = [_Node(0, 0.0, 0.0), _Node(1, 100.0, 0.0), _Node(2, 100.0, 100.0), _Node(3, 0.0, 100.0)]
    links = [_Link(0, 0, 1), _Link(1, 1, 2), _Link(2, 2, 3), _Link(3, 3, 0)]
    return nodes, links


def test_every_link_handed_in_is_drawn() -> None:
    """A render that omits geometry makes a broken network look intact."""

    module = _render_module()
    nodes, links = _square()

    svg = module.render_svg(nodes=nodes, links=links, title="t", caption_lines=())

    assert svg.count("<line") == len(links), (
        f"drew {svg.count('<line')} segments for {len(links)} links"
    )


def test_a_degenerate_link_is_still_drawn_and_not_silently_skipped() -> None:
    """Zero-length links are exactly what a reviewer needs to see, not hide.

    Dropping them is how a duplicated node pair stops being visible at the one
    moment somebody is looking for duplicated node pairs.
    """

    module = _render_module()
    nodes = [_Node(0, 10.0, 10.0), _Node(1, 10.0, 10.0), _Node(2, 90.0, 90.0)]
    links = [_Link(0, 0, 1), _Link(1, 1, 2)]

    svg = module.render_svg(nodes=nodes, links=links, title="t", caption_lines=())

    assert svg.count("<line") == 2


def test_all_geometry_lands_inside_the_view_box() -> None:
    """An off-canvas node is invisible, which reads as a node that is not there."""

    module = _render_module()
    nodes, links = _square()

    svg = module.render_svg(nodes=nodes, links=links, title="t", caption_lines=())

    box = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    assert box, "no viewBox"
    width, height = float(box.group(1)), float(box.group(2))
    coords = [float(value) for value in re.findall(r'(?:x1|x2|y1|y2)="([-\d.]+)"', svg)]
    assert coords
    assert all(-1e-6 <= value <= max(width, height) + 1e-6 for value in coords), (
        f"geometry escapes the {width}x{height} view box"
    )


def test_every_caption_line_lands_inside_the_canvas() -> None:
    """A caption that runs off the bottom takes the provenance with it.

    The viewBox check above reads `x1/x2/y1/y2`, which are line attributes only,
    so it was blind to text placement -- and the first render did clip its last
    line, the one saying the image measures nothing. Exactly the sentence that
    must not fall off.
    """

    module = _render_module()
    nodes, links = _square()
    caption = tuple(f"line {index}" for index in range(5))

    svg = module.render_svg(nodes=nodes, links=links, title="t", caption_lines=caption)

    box = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    assert box
    height = float(box.group(2))
    text_y = [float(value) for value in re.findall(r'<text[^>]*\sy="([\d.]+)"', svg)]
    assert len(text_y) == len(caption) + 1, "title plus one line each"
    assert max(text_y) <= height, (
        f"a caption line sits at y={max(text_y)} on a {height}-high canvas"
    )


def test_the_same_graph_renders_the_same_bytes() -> None:
    """These files are committed; a churning render poisons every future diff."""

    module = _render_module()
    nodes, links = _square()

    first = module.render_svg(nodes=nodes, links=links, title="t", caption_lines=("a", "b"))
    second = module.render_svg(nodes=nodes, links=links, title="t", caption_lines=("a", "b"))

    assert first == second


def test_a_caption_is_read_from_the_committed_artifact_not_recomputed() -> None:
    """The numbers on the map must be the numbers that were audited."""

    module = _render_module()
    scores = module.load_scores()

    record = scores[("growth_fabric_v1", "grid_core/17")]

    assert set(record["metrics"]) == {
        "circuity",
        "dead_end_share",
        "four_way_share",
        "mean_node_degree",
        "median_segment_length_m",
        "orientation_entropy",
        "orientation_order",
    }
    assert isinstance(record["passed"], bool)


def test_score_loader_rejects_duplicate_record_keys(tmp_path: Path) -> None:
    """A duplicate record must not be silently replaced by dict indexing."""
    module = _render_module()
    artifact = tmp_path / "duplicate-scores.json"
    artifact.write_text(
        json.dumps(
            {
                "scores": [
                    {"arm": "alpha", "case": "s17", "metrics": {}},
                    {"arm": "alpha", "case": "s17", "metrics": {}},
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate morphology score key"):
        module.load_scores(artifact)


def test_a_case_absent_from_the_artifact_raises_instead_of_rendering() -> None:
    """An unlabelled render is a picture with no provenance at all."""

    module = _render_module()
    scores = module.load_scores()

    with pytest.raises(KeyError):
        module.caption_for(scores, arm="growth_fabric_v1", case="no_such_style/999")


def test_the_render_set_is_not_only_the_arm_under_review() -> None:
    """A gallery of one arm cannot show a reviewer what failure looks like.

    The control table's value is the contrast: 30/30 for the growth arm against
    0/30 for `realistic_synthetic_v1` and 0/10 for the runtime default. Shipping
    only the winner is how a picture starts arguing.
    """

    module = _render_module()
    arms = {entry.arm for entry in module.RENDER_SET}

    assert "growth_fabric_v1" in arms
    assert len(arms) >= 3, f"the render set shows only {sorted(arms)}"


def test_renderer_verifies_topology_record_integrity() -> None:
    """Renderer must reject topology whose node count differs from the recorded score."""
    module = _render_module()
    nodes, links = _square()
    record = {
        "node_count": 999,  # does not match len(nodes) == 4
        "metrics": {
            "circuity": 1.0,
            "dead_end_share": 0.0,
            "four_way_share": 0.0,
            "mean_node_degree": 2.0,
            "median_segment_length_m": 100.0,
            "orientation_entropy": 1.0,
            "orientation_order": 0.5,
        },
        "passed": True,
        "failed_metrics": [],
        "physical_segment_count": 4,
    }

    class MockTopology:
        def __init__(self, node_list, link_list):
            self.nodes = node_list
            self.links = link_list

    with pytest.raises(ValueError, match="topology record identity mismatch"):
        module.verify_topology_record_integrity(
            MockTopology(nodes, links),
            record,
            arm="test_arm",
            case="test_case",
        )


def test_renderer_binds_metrics_to_exact_source_topology() -> None:
    """A same-count geometry mutation must not inherit a historical caption."""
    from metroflow.city.generated_map import PreviewCityTopology
    from metroflow.city.graph import Node, RoadClass, RoadLink
    from metroflow.city.morphology_control_table import score_street_morphology
    from metroflow.map.road_geometry import build_endpoint_geometry_catalog

    nodes = tuple(
        Node(index, x=x, y=y)
        for index, (x, y) in enumerate(
            ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0), (0.0, -100.0))
        )
    )
    pairs = ((0, 1), (1, 2), (2, 3), (3, 0), (0, 4))
    links = tuple(
        RoadLink(
            link_id=index * 2 + direction,
            src_node_id=pair[direction],
            dst_node_id=pair[1 - direction],
            road_class=RoadClass.LOCAL,
            length_m=100.0,
            free_flow_speed_mps=10.0,
            capacity_veh_per_tick=4.0,
            physical_road_id=index,
        )
        for index, pair in enumerate(pairs)
        for direction in (0, 1)
    )
    geometry = build_endpoint_geometry_catalog(nodes=nodes, links=links)
    topology = PreviewCityTopology(nodes=nodes, links=links, road_geometry=geometry)
    record = score_street_morphology(topology, arm="test_arm", case="c1").as_dict()

    assert len(record["source_topology_fingerprint"]) == 64
    module = _render_module()
    module.verify_topology_record_integrity(topology, record, arm="test_arm", case="c1")

    shifted_nodes = (Node(0, x=1.0, y=0.0),) + nodes[1:]
    shifted = PreviewCityTopology(
        nodes=shifted_nodes,
        links=links,
        road_geometry=geometry,
    )
    with pytest.raises(ValueError, match="topology record identity mismatch"):
        module.verify_topology_record_integrity(
            shifted,
            record,
            arm="test_arm",
            case="c1",
        )


def test_control_table_check_mode(tmp_path: Path) -> None:
    """Control table --check returns 0 when artifacts match and 1 on mismatch."""
    from metroflow.benchmarks.morphology_control_table import check_artifacts, build_morphology_control_table, score_street_morphology, write_artifacts
    from metroflow.city.generated_map import PreviewCityTopology
    from metroflow.city.graph import Node, RoadClass, RoadLink
    from metroflow.map.road_geometry import build_endpoint_geometry_catalog

    nodes = tuple(
        Node(index, x=x, y=y)
        for index, (x, y) in enumerate(
            ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0), (0.0, -100.0))
        )
    )
    pairs = ((0, 1), (1, 2), (2, 3), (3, 0), (0, 4))
    links = tuple(
        RoadLink(
            link_id=index * 2 + direction,
            src_node_id=pair[direction],
            dst_node_id=pair[1 - direction],
            road_class=RoadClass.LOCAL,
            length_m=100.0,
            free_flow_speed_mps=10.0,
            capacity_veh_per_tick=4.0,
            physical_road_id=index,
        )
        for index, pair in enumerate(pairs)
        for direction in (0, 1)
    )
    geometry = build_endpoint_geometry_catalog(nodes=nodes, links=links)
    topology = PreviewCityTopology(nodes=nodes, links=links, road_geometry=geometry)

    score = score_street_morphology(topology, arm="test_arm", case="c1")
    table = build_morphology_control_table([score])

    prefix = tmp_path / "table_test"
    write_artifacts(prefix, table=table, skipped=())

    ok, mismatches = check_artifacts(prefix, table=table, skipped=())
    assert ok is True
    assert not mismatches

    manifest_path = tmp_path / "table_test.manifest.json"
    original_manifest = manifest_path.read_bytes()
    manifest = json.loads(original_manifest)
    manifest["schema_version"] = "morphology_control_table_v0"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    ok, mismatches = check_artifacts(prefix, table=table, skipped=())
    assert ok is False
    assert "table_test.manifest.json: bytes changed" in mismatches

    manifest_path.write_bytes(original_manifest)
    manifest = json.loads(original_manifest)
    manifest["files"]["table_test.json"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    ok, mismatches = check_artifacts(prefix, table=table, skipped=())
    assert ok is False
    assert "table_test.manifest.json: bytes changed" in mismatches

    manifest_path.write_bytes(original_manifest)

    # Tamper markdown
    (tmp_path / "table_test.md").write_text("corrupted", encoding="utf-8")
    ok, mismatches = check_artifacts(prefix, table=table, skipped=())
    assert ok is False
    assert any("table_test.md: bytes changed" in m for m in mismatches)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__]))
