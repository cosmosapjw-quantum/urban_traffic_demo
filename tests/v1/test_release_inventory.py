"""Fixed geometric fleet has physical endpoints and no OD-derived capacity."""
from dataclasses import replace

import pytest

from metroflow.v1.city import CityContractError
from metroflow.v1.release_inventory import InventoryPolicy, build_inventory
from metroflow.v1.scenarios import scenario_city


def test_fixed_inventory_validates_routes_and_registry_order_is_irrelevant():
    city = scenario_city(1000)
    policy = InventoryPolicy(departures_s=(100., 200.))
    inventory = build_inventory(city, policy)
    permuted = replace(city, portals=tuple(reversed(city.portals)),
                       face_graph=replace(city.face_graph, blocks=tuple(reversed(city.face_graph.blocks))),
                       roadmap=replace(city.roadmap, nodes=tuple(reversed(city.roadmap.nodes))))
    assert build_inventory(permuted, policy) == inventory
    assert inventory.city_identity == city.identity
    assert inventory.physical_run_vehicles == 4
    assert inventory.depot_block_id == inventory.stops[0][0]
    assert {c.origin_block for c in inventory.corridors} == {s[0] for s in inventory.stops}
    assert all(c.capacity_persons == 40 for c in inventory.corridors)
    assert inventory.corridors[0].origin_block != inventory.corridors[0].destination_block


def test_policy_change_changes_identity_and_invalid_inputs_fail_explicitly():
    city = scenario_city(1000)
    first = build_inventory(city)
    changed = build_inventory(city, {'capacity_persons': 20})
    assert first.identity != changed.identity
    assert first.stops == changed.stops
    for policy in ({'max_stops': True}, {'departures_s': (100., 100.)},
                   {'capacity_persons': 0}, {'dwell_s': -1}, {'departures_s': (86400.,)},
                   {'departures_s': None}, {'capacity_persons': None}, {'departures_s': ('bad',)},
                   {'unknown': 1}):
        with pytest.raises(CityContractError):
            build_inventory(city, policy)
    with pytest.raises(CityContractError, match='run budget'):
        build_inventory(city, {'max_runs': 1})
    with pytest.raises(CityContractError, match='two distinct'):
        build_inventory(city.with_portals(city.portals[:1]))


def test_inventory_does_not_expand_to_match_resident_or_opportunity_demand():
    small = build_inventory(scenario_city(1000))
    large = build_inventory(scenario_city(2000))
    assert small.stops == large.stops
    assert small.corridors == large.corridors
    assert small.identity != large.identity  # physical supply tied to its own city snapshot
