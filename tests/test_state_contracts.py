from metroflow.core.state import make_empty_world_state, with_graph_version_bump
from metroflow.core.contracts import default_simulation_config, validate_time_scale_separation, validate_state_contract


def test_make_empty_world_state():
    world = make_empty_world_state(seed=42)
    assert world.replay.seed == 42
    assert world.graph.version == 0


def test_graph_version_bump():
    world = make_empty_world_state()
    world2 = with_graph_version_bump(world)
    assert world2.graph.version == world.graph.version + 1


def test_validate_config():
    config = default_simulation_config()
    validate_time_scale_separation(config)


def test_validate_state_contract_empty():
    world = make_empty_world_state()
    validate_state_contract(world)
