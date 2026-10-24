import pytest
from metroflow.terrain_city.network import generate
from metroflow.terrain_city.audit import geometry_audit

@pytest.mark.parametrize('terrain',['coast','valley'])
def test_each_surviving_orbital_component_joins_the_same_physical_backbone(terrain):
    atlas=generate('radial',terrain,4000.,20,17,20000)
    audit=geometry_audit(atlas)
    assert len(audit['component_sizes'])==1
    assert not audit['illegal_projected_contacts']
    assert atlas.summary['cycle_rank']==atlas.summary['bounded_faces']
