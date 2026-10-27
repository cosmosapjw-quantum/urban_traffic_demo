"""Cars, fixed buses and freight share one physical road and journey ledger."""
from dataclasses import replace

import pytest

from metroflow.v1.activity import compile_activity, ActivityPatch
from metroflow.v1.city import CityContractError
from metroflow.v1.demand import TripLeg, Amounts
from metroflow.v1.joint_release_runtime import JointReleaseRuntime
from metroflow.v1.release_services import BusCorridor, compile_service_plan
from metroflow.v1.scenarios import scenario_city
from metroflow.v1.schedules import DepartureProfile, DepartureWindow


def fixture():
    city=scenario_city(1000)
    nodes={n.id:n for n in city.roadmap.nodes}
    measures=[]
    for block,kind in [('block','residential'),('work','job')]:
        p=next(p for p in city.portals if p.block_id==block)
        measures.append(compile_activity(city,block,kind,
                        patches=(ActivityPatch(1000,(nodes[p.node_id].xyz[:2],)),)))
    profile=DepartureProfile((DepartureWindow(0,2),))
    car=TripLeg('car','c',*measures,'work','car','car',Amounts(1.25,1),profile)
    back=replace(car,id='return',origin=car.destination,destination=car.origin,
                 purpose='return_home',depends_on='car',minimum_dwell_s=10)
    bus=replace(car,id='bus',cohort_id='b',mode='bus',vehicle_class='scheduled_bus',amounts=Amounts(25,1))
    busback=replace(bus,id='busreturn',origin=bus.destination,destination=bus.origin,
                    purpose='return_home',depends_on='bus',minimum_dwell_s=10)
    freight=TripLeg('cargo',None,None,car.destination,'delivery','freight','freight',Amounts(cargo_kg=100,vehicles=1),profile)
    legs=(car,back,bus,busback,freight)
    plan=compile_service_plan(city,legs,(BusCorridor('out','block','work',3,50),
                                        BusCorridor('back','work','block',5,50)),
                              depot_block_id='block',step_s=1)
    return city,legs,plan


def test_single_shared_step_whole_car_journey_services_and_blocked_busreturn(tmp_path,monkeypatch):
    city,legs,plan=fixture()
    model=JointReleaseRuntime(city,legs,plan)
    calls=[]
    step=model.service.step
    def counted(*args,**kwargs):
        calls.append(1)
        return step(*args,**kwargs)
    monkeypatch.setattr(model.service,'step',counted)
    state=model.advance(model.initial(),120)
    assert len(calls)==120
    assert state.completed[0]==pytest.approx(1)
    assert state.completed[1]==pytest.approx(1)
    assert state.completed[2]==pytest.approx(1)
    assert state.released[3]==0  # fixed bus already left before parent+dwell
    assert state.completed[4]==pytest.approx(1)
    assert state.birth_carrier_s[0]==pytest.approx(1)
    report=model.report(state)
    assert report['ledger']['cargo_kg']['completed']==pytest.approx(100)
    assert report['ledger']['persons']['pending']==pytest.approx(25)
    classes={c.name for c in state.service.road.class_ledger}
    assert classes=={'car','scheduled_bus','freight'}
    path=tmp_path/'joint.json'
    model.save(path,state)
    restored=model.load(path)
    assert restored==state
    assert model.advance(restored,125)==model.advance(state,125)
    with pytest.raises(CityContractError,match='calendar conservation|receipt'):
        model.check(replace(state,completed=(0,)+state.completed[1:]))


def test_car_egress_not_counted_as_whole_journey_completion():
    city,legs,_=fixture()
    # Move destination activity away from door, creating positive egress delay.
    target=compile_activity(city,'work','job')
    car=replace(legs[0],destination=target)
    bus=replace(legs[2],destination=target)
    cargo=replace(legs[4],destination=target)
    plan=compile_service_plan(city,(car,bus,cargo),
                             (BusCorridor('out','block','work',3,50),),depot_block_id='block')
    model=JointReleaseRuntime(city,(car,bus,cargo),plan)
    state=model.advance(model.initial(),30)
    assert state.service.road.completed>0
    assert state.completed[0]<1
    assert state.egress
    report=model.report(state)
    assert report['ledger']['persons']['active']>0


def test_joint_checkpoint_ties_bus_freight_moments_receipts_and_source_plan():
    city,legs,plan=fixture()
    model=JointReleaseRuntime(city,legs,plan)
    state=model.advance(model.initial(),120)
    for i,kind in ((2,'bus'),(4,'freight')):
        released=list(state.released)
        completed=list(state.completed)
        receipts=list(state.receipts)
        released[i]=completed[i]=0.0
        receipts[i]=()
        with pytest.raises(CityContractError,match=kind+' stage'):
            model.check(replace(state,released=tuple(released),completed=tuple(completed),receipts=tuple(receipts)))
    with pytest.raises(CityContractError,match='birth moment'):
        model.check(replace(state,birth_carrier_s=(0.0,)+state.birth_carrier_s[1:]))
    receipts=list(state.receipts)
    receipts[0]=((121.0,1.0),)
    with pytest.raises(CityContractError,match='receipt time'):
        model.check(replace(state,receipts=tuple(receipts)))
    # Forging BOTH service and calendar completion must still disagree with
    # the immutable physical freight class ledger.
    released=list(state.released)
    completed=list(state.completed)
    receipts=list(state.receipts)
    births=list(state.birth_carrier_s)
    released[4]=completed[4]=births[4]=0.0
    receipts[4]=()
    forged=replace(state,service=replace(state.service,freight_released=(False,),freight_completed=(0.0,)),
                   released=tuple(released),completed=tuple(completed),receipts=tuple(receipts),birth_carrier_s=tuple(births))
    with pytest.raises(CityContractError,match='physical class ledger'):
        model.check(forged)
    changed=replace(plan,source_legs=(replace(legs[0],amounts=Amounts(2.5,2)),)+legs[1:])
    with pytest.raises(CityContractError,match='source calendar'):
        JointReleaseRuntime(city,legs,changed)


def test_internal_only_calendar_uses_inert_clock_without_physical_releases():
    from metroflow.v1.journey import DelayLaw
    city,legs,_=fixture()
    internal=replace(legs[0],destination=legs[0].origin,intrazonal=DelayLaw(((2.,1.),)))
    plan=compile_service_plan(city,(internal,))
    model=JointReleaseRuntime(city,(internal,),plan)
    state=model.advance(model.initial(),10)
    assert state.completed==(1.0,)
    assert state.service.road.released==0
    assert state.service.road.completed==0
