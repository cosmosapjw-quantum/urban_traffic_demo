"""OD-UCB bandit state and online update logic (T063)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

Array = np.ndarray

__all__ = [
    "ODBanditState",
    "create_od_ucb_state",
    "build_od_ucb_state",
    "init_od_bandit_state",
    "select_ucb_arm",
    "choose_ucb_arm",
    "update_od_ucb_state",
    "update_online_od_bandit",
    "apply_od_bandit_reward_update",
    "compute_ucb_scores_core",
    "select_ucb_arm_core",
    "update_od_ucb_arrays_core",
]


@dataclass(slots=True)
class ODBanditState:
    """Per-OD UCB bandit state aligned with the phase-1 data model."""

    od_key: tuple[Any, Any]
    arm_count: int
    pull_count: Array | Any
    estimated_reward: Array | Any
    exploration_bonus: Array | Any | None = None
    last_update_tick: int = 0
    candidate_ids: Array | Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.od_key = tuple(self.od_key)  # type: ignore[assignment]
        self.arm_count = int(self.arm_count)
        self.last_update_tick = int(self.last_update_tick)
        self.pull_count = np.asarray(self.pull_count, dtype=np.int32)
        self.estimated_reward = np.asarray(self.estimated_reward, dtype=np.float32)
        if self.candidate_ids is not None:
            self.candidate_ids = np.asarray(self.candidate_ids, dtype=np.int32)
        if not isinstance(self.metadata, dict):
            self.metadata = dict(self.metadata)

        if len(self.od_key) != 2:
            raise ValueError("od_key must contain exactly (origin, destination)")
        if self.arm_count < 0:
            raise ValueError("arm_count must be >= 0")
        if self.pull_count.ndim != 1 or int(self.pull_count.shape[0]) != self.arm_count:
            raise ValueError("pull_count length must equal arm_count")
        if self.estimated_reward.ndim != 1 or int(self.estimated_reward.shape[0]) != self.arm_count:
            raise ValueError("estimated_reward length must equal arm_count")
        if bool(np.any(self.pull_count < 0)):
            raise ValueError("pull_count values must be >= 0")
        if not bool(np.all(np.isfinite(self.estimated_reward))):
            raise ValueError("estimated_reward values must be finite")
        if self.candidate_ids is not None and (
            self.candidate_ids.ndim != 1 or int(self.candidate_ids.shape[0]) != self.arm_count
        ):
            raise ValueError("candidate_ids length must equal arm_count")
        if self.candidate_ids is not None:
            candidate_id_values = tuple(int(x) for x in self.candidate_ids.tolist())
            if len(set(candidate_id_values)) != len(candidate_id_values):
                raise ValueError("candidate_ids must be unique")

        if self.exploration_bonus is None:
            self.exploration_bonus = np.zeros((self.arm_count,), dtype=np.float32)
        else:
            self.exploration_bonus = np.asarray(self.exploration_bonus, dtype=np.float32)
            if self.exploration_bonus.ndim != 1 or int(self.exploration_bonus.shape[0]) != self.arm_count:
                raise ValueError("exploration_bonus length must equal arm_count")
            if not bool(np.all(np.isfinite(self.exploration_bonus))):
                raise ValueError("exploration_bonus values must be finite")


def create_od_ucb_state(
    *,
    od_key: tuple[Any, Any],
    arm_count: int | None = None,
    candidate_count: int | None = None,
    pull_count: tuple[int, ...] | None = None,
    estimated_reward: tuple[float, ...] | None = None,
    exploration_bonus: tuple[float, ...] | None = None,
    candidate_ids: tuple[int, ...] | None = None,
    last_update_tick: int = 0,
) -> ODBanditState:
    """Create an `ODBanditState` with sensible zero-initialized defaults."""

    n = int(arm_count if arm_count is not None else (candidate_count if candidate_count is not None else 0))
    if arm_count is not None and candidate_count is not None and int(arm_count) != int(candidate_count):
        raise ValueError("arm_count and candidate_count must match when both provided")
    if n < 0:
        raise ValueError("arm_count or candidate_count must be provided and >= 0")
    pulls = np.asarray(pull_count if pull_count is not None else (0,) * n, dtype=np.int32)
    rewards = np.asarray(
        estimated_reward if estimated_reward is not None else (0.0,) * n,
        dtype=np.float32,
    )
    bonus = np.asarray(
        exploration_bonus if exploration_bonus is not None else (0.0,) * n,
        dtype=np.float32,
    )
    if candidate_ids is None:
        candidate_ids = np.arange(n, dtype=np.int32)
    return ODBanditState(
        od_key=od_key,
        arm_count=n,
        pull_count=pulls,
        estimated_reward=rewards,
        exploration_bonus=bonus,
        candidate_ids=candidate_ids,
        last_update_tick=last_update_tick,
    )


def build_od_ucb_state(**kwargs) -> ODBanditState:
    """Alias for `create_od_ucb_state`."""

    return create_od_ucb_state(**kwargs)


def init_od_bandit_state(**kwargs) -> ODBanditState:
    """Alias for `create_od_ucb_state`."""

    return create_od_ucb_state(**kwargs)


def compute_ucb_scores_core(
    estimated_reward: Array | Any,
    pull_count: Array | Any,
    *,
    exploration_scale: float = 1.0,
) -> Array:
    """Array-only UCB1 scores for batch call sites."""

    est = np.asarray(estimated_reward, dtype=np.float32)
    pulls = np.asarray(pull_count, dtype=np.float32)
    total_pulls = np.maximum(1.0, np.sum(pulls))
    safe_pulls = np.maximum(1.0, pulls)
    scale = np.asarray(exploration_scale, dtype=np.float32)
    bonus = scale * np.sqrt(np.log(total_pulls + 1.0) / safe_pulls)
    # Prefer any unpulled arm deterministically by giving it a large finite score.
    unpulled_mask = pulls <= 0.0
    return np.where(unpulled_mask, np.asarray(1.0e9, dtype=np.float32), est + bonus)


def select_ucb_arm_core(
    estimated_reward: Array | Any,
    pull_count: Array | Any,
    *,
    exploration_scale: float = 1.0,
) -> Array:
    """Array-only arm selection core returning selected arm index."""

    return np.argmax(
        compute_ucb_scores_core(
            estimated_reward,
            pull_count,
            exploration_scale=exploration_scale,
        )
    )


def update_od_ucb_arrays_core(
    pull_count: Array | Any,
    estimated_reward: Array | Any,
    *,
    arm_index: Array | Any,
    reward: Array | Any,
) -> tuple[Array, Array, Array]:
    """Array-only online update core for future batch/JIT integration."""

    pulls = np.asarray(pull_count, dtype=np.int32)
    rewards = np.asarray(estimated_reward, dtype=np.float32)
    idx = int(np.asarray(arm_index, dtype=np.int32))
    reward_value = np.asarray(reward, dtype=np.float32)

    next_pulls = pulls.copy()
    next_rewards = rewards.copy()
    next_pulls[idx] += 1
    n = np.asarray(next_pulls[idx], dtype=np.float32)
    prev_mean = rewards[idx]
    next_rewards[idx] = prev_mean + (reward_value - prev_mean) / np.maximum(1.0, n)
    scores = compute_ucb_scores_core(next_rewards, next_pulls)
    unpulled = next_pulls <= 0
    next_bonus = np.where(unpulled, np.asarray(1.0e9, dtype=np.float32), scores - next_rewards)
    return next_pulls, next_rewards, next_bonus


def select_ucb_arm(
    *,
    state: ODBanditState,
    current_tick: int | None = None,
    tick_index: int | None = None,
    seed: int | None = None,
    exploration_scale: float = 1.0,
) -> int | None:
    """Select an arm index using a deterministic UCB1-style policy.

    `seed` is accepted for API compatibility but not used in T063; tie-breaking is
    deterministic (lowest arm index among maxima) for reproducibility. For
    `jit`/`vmap` call sites, use `select_ucb_arm_core(...)` instead.
    """

    _ = int(current_tick if current_tick is not None else (tick_index if tick_index is not None else state.last_update_tick))
    _ = seed
    if state.arm_count == 0:
        return None
    scores = _compute_ucb_scores_host(
        estimated_reward=state.estimated_reward,
        pull_count=state.pull_count,
        exploration_scale=float(exploration_scale),
    )
    return int(np.argmax(scores))


def choose_ucb_arm(**kwargs) -> int | None:
    """Alias for `select_ucb_arm`."""

    return select_ucb_arm(**kwargs)


def update_od_ucb_state(
    *,
    state: ODBanditState,
    arm_index: int | None = None,
    arm_idx: int | None = None,
    reward: float,
    current_tick: int | None = None,
    tick_index: int | None = None,
    seed: int | None = None,
) -> ODBanditState:
    """Apply an online reward update to the selected arm via incremental mean.

    This wrapper materializes Python fields on the returned dataclass. For
    `jit`/`vmap` call sites, use `update_od_ucb_arrays_core(...)` instead.
    """

    _ = seed
    idx = int(arm_index if arm_index is not None else (arm_idx if arm_idx is not None else -1))
    if not (0 <= idx < state.arm_count):
        raise ValueError("arm_index out of range")
    reward_value = float(reward)
    if not bool(np.isfinite(reward_value)):
        raise ValueError("reward must be finite")

    next_pulls_arr = np.asarray(state.pull_count, dtype=np.int32).copy()
    next_rewards_arr = np.asarray(state.estimated_reward, dtype=np.float32).copy()
    next_pulls_arr[idx] += 1
    n = float(next_pulls_arr[idx])
    prev_mean = float(next_rewards_arr[idx])
    next_rewards_arr[idx] = prev_mean + (reward_value - prev_mean) / max(1.0, n)
    scores = _compute_ucb_scores_host(
        estimated_reward=next_rewards_arr,
        pull_count=next_pulls_arr,
        exploration_scale=1.0,
    )
    unpulled = next_pulls_arr <= 0
    next_bonuses_arr = np.where(
        unpulled,
        np.float32(1.0e9),
        scores - next_rewards_arr,
    ).astype(np.float32)

    next_tick = int(current_tick if current_tick is not None else (tick_index if tick_index is not None else state.last_update_tick))
    return replace(
        state,
        pull_count=next_pulls_arr,
        estimated_reward=next_rewards_arr,
        exploration_bonus=next_bonuses_arr,
        last_update_tick=next_tick,
    )


def _compute_ucb_scores_host(
    *,
    estimated_reward: Any,
    pull_count: Any,
    exploration_scale: float,
) -> np.ndarray:
    est = np.asarray(estimated_reward, dtype=np.float32)
    pulls = np.asarray(pull_count, dtype=np.float32)
    total_pulls = max(1.0, float(np.sum(pulls)))
    safe_pulls = np.maximum(1.0, pulls)
    bonus = float(exploration_scale) * np.sqrt(np.log(total_pulls + 1.0) / safe_pulls)
    scores = est + bonus
    scores[pulls <= 0.0] = np.float32(1.0e9)
    return scores.astype(np.float32, copy=False)


def update_online_od_bandit(**kwargs) -> ODBanditState:
    """Alias for `update_od_ucb_state`."""

    return update_od_ucb_state(**kwargs)


def apply_od_bandit_reward_update(**kwargs) -> ODBanditState:
    """Alias for `update_od_ucb_state`."""

    return update_od_ucb_state(**kwargs)
