from metroflow.core.state import make_empty_world_state
from metroflow.sim.replay import make_replay_record


def test_make_replay_record():
    world = make_empty_world_state(seed=7)
    rec = make_replay_record(world, num_steps=100, metric_signature=1.23)
    assert rec.seed == 7
    assert rec.num_steps == 100
