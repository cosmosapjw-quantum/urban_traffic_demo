import pytest
from metroflow.terrain_city.landscape import Polygon,make_landscape,segment_clear

def test_narrow_water_between_dry_endpoints_and_width_are_real_constraints():
    p=Polygon('water',((45.,-2.),(55.,-2.),(55.,2.),(45.,2.)))
    assert not segment_clear((0.,0.),(100.,0.),(p,))
    assert not segment_clear((0.,5.),(100.,5.),(p,),4.)
    assert segment_clear((0.,10.),(100.,10.),(p,),4.)

@pytest.mark.parametrize('kind',['flat','river','coast','valley','lake'])
def test_distinct_terrain_is_a_bounded_replayable_environment(kind):
    a=make_landscape(kind,4000.,17);b=make_landscape(kind,4000.,17)
    assert a is not None and a==b
    assert a.terrain.n>=20
    assert len(a.water)>0 if kind!='flat' else not a.water
    assert a.terrain.spacing_m*a.terrain.n==4000.

def test_unknown_or_nonphysical_landscape_rejected():
    with pytest.raises(ValueError):make_landscape('imaginary')
    with pytest.raises(ValueError):make_landscape('river',float('nan'))
