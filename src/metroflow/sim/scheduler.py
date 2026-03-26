from __future__ import annotations

from dataclasses import dataclass
from metroflow.core.contracts import TickSchedule


@dataclass(frozen=True)
class SchedulerDecision:
    run_fast: bool
    run_medium: bool
    run_slow: bool


def should_run(step_idx: int, every: int) -> bool:
    if every <= 0:
        raise ValueError("Cadence must be positive.")
    return step_idx % every == 0


def scheduler_decision(step_idx: int, schedule: TickSchedule) -> SchedulerDecision:
    return SchedulerDecision(
        run_fast=should_run(step_idx, schedule.fast_every),
        run_medium=should_run(step_idx, schedule.medium_every),
        run_slow=should_run(step_idx, schedule.slow_every),
    )
