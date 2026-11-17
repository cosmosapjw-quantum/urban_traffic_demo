"""Marginal frontend equivalence; these tests require no native extension."""

from dataclasses import asdict, replace
import json
import sys
from types import SimpleNamespace

import pytest

from metroflow.foundation_kinetics import VehicleClass
from metroflow.ordered_network import Route
from metroflow.v1.activity import ActivityPatch, compile_activity
from metroflow.v1.city import CityContractError, PortalRef
from metroflow.v1.factorized_demand import FactorizedSchedule, compile_factorized_demand
from metroflow.v1.native_road import NativeRoadNetwork
from metroflow.v1.native_static import prepare_native_static
from metroflow.v1.release_inventory import InventoryPolicy, build_inventory
from metroflow.v1.release_runtime import ReleaseRuntime
from metroflow.v1.release_services import compile_service_plan
from metroflow.v1.scenarios import scenario_city


def fixture(city=None):
    city = scenario_city(1000) if city is None else city
    # Two points in the same delay bin make maximum ingress differ from its
    # compressed mean; the service prior on this block is deliberately distinct.
    home = compile_activity(city, "block", patches=(
        ActivityPatch(500, ((309., 10.),)), ActivityPatch(500, ((309.4, 10.),)),
    ))
    job = compile_activity(city, "work", "job")
    service = compile_activity(city, "block", "service", service_stock=400,
                               patches=(ActivityPatch(400, ((20., 20.),)),))
    other_service = compile_activity(city, "work", "service", service_stock=400)
    schedule = compile_factorized_demand(
        (home,), (job,), (service, other_service), worker_fraction=.4, service_fraction=.3,
        school_share=.4, freight_kg=100, minimum_dwell_s=10,
    )
    inventory = build_inventory(city, InventoryPolicy(departures_s=(32400., 64800.)))
    return city, schedule, inventory


def label(value):
    return json.dumps(asdict(value), sort_keys=True, allow_nan=False)


def test_access_and_intrazonal_marginals_equal_small_calendar_oracles():
    city, schedule, inventory = fixture()
    payload = prepare_native_static(city, schedule, inventory)
    legs = tuple(schedule.iter_legs())
    cars = ReleaseRuntime(city, legs, step_s=10)
    services = compile_service_plan(city, legs, inventory.corridors,
                                    depot_block_id=inventory.depot_block_id, step_s=10)
    rows = {row[0]: row for row in payload["activities"]}
    by_id = {leg.id: leg for leg in legs}
    for leg_id, boundary in cars.model.boundaries.items():
        leg = by_id[leg_id]
        assert rows[label(leg.origin)][4] == boundary.origin.atoms
        assert rows[label(leg.destination)][4] == boundary.destination.atoms
    laws = dict(payload["intrazonal_laws"])
    for law in cars.internal_laws.values():
        assert laws[label(law)] == law.atoms
    for metadata in services.metadata:
        leg = by_id[metadata["leg_id"]]
        assert rows[label(leg.destination)][5] == metadata["destination_access"]
        if "origin_access" in metadata:
            assert rows[label(leg.origin)][5] == metadata["origin_access"]
    home, service = rows[label(schedule.homes[0])], rows[label(schedule.services[0])]
    assert home[1] == service[1]
    assert home[4] != service[4]  # full measure, not block ID, keys the law
    assert home[6] > max(delay for delay, _ in home[5])
    assert payload["corridor_routes"] == [(b.id, list(b.legs[0])) for b in services.buses]


def test_no_python_leg_expansion_and_exact_measure_access_computed_once(monkeypatch):
    import metroflow.v1.native_static as module

    city, schedule, inventory = fixture()
    calls = []
    actual = module.activity_access

    def counted(measure, *args, **kwargs):
        calls.append(measure)
        return actual(measure, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("static frontend must not enumerate calendar legs")

    monkeypatch.setattr(module, "activity_access", counted)
    monkeypatch.setattr(FactorizedSchedule, "iter_legs", forbidden)
    monkeypatch.setattr(FactorizedSchedule, "iter_records", forbidden)
    payload = prepare_native_static(city, schedule, inventory)
    assert len(calls) == len(set(calls)) == 4
    assert len(payload["activities"]) == 4
    assert payload["class_names"] == ["car", "freight", "scheduled_bus"]
    assert len(payload["intrazonal_laws"]) == 1


def test_road_primitives_match_existing_native_adapter(monkeypatch):
    city, schedule, inventory = fixture()
    payload = prepare_native_static(city, schedule, inventory, record_budget=4321)
    plan = compile_service_plan(city, tuple(schedule.iter_legs()), inventory.corridors,
                                depot_block_id=inventory.depot_block_id, step_s=10)
    first = plan.contract.groups[0].id
    reference = plan.model(
        traffic_routes=(Route("test-car", (first,)),),
        traffic_classes={"test-car": VehicleClass("car", preferred_mps=10)},
        record_budget=4321,
    ).network
    calls = []
    monkeypatch.setitem(sys.modules, "_metroflow_rust", SimpleNamespace(
        V1Road=lambda *args: calls.append(args),
    ))
    NativeRoadNetwork(reference)
    args, = calls
    assert payload["step_s"] == args[1]
    assert payload["groups"] == args[2]
    assert payload["signals"] == args[3]
    assert payload["classes"] == args[5]
    assert payload["incoming"] == args[6]
    assert payload["windows"] == args[7]
    assert (payload["record_budget"], payload["event_budget"],
            payload["preserve_entry_intervals"]) == args[8:11]


def test_multiple_portals_keep_service_door_but_disable_car_endpoint():
    city = scenario_city(1000)
    city = city.with_portals(city.portals + (PortalRef("second", "block", "0"),))
    city, schedule, inventory = fixture(city)
    payload = prepare_native_static(city, schedule, inventory)
    home = next(row for row in payload["activities"] if row[0] == label(schedule.homes[0]))
    assert home[2] is None and home[4] == ()
    assert home[3] == "0" and home[5]
    assert dict(payload["block_doors"])["block"] == "0"


def test_absent_door_stays_explicit_and_mismatched_snapshots_reject():
    city, schedule, inventory = fixture()
    # A marginal block without a door remains represented rather than dropped.
    absent = replace(schedule.jobs[0], block_id="unserved-declaration")
    changed = replace(schedule, jobs=(absent,), identity="unserved-schedule")
    payload = prepare_native_static(city, changed, inventory)
    missing = next(row for row in payload["activities"] if row[1] == absent.block_id)
    assert missing[2:] == (None, None, (), (), 0.0)
    assert payload["depot_node_or_None"] == dict(payload["block_doors"])[inventory.depot_block_id]
    for bad_schedule, bad_inventory in (
        (replace(schedule, city_identity="wrong"), inventory),
        (schedule, replace(inventory, city_identity="wrong")),
        (replace(schedule, jobs=(replace(schedule.jobs[0], city_identity="wrong"),)), inventory),
    ):
        with pytest.raises(CityContractError, match="identit|another city"):
            prepare_native_static(city, bad_schedule, bad_inventory)


def test_identity_covers_configuration_and_invalid_fleet_is_not_dropped():
    city, schedule, inventory = fixture()
    first = prepare_native_static(city, schedule, inventory)
    assert prepare_native_static(city, schedule, inventory) == first
    assert prepare_native_static(city, schedule, inventory, step_s=5)["identity"] != first["identity"]
    invalid = replace(inventory, corridors=(replace(
        inventory.corridors[0], destination_block=inventory.corridors[0].origin_block),))
    with pytest.raises(CityContractError, match="nonempty legal"):
        prepare_native_static(city, schedule, invalid)
