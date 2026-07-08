from __future__ import annotations

import sys

import pytest

from metroflow.city import GeneratorV2
from metroflow.sim.config import CityGenerationConfig, SimulationConfig


def test_zoning_generates_valid_pois_from_root_preview_topology_without_donor_path() -> None:
    assert not any(path.endswith("/metro/src") for path in sys.path)

    from metroflow.city.zones import POIType, generate_zones_and_pois

    topology = GeneratorV2().generate_preview_topology(
        {"scenario_id": "synthetic_smoke", "seed": 11}
    )

    zoning = generate_zones_and_pois(
        topology,
        CityGenerationConfig(poi_density_profile="sparse"),
        seed=11,
        population_target=1_200,
    )

    assert zoning.validate(topology=topology) == ()
    assert len(zoning.zones) == 4
    assert set(zoning.node_zone_by_id) == {node.node_id for node in topology.nodes}
    assert {poi.poi_type for poi in zoning.pois} == {
        POIType.HOME,
        POIType.WORKPLACE,
        POIType.LEISURE,
    }
    assert zoning.metadata["population_target"] == 1_200


def test_population_generation_is_deterministic_and_respects_poi_capacity() -> None:
    from metroflow.city.zones import POIType, generate_zones_and_pois
    from metroflow.demand.population import generate_citizen_population

    topology = GeneratorV2().generate_preview_topology(
        {"scenario_id": "synthetic_smoke", "seed": 13}
    )
    zoning = generate_zones_and_pois(topology, seed=13, population_target=160)

    cfg = SimulationConfig(population_target=200)
    first = generate_citizen_population(zoning, cfg, seed=101, population_target=80)
    second = generate_citizen_population(zoning, cfg, seed=101, population_target=80)

    assert first == second
    assert first.metadata["citizen_count"] == len(first.citizens)
    assert first.metadata["citizen_count"] <= 80
    assert first.metadata["citizen_count_capped"] == int(first.metadata["citizen_count"] < 80)
    assert first.schedule_templates
    assert first.behavior_profiles

    poi_by_id = {poi.poi_id: poi for poi in zoning.pois}
    for citizen in first.citizens:
        assert poi_by_id[citizen.home_poi_id].poi_type == POIType.HOME
        if citizen.work_poi_id is not None:
            assert poi_by_id[citizen.work_poi_id].poi_type == POIType.WORKPLACE
        assert citizen.schedule_template_id in {
            template.schedule_template_id for template in first.schedule_templates
        }


def test_trip_requests_are_deterministic_and_activate_without_mutating_queued_requests() -> None:
    from metroflow.city.zones import generate_zones_and_pois
    from metroflow.demand.population import generate_citizen_population
    from metroflow.demand.trips import (
        TripRequestStatus,
        activate_trip_requests,
        generate_trip_requests,
    )
    from metroflow.sim.config import DayType, TimeBand

    topology = GeneratorV2().generate_preview_topology(
        {"scenario_id": "synthetic_smoke", "seed": 17}
    )
    zoning = generate_zones_and_pois(topology, seed=17, population_target=120)
    population = generate_citizen_population(zoning, seed=17, population_target=40)

    first = generate_trip_requests(
        population,
        zoning,
        seed=202,
        day_type=DayType.WEEKDAY,
        time_band=TimeBand.MORNING,
        start_tick=300,
        jitter_max_ticks=0,
    )
    second = generate_trip_requests(
        population,
        zoning,
        seed=202,
        day_type="weekday",
        time_band="morning",
        start_tick=300,
        jitter_max_ticks=0,
    )

    assert first == second
    assert first.trip_requests
    assert {trip.status for trip in first.trip_requests} == {TripRequestStatus.QUEUED}
    assert all(trip.origin_poi_id != trip.dest_poi_id for trip in first.trip_requests)

    not_due = activate_trip_requests(first.trip_requests, current_tick=299)
    due = activate_trip_requests(first.trip_requests, current_tick=300)

    assert not_due is first.trip_requests
    assert {trip.status for trip in due} == {TripRequestStatus.ACTIVATED}
    assert {trip.status for trip in first.trip_requests} == {TripRequestStatus.QUEUED}


def test_population_generation_rejects_zoning_without_home_pois() -> None:
    from metroflow.city.zones import POI, POIType, Zone, ZoningPlacementResult
    from metroflow.demand.population import generate_citizen_population
    from metroflow.sim.config import ZoneType

    zoning = ZoningPlacementResult(
        zones=(
            Zone(
                zone_id=1,
                zone_type=ZoneType.CBD_COMMERCIAL,
                centroid_x=0.0,
                centroid_y=0.0,
                population_capacity=10,
                job_capacity=10,
                leisure_capacity=10,
            ),
        ),
        pois=(POI(poi_id=1, zone_id=1, poi_type=POIType.WORKPLACE, node_id=1),),
        node_zone_by_id={1: 1},
        zone_node_ids={1: (1,)},
    )

    with pytest.raises(ValueError, match="at least one home POI"):
        generate_citizen_population(zoning, population_target=5)
