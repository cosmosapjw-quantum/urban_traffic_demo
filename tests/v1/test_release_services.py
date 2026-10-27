"""Explicit inventory, road sharing and conservative passenger eligibility."""
from dataclasses import replace

import pytest

from metroflow.foundation_kinetics import VehicleClass
from metroflow.ordered_network import Route
from metroflow.v1.activity import ActivityPatch, compile_activity
from metroflow.v1.city import CityContractError
from metroflow.v1.demand import Amounts, TripLeg
from metroflow.v1.release_services import BusCorridor, compile_service_plan
from metroflow.v1.scenarios import scenario_city
from metroflow.v1.schedules import DepartureProfile, DepartureWindow


def fixture():
    city = scenario_city(1000)
    nodes = {n.id:n for n in city.roadmap.nodes}
    measures = []
    for block, kind in [('block','residential'),('work','job')]:
        door = next(p for p in city.portals if p.block_id == block)
        xy = nodes[door.node_id].xyz[:2]
        measures.append(compile_activity(city, block, kind,
                                        patches=(ActivityPatch(1000,(xy,)),)))
    bus = TripLeg('out','cohort',*measures,'work','bus','scheduled_bus',Amounts(25,1),
                  DepartureProfile((DepartureWindow(0,2),)))
    freight = replace(bus,id='delivery',cohort_id=None,origin=None,mode='freight',
                      purpose='delivery',vehicle_class='freight',amounts=Amounts(0,1,1000))
    return city,bus,freight


def test_fixed_bus_and_explicit_depot_freight_share_road_with_car():
    city,bus,freight = fixture()
    plan = compile_service_plan(city,(bus,freight),
                                (BusCorridor('fleet','block','work',3,10),),
                                depot_block_id='block')
    route = plan.buses[0].legs[0]
    car = Route('daily',route)
    model = plan.model(step_s=1, traffic_routes=(car,),
                       traffic_classes={'daily':VehicleClass('car',preferred_mps=10)})
    assert len(model.network.groups) == len(city.transport_graph.roads)
    state = model.initial()
    state = model.step(state,offers=(('daily',1,0),))
    state = model.advance(state,180)
    report = model.report(state)
    assert report['scheduled_bus_vehicles'] == 1
    assert report['waiting_persons'] == pytest.approx(15)
    assert report['arrived_persons'] == pytest.approx(10)
    assert report['cargo_delivered_kg'] == pytest.approx(1000)
    assert report['road_released_veh'] == pytest.approx(3)
    assert report['road_completed_veh'] == pytest.approx(3)
    assert sum(r['birth_person_s'] for r in plan.metadata if 'birth_person_s' in r) == pytest.approx(25)


def test_missing_inventory_and_dependent_return_remain_pending():
    city,bus,freight = fixture()
    back = replace(bus,id='back',depends_on=bus.id)
    plan = compile_service_plan(city,(bus,freight,back))
    assert not plan.buses and not plan.passengers and not plan.freight
    assert len(plan.pending) == 3
    units = plan.assignment_report()['units']
    assert units['persons'] == dict(requested=50,assigned=0,unassigned=50)
    assert units['vehicles'] == dict(requested=3,assigned=0,unassigned=3)
    assert units['cargo_kg'] == dict(requested=1000,assigned=0,unassigned=1000)
    assert plan.source_legs == (bus,freight,back)
    with pytest.raises(CityContractError,match='budget'):
        compile_service_plan(city,(bus,freight),max_legs=1)


def test_tied_fleet_runs_share_person_mass_without_id_priority():
    city,bus,_ = fixture()
    plan = compile_service_plan(city,(bus,),
                                (BusCorridor('z','block','work',3,20),
                                 BusCorridor('a','block','work',3,20)))
    assert tuple(p.persons for p in plan.passengers) == (12.5,12.5)
    assert sum(m['birth_person_s'] for m in plan.metadata) == pytest.approx(25)
    no_bus = compile_service_plan(city,(bus,),
                                  (BusCorridor('early','block','work',1,100),))
    assert not no_bus.passengers and no_bus.pending


def test_dependent_bus_candidates_require_external_completion_eligibility():
    city,bus,_ = fixture()
    back = replace(bus,id='home',origin=bus.destination,destination=bus.origin,
                   depends_on='out',minimum_dwell_s=5)
    plan = compile_service_plan(city,(back,),
                                (BusCorridor('return','work','block',3,100),))
    assert len(plan.passengers) == 1
    assert plan.metadata[0]['depends_on'] == 'out'
    assert plan.metadata[0]['minimum_dwell_s'] == 5
    model = plan.model()
    with pytest.raises(CityContractError,match='eligibility'):
        model.step(model.initial())
    state = model.initial()
    for _ in range(180):
        state = model.step(state,eligible_passengers=())
    report = model.report(state)
    assert report['waiting_persons'] == pytest.approx(25)
    assert report['arrived_persons'] == 0
