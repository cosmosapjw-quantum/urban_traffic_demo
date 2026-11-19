"""Partition invariance of admissible FIFO descriptions: physical regression tests."""
from dataclasses import replace

import pytest

from metroflow.v1.kcmb import KCMBClass
from metroflow.v1.kcmb_network import KCMBLink, KCMBRoute, KCMBNetworkConfig
from metroflow.v1.kcmb_ordered_fifo import OrderedKCMBBoundedNetwork, OrderedRun


def merge_case(backend="python", out_cap=.3):
    c=KCMBClass("car",10.,5.,.2,0.,1.,source_p=1.,source_speed_fraction=1.)
    links=(KCMBLink("n","N","J",20.,1,2.,5.),
           KCMBLink("s","S","J",20.,1,2.,5.),
           KCMBLink("out","J","D",20.,1,out_cap,5.))
    rs=(KCMBRoute("A",c,("n","out")),KCMBRoute("B",c,("s","out")))
    obj=OrderedKCMBBoundedNetwork(KCMBNetworkConfig(links,rs,.5),
                                   backend=backend,max_runs=300)
    state=obj.initial_profile({"n":(2.,0.),"s":(0.,2.)})
    split=replace(state,runs=((OrderedRun(0,.2,0),OrderedRun(0,1.8,1)),
                              state.runs[1],state.runs[2]))
    assert split.moments==state.moments and split.released==state.released
    return obj,state,split


@pytest.mark.parametrize("backend",["python","rust"])
@pytest.mark.parametrize("out_cap",[.3,.5,1.,2.])
def test_eligible_same_route_partition_does_not_bias_competing_merge(backend,out_cap):
    model,whole,partitioned=merge_case(backend,out_cap)
    a,ra=model.step(whole,(0.,0.))
    b,rb=model.step(partitioned,(0.,0.))
    for key in set(ra["turn_flows"])|set(rb["turn_flows"]):
        assert ra["turn_flows"].get(key,0.)==pytest.approx(
            rb["turn_flows"].get(key,0.),rel=3e-11,abs=1e-10)
    for x,y in zip(a.moments,b.moments):
        assert x==pytest.approx(y,rel=3e-11,abs=1e-10)
    assert a.pending==pytest.approx(b.pending,abs=1e-10)
    assert a.completed==pytest.approx(b.completed,abs=1e-10)
    assert ra["mass_error_max_veh"]<1e-9
    assert rb["mass_error_max_veh"]<1e-9


def test_ineligible_second_fragment_is_not_collapsed_with_eligible_head():
    model,whole,s=merge_case(out_cap=.3)
    delayed=replace(s,runs=((OrderedRun(0,.2,0),OrderedRun(0,1.8,8)),
                            s.runs[1],s.runs[2]))
    a,ra=model.step(delayed,(0.,0.))
    assert ra["turn_flows"].get(("n","out","A"),0.) <= .2+1e-12
    # The original non-eligible mass is still present at this link.
    assert len(a.runs[0])>=1
