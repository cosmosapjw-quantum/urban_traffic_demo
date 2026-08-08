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


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__]))
