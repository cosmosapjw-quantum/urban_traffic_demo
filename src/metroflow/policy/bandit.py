from dataclasses import dataclass


@dataclass(frozen=True)
class BanditArmState:
    value_estimate: float = 0.0
    count: int = 0


def update_bandit_arm(state: BanditArmState, reward: float, alpha: float = 0.1) -> BanditArmState:
    new_q = state.value_estimate + alpha * (reward - state.value_estimate)
    return BanditArmState(value_estimate=new_q, count=state.count + 1)
