from dataclasses import dataclass
from metroflow.core.state import WorldState


@dataclass(frozen=True)
class ReplayRecord:
    seed: int
    num_steps: int
    metric_signature: float


def make_replay_record(world: WorldState, num_steps: int, metric_signature: float) -> ReplayRecord:
    return ReplayRecord(seed=world.replay.seed, num_steps=num_steps, metric_signature=metric_signature)
