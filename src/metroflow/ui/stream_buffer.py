"""Throttled UI snapshot emission buffer (coalescing latest snapshot)."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from typing import Any

__all__ = [
    "UISnapshotEmission",
    "UISnapshotBufferStats",
    "UISnapshotStreamBuffer",
    "compute_min_emit_interval_ticks",
]


def compute_min_emit_interval_ticks(*, tick_seconds: float, hz_limit: float) -> int:
    """Convert tick duration + Hz limit into a minimum emit interval in ticks."""

    tick_seconds = float(tick_seconds)
    hz_limit = float(hz_limit)
    if tick_seconds <= 0:
        raise ValueError("tick_seconds must be > 0")
    if hz_limit <= 0:
        raise ValueError("hz_limit must be > 0")
    # At most one snapshot can be emitted per simulation tick.
    return max(1, ceil(1.0 / (tick_seconds * hz_limit)))


@dataclass(slots=True)
class UISnapshotEmission:
    """Emission event returned by the buffer when a snapshot is due."""

    snapshot_source: Any
    snapshot_tick: int
    emitted_at_tick: int
    frame_seq: int
    dropped_since_last_emit: int = 0
    forced: bool = False

    def __post_init__(self) -> None:
        self.snapshot_tick = int(self.snapshot_tick)
        self.emitted_at_tick = int(self.emitted_at_tick)
        self.frame_seq = int(self.frame_seq)
        self.dropped_since_last_emit = int(self.dropped_since_last_emit)
        self.forced = bool(self.forced)
        if self.snapshot_tick < 0 or self.emitted_at_tick < 0:
            raise ValueError("tick values must be >= 0")
        if self.frame_seq < 0:
            raise ValueError("frame_seq must be >= 0")
        if self.dropped_since_last_emit < 0:
            raise ValueError("dropped_since_last_emit must be >= 0")


@dataclass(slots=True)
class UISnapshotBufferStats:
    """Operational counters for UI buffer observability/debugging."""

    offered: int = 0
    emitted: int = 0
    dropped_coalesced: int = 0
    forced_emits: int = 0

    def __post_init__(self) -> None:
        self.offered = int(self.offered)
        self.emitted = int(self.emitted)
        self.dropped_coalesced = int(self.dropped_coalesced)
        self.forced_emits = int(self.forced_emits)
        for name in ("offered", "emitted", "dropped_coalesced", "forced_emits"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be >= 0")

    def as_dict(self) -> dict[str, int]:
        return {
            "offered": self.offered,
            "emitted": self.emitted,
            "dropped_coalesced": self.dropped_coalesced,
            "forced_emits": self.forced_emits,
        }


@dataclass(slots=True)
class UISnapshotStreamBuffer:
    """Throttle/coalesce UI snapshot emissions without blocking simulation ticks.

    Design intent (T017):
    - Keep only the latest pending `UISnapshotSource` (coalescing older snapshots)
    - Emit at most `ui_stream_hz_limit` relative to simulation tick cadence
    - Support forced emission (e.g., UI snapshot request) without changing cadence
    """

    tick_seconds: float
    hz_limit: float
    min_emit_interval_ticks: int | None = None
    last_emitted_tick: int | None = None
    _pending_snapshot_source: Any = None
    _pending_snapshot_tick: int | None = None
    _dropped_since_last_emit: int = 0
    _frame_seq_next: int = 0
    stats: UISnapshotBufferStats = field(default_factory=UISnapshotBufferStats)

    def __post_init__(self) -> None:
        self.tick_seconds = float(self.tick_seconds)
        self.hz_limit = float(self.hz_limit)
        if self.tick_seconds <= 0:
            raise ValueError("tick_seconds must be > 0")
        if self.hz_limit <= 0:
            raise ValueError("hz_limit must be > 0")
        if self.min_emit_interval_ticks is None:
            self.min_emit_interval_ticks = compute_min_emit_interval_ticks(
                tick_seconds=self.tick_seconds,
                hz_limit=self.hz_limit,
            )
        self.min_emit_interval_ticks = int(self.min_emit_interval_ticks)
        if self.min_emit_interval_ticks < 1:
            raise ValueError("min_emit_interval_ticks must be >= 1")
        if self.last_emitted_tick is not None:
            self.last_emitted_tick = int(self.last_emitted_tick)
            if self.last_emitted_tick < 0:
                raise ValueError("last_emitted_tick must be >= 0")
        self._pending_snapshot_tick = (
            None if self._pending_snapshot_tick is None else int(self._pending_snapshot_tick)
        )
        if self._pending_snapshot_tick is not None and self._pending_snapshot_tick < 0:
            raise ValueError("_pending_snapshot_tick must be >= 0")
        self._dropped_since_last_emit = int(self._dropped_since_last_emit)
        self._frame_seq_next = int(self._frame_seq_next)
        if self._dropped_since_last_emit < 0 or self._frame_seq_next < 0:
            raise ValueError("internal counters must be >= 0")
        if not isinstance(self.stats, UISnapshotBufferStats):
            self.stats = UISnapshotBufferStats(**dict(self.stats))

    @property
    def has_pending_snapshot(self) -> bool:
        return self._pending_snapshot_tick is not None

    @property
    def pending_snapshot_tick(self) -> int | None:
        return self._pending_snapshot_tick

    def offer(
        self,
        snapshot_source: Any,
        *,
        tick: int,
        force_emit: bool = False,
    ) -> UISnapshotEmission | None:
        """Offer a new snapshot and emit immediately if cadence permits."""

        tick = int(tick)
        if tick < 0:
            raise ValueError("tick must be >= 0")
        self.stats.offered += 1

        if self.has_pending_snapshot:
            self._dropped_since_last_emit += 1
            self.stats.dropped_coalesced += 1

        self._pending_snapshot_source = snapshot_source
        self._pending_snapshot_tick = tick

        return self.poll(tick=tick, force_emit=force_emit)

    def poll(self, *, tick: int, force_emit: bool = False) -> UISnapshotEmission | None:
        """Emit the latest pending snapshot if due, otherwise return `None`."""

        tick = int(tick)
        if tick < 0:
            raise ValueError("tick must be >= 0")
        if not self.has_pending_snapshot:
            return None
        if not force_emit and not self._is_emit_due(tick):
            return None
        return self._emit_pending(emitted_at_tick=tick, forced=force_emit)

    def flush(self, *, tick: int) -> UISnapshotEmission | None:
        """Force-emit the latest pending snapshot if one exists."""

        return self.poll(tick=tick, force_emit=True)

    def clear_pending(self) -> None:
        """Drop the pending snapshot without emitting (rare admin/reset path)."""

        if self.has_pending_snapshot:
            self.stats.dropped_coalesced += 1
            self._dropped_since_last_emit += 1
        self._pending_snapshot_source = None
        self._pending_snapshot_tick = None

    def _is_emit_due(self, tick: int) -> bool:
        if self.last_emitted_tick is None:
            return True
        return (tick - self.last_emitted_tick) >= self.min_emit_interval_ticks

    def _emit_pending(self, *, emitted_at_tick: int, forced: bool) -> UISnapshotEmission:
        assert self._pending_snapshot_tick is not None
        emission = UISnapshotEmission(
            snapshot_source=self._pending_snapshot_source,
            snapshot_tick=self._pending_snapshot_tick,
            emitted_at_tick=emitted_at_tick,
            frame_seq=self._frame_seq_next,
            dropped_since_last_emit=self._dropped_since_last_emit,
            forced=forced,
        )
        self._frame_seq_next += 1
        self.last_emitted_tick = int(emitted_at_tick)
        self._pending_snapshot_source = None
        self._pending_snapshot_tick = None
        self._dropped_since_last_emit = 0
        self.stats.emitted += 1
        if forced:
            self.stats.forced_emits += 1
        return emission
