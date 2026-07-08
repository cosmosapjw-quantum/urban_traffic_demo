"""PRNG seed/key helpers for reproducible host-driven simulation flows."""

from __future__ import annotations

import hashlib
from typing import Final

import numpy as np

__all__ = [
    "PRNGKeyArray",
    "normalize_seed",
    "key_from_seed",
    "seed_from_key",
    "split_keys",
    "next_key",
    "fold_in_u32",
    "fold_in_path",
]

PRNGKeyArray = np.ndarray
_UINT32_MASK: Final[int] = 0xFFFFFFFF


def normalize_seed(seed: int) -> int:
    """Normalize any Python int into the unsigned 32-bit range used by JAX keys."""

    return int(seed) & _UINT32_MASK


def key_from_seed(seed: int) -> PRNGKeyArray:
    """Create a deterministic two-word host PRNG key from a normalized seed."""

    return np.asarray([0, normalize_seed(seed)], dtype=np.uint32)


def seed_from_key(key: PRNGKeyArray) -> int:
    """Convert a two-word key into a deterministic integer seed for host RNGs."""

    key_np = _coerce_key(key)
    return (int(key_np[0]) << 32) | int(key_np[1])


def split_keys(key: PRNGKeyArray, num: int = 2) -> tuple[PRNGKeyArray, ...]:
    """Split a PRNG key into `num` deterministic subkeys."""

    if num < 1:
        raise ValueError("num must be >= 1")
    return tuple(fold_in_u32(key, i) for i in range(int(num)))


def next_key(key: PRNGKeyArray) -> tuple[PRNGKeyArray, PRNGKeyArray]:
    """Return `(next_state_key, use_now_subkey)` for sequential RNG consumption.

    This avoids `random.split` compile churn in host-driven step loops while
    preserving deterministic 32-bit key progression.
    """

    key_np = np.asarray(key, dtype=np.uint32)
    if key_np.shape != (2,):
        raise ValueError("key must have shape (2,)")
    next_key_np = key_np.copy()
    next_key_np[1] = np.uint32(normalize_seed(int(next_key_np[1]) + 1))
    return next_key_np, next_key_np.copy()


def fold_in_u32(key: PRNGKeyArray, value: int) -> PRNGKeyArray:
    """Fold an integer token into a PRNG key using deterministic uint32 coercion."""

    key_np = _coerce_key(key)
    digest = hashlib.blake2s(
        key_np.tobytes() + normalize_seed(value).to_bytes(4, byteorder="little", signed=False),
        digest_size=8,
    ).digest()
    return np.asarray(
        [
            int.from_bytes(digest[:4], byteorder="little", signed=False),
            int.from_bytes(digest[4:], byteorder="little", signed=False),
        ],
        dtype=np.uint32,
    )


def fold_in_path(key: PRNGKeyArray, *parts: int | str) -> PRNGKeyArray:
    """Fold a sequence of stable tokens into a PRNG key.

    String tokens are converted with a deterministic 32-bit hash (not Python's
    process-randomized `hash()`), so the result is reproducible across runs.
    """

    out = key
    for part in parts:
        token = _stable_token_u32(part)
        out = fold_in_u32(out, token)
    return out


def _coerce_key(key: PRNGKeyArray) -> np.ndarray:
    arr = np.asarray(key, dtype=np.uint32)
    if arr.shape != (2,):
        raise ValueError("key must have shape (2,)")
    return arr.copy()


def _stable_token_u32(part: int | str) -> int:
    if isinstance(part, int):
        return normalize_seed(part)
    digest = hashlib.blake2s(part.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, byteorder="little", signed=False)
