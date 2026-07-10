from __future__ import annotations

import textwrap


OSM_FIXTURE = textwrap.dedent(
    """\
    <?xml version="1.0" encoding="UTF-8"?>
    <osm version="0.6" generator="metroflow-test">
      <node id="1" lat="37.0000" lon="127.0000" />
      <node id="2" lat="37.0000" lon="127.0010" />
      <node id="3" lat="37.0000" lon="127.0020" />
      <node id="4" lat="36.9990" lon="127.0010" />
      <node id="5" lat="37.0010" lon="127.0010" />
      <node id="6" lat="37.0005" lon="127.0025" />
      <node id="7" lat="37.0000" lon="127.0030" />
      <way id="100">
        <nd ref="1"/><nd ref="2"/><nd ref="3"/>
        <tag k="highway" v="primary"/>
        <tag k="lanes" v="4"/>
        <tag k="maxspeed" v="60"/>
        <tag k="name" v="Main Avenue"/>
      </way>
      <way id="200">
        <nd ref="4"/><nd ref="2"/><nd ref="5"/>
        <tag k="highway" v="residential"/>
      </way>
      <way id="300">
        <nd ref="3"/><nd ref="6"/><nd ref="7"/>
        <tag k="highway" v="motorway_link"/>
        <tag k="oneway" v="yes"/>
        <tag k="lanes" v="1"/>
      </way>
      <way id="900">
        <nd ref="1"/><nd ref="4"/>
        <tag k="highway" v="footway"/>
      </way>
    </osm>
    """
)


def test_osm_import_projects_splits_and_classifies_supported_ways() -> None:
    from metroflow.city.graph import RoadClass
    from metroflow.map.osm_import import import_osm_xml_text

    result = import_osm_xml_text(OSM_FIXTURE, source_name="fixture.osm")

    assert len(result.road_geometry.centerlines) == 5
    assert len(result.links) == 9
    assert len(result.road_sections.assignments) == len(result.links)
    assert result.metadata["included_way_count"] == 3
    assert result.metadata["skipped_way_count"] == 1
    assert result.metadata["split_physical_road_count"] == 5
    assert result.metadata["projection"] == "local_equirectangular"
    assert result.metadata["source_name"] == "fixture.osm"
    assert {link.road_class for link in result.links} == {
        RoadClass.LOCAL,
        RoadClass.ARTERIAL,
        RoadClass.RAMP,
    }
    ramp_links = [link for link in result.links if link.road_class is RoadClass.RAMP]
    assert len(ramp_links) == 1
    assert ramp_links[0].lanes == 1
    assert all(centerline.source.value == "osm" for centerline in result.road_geometry.centerlines)
    assert any("way:100" in centerline.source_ref for centerline in result.road_geometry.centerlines)


def test_osm_import_preserves_curve_points_and_simplifies_in_meter_space() -> None:
    from metroflow.map.osm_import import OSMImportConfig, import_osm_xml_text

    curved = textwrap.dedent(
        """\
        <osm version="0.6">
          <node id="1" lat="37.0" lon="127.0"/>
          <node id="2" lat="37.00001" lon="127.001"/>
          <node id="3" lat="37.0" lon="127.002"/>
          <way id="10"><nd ref="1"/><nd ref="2"/><nd ref="3"/>
            <tag k="highway" v="secondary"/></way>
        </osm>
        """
    )

    unsimplified = import_osm_xml_text(curved)
    simplified = import_osm_xml_text(
        curved,
        config=OSMImportConfig(simplify_tolerance_m=2.0),
    )

    assert len(unsimplified.road_geometry.centerlines[0].points_m) == 3
    assert len(simplified.road_geometry.centerlines[0].points_m) == 2
    assert unsimplified.road_geometry.centerlines[0].length_m > 170.0


