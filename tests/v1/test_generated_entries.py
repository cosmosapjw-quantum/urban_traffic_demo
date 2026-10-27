"""Synthetic construction and resident ledger, distinct from source inventory."""
from types import SimpleNamespace

import pytest

from metroflow.v1.access_audit import fixture_city
from metroflow.v1.city import CityContractError, compile_city
from metroflow.v1.generated_entries import generate_entries, _components


def test_components_respect_directed_turns_not_undirected_contact():
    net = SimpleNamespace(roads=[SimpleNamespace(id=x) for x in 'abcd'],
                          allowed_turns=[('a', 'b'), ('a', 'c'), ('c', 'b'), ('b', 'd'), ('d', 'b')])
    assert set(_components(net)) == {frozenset('a'), frozenset('c'), frozenset('bd')}


def test_new_entrance_has_verified_corridor_and_preserves_source():
    original = fixture_city()
    city = compile_city(original.roadmap, original.landscape, original.face_graph.blocks)
    constructed, report = generate_entries(city)
    assert city.portals == ()
    assert constructed.identity != city.identity
    assert len(constructed.portals) == 1
    assert report['registered_served_residents'] == 1000
    assert report['registered_unserved_residents'] == 0
    assert report['registered_connectivity_status'] == 'PASS'
    assert report['registered_access_cdf'][-1][1] == pytest.approx(1)
    assert report['entries'][0]['capacity_veh_s'] == 1
    assert report['entries'][0]['existing'] is False
    assert report['entries'][0]['city_identity'] == constructed.identity
    assert report['entries'][0]['construction_length_m'] > 0
    for (_, lower), (_, estimate), (_, upper) in zip(
            report['registered_access_cdf_lower'], report['registered_access_cdf'],
            report['registered_access_cdf_upper']):
        assert 0 <= lower <= estimate <= upper <= 1
    with pytest.raises(CityContractError, match='portal-free'):
        generate_entries(constructed)


def test_unplaced_population_never_renormalizes_to_served():
    original = fixture_city()
    city = compile_city(original.roadmap, original.landscape, original.face_graph.blocks,
                        requested_population=1020, unplaced_residents=20)
    _, report = generate_entries(city)
    assert report['registered_unserved_residents'] == 20
    assert report['registered_access_status'] == 'PARTIAL_UNSERVED'
    assert report['registered_access_cdf'][-1][1] == pytest.approx(1000 / 1020)


def test_no_legal_turn_backbone_preserves_all_stock(monkeypatch):
    import metroflow.v1.generated_entries as generated
    original = fixture_city()
    city = compile_city(original.roadmap, original.landscape, original.face_graph.blocks)
    monkeypatch.setattr(generated, '_components', lambda net: [])
    result, report = generate_entries(city)
    assert not result.portals
    assert report['registered_served_residents'] == 0
    assert report['registered_unserved_residents'] == 1000
    assert report['registered_connectivity_status'] == 'PARTIAL_UNSERVED'
    assert all(value == 0 for _, value in report['registered_access_cdf'])


def test_portal_only_update_matches_full_compile_and_rejects_bad_contact():
    from dataclasses import replace
    from metroflow.v1.city import PortalRef
    original = fixture_city()
    source = compile_city(original.roadmap, original.landscape, original.face_graph.blocks)
    updated = source.with_portals(reversed(original.portals))
    full = compile_city(source.roadmap, source.landscape, source.face_graph.blocks,
                        original.portals)
    assert updated.identity == full.identity
    assert updated.to_dict() == full.to_dict()
    assert updated.transport_graph is source.transport_graph
    with pytest.raises(CityContractError, match='ground node'):
        source.with_portals((PortalRef('invalid', 'block', 'absent'),))
    with pytest.raises(CityContractError, match='unmodified'):
        replace(source, identity='stale').with_portals(())
