from metroflow.v1.services import ServiceModel, BusRun, PassengerCohort
from metroflow.v1.lanegroups import LaneGroupContract
from metroflow.ordered_network import Group, Route
from metroflow.ordered_lane import Lane
from metroflow.foundation_kinetics import VehicleClass
from metroflow.v1.city import CityContractError
import pytest


def model():
    group = Group("g", "O", "D", Lane(10, 10, 100, 100, 1000))
    contract = LaneGroupContract("boundary", (group,), frozenset(), (), (("g", 1000),), (), ())
    return ServiceModel(
        contract,
        (BusRun("b", (("g",),), (0.0,), 10, 0, frozenset({"g"})),),
        (PassengerCohort("p", "b", 0, 1, 0, 5),),
        (),
        bus_class=VehicleClass(name="bus", length_m=12),
        freight_class=VehicleClass(name="freight"),
        traffic_routes=(Route("dynamic", ("g",)),),
        traffic_classes={"dynamic": VehicleClass(name="car")},
    )


def test_dynamic_offers_preserve_single_network_and_input_checkpoint():
    m = model()
    initial = m.initial()
    s = m.step(initial, (("dynamic", 2.0, 0.0),), eligible_passengers=())
    assert initial.road.released == 0
    assert s.passengers[0].onboard == 0 and s.passengers[0].waiting == 5
    s = m.advance(s, 20.1)
    assert s.road.completed == pytest.approx(3)
    assert {c.name for c in s.road.class_ledger} == {"bus", "car"}


def test_external_offers_cannot_duplicate_scheduled_bus_or_unknown_cohort():
    m = model()
    s = m.initial()
    with pytest.raises(CityContractError) as e:
        m.step(s, (("bus:b:0", 1.0, 0.0),))
    assert e.value.checkpoint is s
    with pytest.raises(CityContractError):
        m.step(s, eligible_passengers={"unknown"})