def test_osm_import_clips_centerlines_to_meter_bounds() -> None:
    from metroflow.map.osm_import import OSMImportConfig, import_osm_xml_text

    result = import_osm_xml_text(
        OSM_FIXTURE,
        config=OSMImportConfig(clip_bounds_m=(-45.0, -45.0, 45.0, 45.0)),
    )

    assert result.road_geometry.centerlines
    assert result.metadata["clip_bounds_m"] == (-45.0, -45.0, 45.0, 45.0)
    assert all(
        -45.000001 <= coordinate <= 45.000001
        for centerline in result.road_geometry.centerlines
        for point in centerline.points_m
        for coordinate in point
    )


def test_osm_import_is_deterministic_and_has_no_optional_runtime_imports() -> None:
    from pathlib import Path
    import subprocess
    import sys

    from metroflow.map.osm_import import import_osm_xml_text

    first = import_osm_xml_text(OSM_FIXTURE)
    second = import_osm_xml_text(OSM_FIXTURE)
    source_root = Path(__file__).resolve().parents[1] / "src"
    code = (
        f"import sys; sys.path.insert(0, {str(source_root)!r}); "
        "import metroflow.map; "
        "banned=('osmnx','networkx','requests'); "
        "assert not any(name.startswith(banned) for name in sys.modules)"
    )
    subprocess.run([sys.executable, "-I", "-c", code], check=True)

    assert first.fingerprint == second.fingerprint
    assert first.road_geometry.fingerprint == second.road_geometry.fingerprint
    assert first.road_sections.fingerprint == second.road_sections.fingerprint
    assert first.metadata["source_sha256"] == second.metadata["source_sha256"]


def test_osm_import_fails_closed_for_missing_reference_and_bad_numeric_tag() -> None:
    import pytest

    from metroflow.map.osm_import import import_osm_xml_text

    missing = """
    <osm version="0.6"><node id="1" lat="0" lon="0"/>
      <way id="2"><nd ref="1"/><nd ref="99"/><tag k="highway" v="primary"/></way>
    </osm>
    """
    malformed = OSM_FIXTURE.replace('v="4"', 'v="four"', 1)

    with pytest.raises(ValueError, match="missing node reference 99"):
        import_osm_xml_text(missing)
    with pytest.raises(ValueError, match="lanes"):
        import_osm_xml_text(malformed)


