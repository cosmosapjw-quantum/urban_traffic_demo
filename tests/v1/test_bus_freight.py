import pickle
import pytest
from metroflow.v1.services import BusRun, PassengerCohort, FreightRun, ServiceModel
from metroflow.v1.city import CityContractError
from metroflow.v1.kinetics import ClassMass
from metroflow.v1.lanegroups import LaneGroupContract
from metroflow.ordered_lane import Lane
from metroflow.ordered_network import Group
from metroflow.foundation_kinetics import VehicleClass


def fixture(persons=5, dwell=2, cars=False):
    groups = tuple(
        Group(str(i), str(i), str(i + 1), Lane(10, 10, 100, 100, 1000, interaction_rate=0))
        for i in range(3)
    )
    links = frozenset(g.id for g in groups)
    contract = LaneGroupContract(
        "service-test",
        groups,
        frozenset({("0", "1"), ("1", "2")}),
        (),
        tuple((g.id, 1000) for g in groups),
        (),
        (),
    )
    buses = (
        BusRun("A", (("0",), ("1",)), (0.0, 0.0), 10, dwell, links),
        BusRun("B", (("1",), ("2",)), (0.0, 0.0), 10, dwell, links),
    )
    people = (
        PassengerCohort("a", "A", 0, 2, 0, persons),
        PassengerCohort("b", "B", 0, 1, 0, 3),
        PassengerCohort("c", "A", 1, 2, 0, 2),
    )
    freight = (FreightRun("F", ("0", "1", "2"), 0, 2, 100, 1000, 2000, links),)
    bus = VehicleClass(name="scheduled_bus", preferred_mps=10, length_m=12)
    truck = VehicleClass(name="freight", preferred_mps=10, length_m=10)
    from metroflow.v1.services import CarRun

    car = VehicleClass(name="car", preferred_mps=10)
    m = ServiceModel(
        contract,
        buses,
        people,
        freight,
        bus_class=bus,
        freight_class=truck,
        templates=(ClassMass(bus, 1, 1, 0, 0), ClassMass(truck, 1, 1, 0, 0)),
        entry_speeds={"scheduled_bus": 10, "freight": 10, **({"car": 10} if cars else {})},
        cars=(CarRun("C", ("0", "1", "2"), 0, 2),) if cars else (),
        car_class=car if cars else None,
    )
    return m


def test_two_routes_stops_and_freight_complete_real_shared_road():
    m = fixture()
    s = m.advance(m.initial(), 30)
    r = m.report(s)
    assert r["completed_bus_vehicles"] == 2
    assert r["arrived_persons"] == 10
    assert r["waiting_persons"] == r["onboard_persons"] == 0
    assert r["cargo_delivered_kg"] == pytest.approx(100)
    assert r["freight_completed_vehicles"] == pytest.approx(2)
    assert r["road_released_veh"] == pytest.approx(6)  # four bus legs + two freight vehicles
    assert r["road_completed_veh"] == pytest.approx(6)


def test_extra_passengers_do_not_spawn_buses_or_delete_waiting_mass():
    m = fixture(30)
    s = m.advance(m.initial(), 30)
    r = m.report(s)
    assert r["scheduled_bus_vehicles"] == 2 and r["road_released_veh"] == pytest.approx(6)
    assert r["arrived_persons"] == 13
    assert r["waiting_persons"] == 22
    assert sum(v.waiting + v.onboard + v.arrived for v in s.passengers) == 35


def test_dwell_delays_stop_boarding_and_vehicle_departure():
    a, b = fixture(dwell=0), fixture(dwell=10)
    sa, sb = a.advance(a.initial(), 8), b.advance(b.initial(), 8)
    assert a.report(sa)["arrived_persons"] > b.report(sb)["arrived_persons"]
    assert b.report(sb)["waiting_persons"] >= 2
    assert any(v.phase == "STOP" for v in sb.buses)


def test_resume_and_input_immutability():
    m = fixture()
    s = m.advance(m.initial(), 3)
    raw = pickle.dumps(s)
    a = m.advance(s, 30)
    b = m.advance(pickle.loads(raw), 30)
    assert a == b and pickle.dumps(s) == raw


def test_simultaneous_cohorts_share_capacity_without_id_priority():
    m = fixture(20)
    # Existing first cohort occupies all ten seats. Intermediate cohort remains waiting.
    s = m.advance(m.initial(), 30)
    assert s.passengers[0].arrived == 10 and s.passengers[0].waiting == 10
    assert s.passengers[2].waiting == 2


def test_freight_weight_and_link_restrictions_explicit():
    with pytest.raises(CityContractError):
        FreightRun("x", ("a",), 0, 1, 100, 3000, 2000, frozenset({"a"}))
    with pytest.raises(CityContractError):
        FreightRun("x", ("b",), 0, 1, 100, 1000, 2000, frozenset({"a"}))


def test_unsupported_transfer_never_completes_at_zero_time():
    with pytest.raises(CityContractError):
        PassengerCohort("x", "unknown", 1, 0, 0, 1)


def test_cross_model_checkpoint_and_unaligned_horizon_rejected():
    a, b = fixture(), fixture(dwell=10)
    with pytest.raises(CityContractError):
        b.step(a.initial())
    with pytest.raises(CityContractError):
        a.advance(a.initial(), 0.15)


def test_car_bus_freight_share_one_physical_network_and_conserve_each_class():
    m = fixture(cars=True)
    s = m.advance(m.initial(), 30)
    r = m.report(s)
    assert set(c.name for c in s.road.class_ledger) == {"car", "scheduled_bus", "freight"}
    assert r["road_released_veh"] == pytest.approx(8)
    assert r["road_completed_veh"] == pytest.approx(8)
    assert all(c.released == pytest.approx(c.completed) for c in s.road.class_ledger)
