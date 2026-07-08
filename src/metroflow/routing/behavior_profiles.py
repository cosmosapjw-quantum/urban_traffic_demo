"""Route-choice behavior profile generation and sampling (US2/T050)."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np
from metroflow.sim.rng import PRNGKeyArray

from metroflow.sim.rng import fold_in_path, key_from_seed, seed_from_key

__all__ = [
    "RouteChoiceProfile",
    "generate_route_choice_profiles",
    "build_route_choice_profiles",
    "sample_behavior_profile_ids",
    "sample_behavior_profile_ids_core",
]


@dataclass(frozen=True, slots=True)
class RouteChoiceProfile:
    """Behavior diversity profile for routing and reroute logic."""

    behavior_profile_id: int
    delay_sensitivity: float
    reroute_willingness: float
    persistence_bias: float
    exploration_bias: float

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.delay_sensitivity)):
            raise ValueError("delay_sensitivity must be finite")
        if not math.isfinite(float(self.reroute_willingness)):
            raise ValueError("reroute_willingness must be finite")
        if not math.isfinite(float(self.persistence_bias)):
            raise ValueError("persistence_bias must be finite")
        if not math.isfinite(float(self.exploration_bias)):
            raise ValueError("exploration_bias must be finite")
        if not 0.0 <= float(self.reroute_willingness) <= 1.0:
            raise ValueError("reroute_willingness must be in [0, 1]")


def generate_route_choice_profiles(*, seed: int = 0, count: int = 8) -> tuple[RouteChoiceProfile, ...]:
    """Generate deterministic route-choice behavior profiles for routing logic."""

    count = max(1, int(count))
    key = key_from_seed(seed)
    rng = np.random.default_rng(
        seed_from_key(fold_in_path(key, "routing", "behavior_profiles", "reroute_jitter"))
    )
    reroute_jitter = rng.uniform(low=-0.05, high=0.05, size=(count,))
    profiles: list[RouteChoiceProfile] = []
    for idx in range(count):
        base = idx / max(1, count - 1)
        profiles.append(
            RouteChoiceProfile(
                behavior_profile_id=idx,
                delay_sensitivity=0.75 + 1.25 * base,
                reroute_willingness=min(1.0, max(0.0, 0.25 + 0.65 * base + float(reroute_jitter[idx]))),
                persistence_bias=max(0.0, 1.0 - base),
                exploration_bias=0.05 + 0.25 * base,
            )
        )
    return tuple(profiles)


def build_route_choice_profiles(*, seed: int = 0, count: int = 8) -> tuple[RouteChoiceProfile, ...]:
    """Alias for `generate_route_choice_profiles`."""

    return generate_route_choice_profiles(seed=seed, count=count)


def sample_behavior_profile_ids(
    *,
    profiles: Iterable[RouteChoiceProfile],
    population_size: int,
    seed: int = 0,
) -> tuple[int, ...]:
    """Sample behavior-profile ids reproducibly for a population assignment pass."""

    profile_tuple = tuple(profiles)
    n = int(population_size)
    if n < 0:
        raise ValueError("population_size must be >= 0")
    if not profile_tuple:
        raise ValueError("profiles must not be empty")
    if n == 0:
        return ()

    profile_ids, weights = _prepare_sampling_arrays(profile_tuple)
    key = fold_in_path(key_from_seed(seed), "routing", "behavior_profiles", "sample_ids", n)
    sampled_ids = sample_behavior_profile_ids_core(
        profile_ids=profile_ids,
        weights=weights,
        population_size=n,
        key=key,
    )
    return tuple(int(v) for v in sampled_ids.tolist())


def sample_behavior_profile_ids_core(
    *,
    profile_ids: np.ndarray,
    weights: np.ndarray,
    population_size: int,
    key: PRNGKeyArray,
) -> np.ndarray:
    """Array-only core for behavior-profile id sampling."""

    n = int(population_size)
    if n < 0:
        raise ValueError("population_size must be >= 0")
    profile_ids = np.asarray(profile_ids, dtype=np.int32)
    weights = np.asarray(weights, dtype=np.float32)
    if profile_ids.ndim != 1 or weights.ndim != 1:
        raise ValueError("profile_ids and weights must be 1-D arrays")
    if profile_ids.shape[0] != weights.shape[0]:
        raise ValueError("profile_ids and weights length mismatch")
    if profile_ids.shape[0] == 0:
        if n == 0:
            return np.asarray((), dtype=np.int32)
        raise ValueError("profile_ids must not be empty when population_size > 0")
    rng = np.random.default_rng(seed_from_key(key))
    sampled_idx = rng.choice(weights.shape[0], size=(int(n),), replace=True, p=weights)
    return profile_ids[sampled_idx]


def _prepare_sampling_arrays(profiles: tuple[RouteChoiceProfile, ...]) -> tuple[np.ndarray, np.ndarray]:
    ids: list[int] = []
    delay_vals: list[float] = []
    reroute_vals: list[float] = []
    persist_vals: list[float] = []
    explore_vals: list[float] = []

    seen_ids: set[int] = set()
    for profile in profiles:
        profile_id = int(profile.behavior_profile_id)
        if profile_id in seen_ids:
            raise ValueError("behavior_profile_id values must be unique")
        seen_ids.add(profile_id)
        ids.append(profile_id)

        delay = float(profile.delay_sensitivity)
        reroute = float(profile.reroute_willingness)
        persist = float(profile.persistence_bias)
        explore = float(profile.exploration_bias)
        if not all(math.isfinite(v) for v in (delay, reroute, persist, explore)):
            raise ValueError("behavior profile numeric fields must be finite")
        if not 0.0 <= reroute <= 1.0:
            raise ValueError("reroute_willingness must be in [0, 1]")
        delay_vals.append(delay)
        reroute_vals.append(reroute)
        persist_vals.append(persist)
        explore_vals.append(explore)

    profile_ids = np.asarray(ids, dtype=np.int32)
    weights = _sampling_weights_from_arrays(
        delay=np.asarray(delay_vals, dtype=np.float32),
        reroute=np.asarray(reroute_vals, dtype=np.float32),
        persist=np.asarray(persist_vals, dtype=np.float32),
        explore=np.asarray(explore_vals, dtype=np.float32),
    )
    return profile_ids, weights


def _sampling_weights(profiles: tuple[RouteChoiceProfile, ...]) -> np.ndarray:
    _, weights = _prepare_sampling_arrays(profiles)
    return weights


def _sampling_weights_from_arrays(
    *,
    delay: np.ndarray,
    reroute: np.ndarray,
    persist: np.ndarray,
    explore: np.ndarray,
) -> np.ndarray:
    if not (delay.ndim == reroute.ndim == persist.ndim == explore.ndim == 1):
        raise ValueError("behavior profile arrays must be 1-D")
    if not (delay.shape == reroute.shape == persist.shape == explore.shape):
        raise ValueError("behavior profile arrays must have matching shapes")

    # Balanced nonzero weighting so all profiles remain sampleable while still
    # reflecting diversity dimensions relevant to US2 reroute behavior.
    centered_persist = np.abs(persist - np.mean(persist))
    raw = 0.25 + 0.35 * reroute + 0.15 * explore + 0.15 * centered_persist + 0.10 * (
        delay / np.maximum(1.0, np.max(delay))
    )
    raw = np.clip(raw, 1e-6, None)
    return (raw / np.sum(raw)).astype(np.float32)