def test_osm_file_import_reads_only_the_supplied_local_path(tmp_path) -> None:
    import hashlib

    from metroflow.map.osm_import import import_osm_xml_file

    path = tmp_path / "fixture.osm"
    source_bytes = OSM_FIXTURE.replace("\n", "\r\n").encode("utf-8")
    path.write_bytes(source_bytes)

    result = import_osm_xml_file(path)

    assert result.metadata["source_name"] == "fixture.osm"
    assert result.metadata["source_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert result.links


def test_osm_import_preserves_distinct_source_node_identity_at_same_coordinate() -> None:
    from metroflow.map.osm_import import import_osm_xml_text

    xml = """
    <osm version="0.6">
      <node id="1" lat="37.0" lon="127.0"/>
      <node id="2" lat="37.0" lon="127.001"/>
      <node id="3" lat="37.0" lon="127.0"/>
      <node id="4" lat="37.001" lon="127.0"/>
      <way id="10"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/></way>
      <way id="20"><nd ref="3"/><nd ref="4"/><tag k="highway" v="residential"/></way>
    </osm>
    """

    result = import_osm_xml_text(xml)

    assert len(result.nodes) == 4
    assert len(result.road_geometry.centerlines) == 2


def test_osm_lane_tags_are_validated_as_consistent_total_and_directions() -> None:
    import pytest

    from metroflow.map.osm_import import import_osm_xml_text

    template = """
    <osm version="0.6">
      <node id="1" lat="37.0" lon="127.0"/>
      <node id="2" lat="37.0" lon="127.001"/>
      <way id="10"><nd ref="1"/><nd ref="2"/><tag k="highway" v="primary"/>
        {tags}
      </way>
    </osm>
    """

    with pytest.raises(ValueError, match="bidirectional total lanes"):
        import_osm_xml_text(template.format(tags='<tag k="lanes" v="1"/>'))
    with pytest.raises(ValueError, match="lanes must"):
        import_osm_xml_text(
            template.format(
                tags=(
                    '<tag k="lanes" v="bad"/><tag k="lanes:forward" v="1"/>'
                    '<tag k="lanes:backward" v="1"/>'
                )
            )
        )
    with pytest.raises(ValueError, match="sum to total"):
        import_osm_xml_text(
            template.format(
                tags=(
                    '<tag k="lanes" v="4"/><tag k="lanes:forward" v="3"/>'
                    '<tag k="lanes:backward" v="2"/>'
                )
            )
        )

    result = import_osm_xml_text(
        template.format(
            tags='<tag k="lanes" v="3"/><tag k="lanes:forward" v="2"/>'
        )
    )
    assert [link.lanes for link in result.links] == [2, 1]


def test_osm_closed_roundabout_and_implicit_motorway_oneway_are_supported() -> None:
    from metroflow.map.osm_import import import_osm_xml_text

    xml = """
    <osm version="0.6">
      <node id="1" lat="37.0" lon="127.0"/>
      <node id="2" lat="37.0" lon="127.001"/>
      <node id="3" lat="37.001" lon="127.001"/>
      <node id="4" lat="37.001" lon="127.0"/>
      <node id="5" lat="37.002" lon="127.0"/>
      <node id="6" lat="37.002" lon="127.001"/>
      <way id="10"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/>
        <tag k="highway" v="secondary"/><tag k="junction" v="roundabout"/>
      </way>
      <way id="20"><nd ref="5"/><nd ref="6"/><tag k="highway" v="motorway"/></way>
    </osm>
    """

    result = import_osm_xml_text(xml)

    assert len(result.road_geometry.centerlines) == 5
    assert len(result.links) == 5
    assert all(assignment.reversed is False for assignment in result.road_geometry.assignments)


def test_osm_projection_unwraps_small_antimeridian_extract() -> None:
    from metroflow.map.osm_import import import_osm_xml_text

    xml = """
    <osm version="0.6">
      <node id="1" lat="0.0" lon="179.999"/>
      <node id="2" lat="0.0" lon="-179.999"/>
      <way id="10"><nd ref="1"/><nd ref="2"/><tag k="highway" v="primary"/></way>
    </osm>
    """

    result = import_osm_xml_text(xml)

    assert result.road_geometry.centerlines[0].length_m < 500.0
    assert result.metadata["longitude_unwrapped"] is True


def test_osm_version_and_exact_input_hash_are_provenance_bound() -> None:
    import pytest

    from metroflow.map.osm_import import import_osm_xml_text

    first = import_osm_xml_text(OSM_FIXTURE)
    changed = import_osm_xml_text(OSM_FIXTURE.replace("Main Avenue", "Other Avenue"))

    assert first.metadata["source_format"] == "osm_xml_0.6"
    assert first.metadata["source_sha256"] != changed.metadata["source_sha256"]
    assert first.fingerprint != changed.fingerprint
    with pytest.raises(ValueError, match="unsupported OSM XML version"):
        import_osm_xml_text(OSM_FIXTURE.replace('version="0.6"', 'version="0.5"', 1))


def test_osm_import_rejects_zero_length_source_edges_before_clipping() -> None:
    import pytest

    from metroflow.map.osm_import import import_osm_xml_text

    xml = """
    <osm version="0.6">
      <node id="1" lat="37.0" lon="127.0"/>
      <node id="2" lat="37.0" lon="127.0"/>
      <node id="3" lat="37.0" lon="127.001"/>
      <way id="10"><nd ref="1"/><nd ref="2"/><nd ref="3"/>
        <tag k="highway" v="primary"/>
      </way>
    </osm>
    """

    with pytest.raises(ValueError, match="zero-length source edge"):
        import_osm_xml_text(xml)
