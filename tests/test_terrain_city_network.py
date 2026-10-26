import pytest
from metroflow.terrain_city.network import generate


@pytest.mark.parametrize(
    "style,terrain",
    [("planned", "flat"), ("polycentric", "river"), ("radial", "flat"), ("corridor", "valley")],
)
def test_generated_city_has_connected_hierarchy_and_actual_land_stock(style, terrain):
    c = generate(style, terrain, size_m=4000.0, resolution=20, population=20000)
    assert c is not None, "No physical city produced"
    assert len(c.roadmap.nodes) > 100
    assert {"local", "collector", "arterial"} <= {e.hierarchy for e in c.roadmap.sections}
    assert c.summary["components"] == 1
    assert sum(b.residents for b in c.blocks) + c.summary["unplaced_residents"] == 20000
    assert all(0 <= b.residents <= b.housing_capacity for b in c.blocks)
    assert c.summary["cycle_rank"] == c.summary["bounded_faces"]


def test_same_input_replays_and_masks_are_not_cosmetic():
    a = generate("polycentric", "river", size_m=4000.0, resolution=20, population=20000)
    assert a is not None
    assert a == generate("polycentric", "river", size_m=4000.0, resolution=20, population=20000)
    assert any(s.facility == "bridge" for s in a.roadmap.sections)
    assert a.summary["illegal_surface_water"] == 0
    assert a.summary["illegal_protected"] == 0


def test_input_limits_are_explicit():
    with pytest.raises(ValueError):
        generate("not_a_city")
    with pytest.raises(ValueError):
        generate(resolution=3)
    with pytest.raises(ValueError):
        generate(population=-1)
