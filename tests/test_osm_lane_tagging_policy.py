"""Real-world lane tagging the strict parser rejects as malformed.

Measured across seven offline extracts (4,923 drive-network ways), three valid
OSM tagging patterns trip `_parse_directional_lanes`. They are only 1.7% of
ways, but the import is fail-closed at file level, so one way aborts an entire
city: 6 of 7 extracts were unimportable.

Spec 039 FR-006 requires malformed numeric tags to fail closed. None of these
three are malformed under the OSM wiki data model, so interpreting them is
honoring FR-006 rather than weakening it. The strict default is preserved and
the interpretation is opt-in, so no existing contract changes.
"""

from __future__ import annotations

import pytest

TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="metroflow-test">
  <node id="1" lat="0.0000" lon="0.0000"/>
  <node id="2" lat="0.0000" lon="0.0020"/>
  <way id="10">
    <nd ref="1"/><nd ref="2"/>
    <tag k="highway" v="residential"/>
    {tags}
  </way>
</osm>
"""


def _import(tags: str, **kwargs):
    from metroflow.map.osm_import import OSMImportConfig, import_osm_xml_text

    config = OSMImportConfig(**kwargs) if kwargs else None
    return import_osm_xml_text(TEMPLATE.format(tags=tags), config=config)


def test_single_track_two_way_street_is_importable_under_the_wiki_policy() -> None:
    """`lanes=1` with no oneway is a single lane shared by both directions."""

    tags = '<tag k="lanes" v="1"/>'

    with pytest.raises(ValueError, match="bidirectional total lanes"):
        _import(tags)

    result = _import(tags, lane_tagging_policy="osm_wiki")

    assert [link.lanes for link in result.links] == [1, 1]
    assert result.metadata["lane_tagging_policy"] == "osm_wiki"
    assert result.metadata["lane_interpretation_counts"]["single_track_two_way"] == 1


def test_contraflow_lane_on_a_oneway_street_is_importable() -> None:
    """`oneway=yes` + `lanes:backward` is a contraflow bus/cycle lane.

    It carries no general motor traffic, so a drive network drops it rather
    than treating the way as invalid. `lanes` is the total including the
    contraflow lane, so 2 total minus 1 backward leaves 1 forward lane, and
    the way stays one-way.
    """

    tags = '<tag k="oneway" v="yes"/><tag k="lanes" v="2"/><tag k="lanes:backward" v="1"/>'

    with pytest.raises(ValueError, match="opposing direction"):
        _import(tags)

    result = _import(tags, lane_tagging_policy="osm_wiki")

    assert [link.lanes for link in result.links] == [1]
    assert result.metadata["lane_interpretation_counts"]["oneway_contraflow_ignored"] == 1


def test_partial_directional_tagging_defaults_the_untagged_side() -> None:
    """`lanes:forward` alone leaves the other direction implied, not invalid."""

    tags = '<tag k="lanes:forward" v="2"/>'

    with pytest.raises(ValueError, match="require both directions"):
        _import(tags)

    result = _import(tags, lane_tagging_policy="osm_wiki")

    assert [link.lanes for link in result.links] == [2, 1]
    assert result.metadata["lane_interpretation_counts"]["partial_directional"] == 1


def test_genuinely_contradictory_tags_still_fail_under_both_policies() -> None:
    """Relaxing valid patterns must not stop malformed data failing closed."""

    contradictory = (
        '<tag k="lanes" v="4"/><tag k="lanes:forward" v="3"/><tag k="lanes:backward" v="2"/>'
    )
    unparseable = '<tag k="lanes" v="bad"/>'

    for tags in (contradictory, unparseable):
        with pytest.raises(ValueError):
            _import(tags)
        with pytest.raises(ValueError):
            _import(tags, lane_tagging_policy="osm_wiki")


def test_strict_remains_the_default_policy() -> None:
    from metroflow.map.osm_import import OSMImportConfig

    assert OSMImportConfig().lane_tagging_policy == "strict"
    with pytest.raises(ValueError, match="lane_tagging_policy"):
        OSMImportConfig(lane_tagging_policy="lenient")
