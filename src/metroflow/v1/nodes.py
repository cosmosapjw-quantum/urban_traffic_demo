"""Explicit node allocation and signal conflict contracts; rates are veh/s."""

import math

from ..packet_network import _rates
from ..active_suffix.common import _signal_green
from .city import reject


def allocate_node(fractions, sending, receiving, priorities):
    """Weighted progressive filling with fixed shared-head turn probabilities.

    A zero downstream supply blocks any shared head with positive turn fraction.
    Disjoint lane groups are separate inputs, so unrelated heads can still move.
    This is weighted max-min allocation, not global throughput maximization.
    """
    if set(fractions) != set(sending) or set(fractions) != set(priorities):
        reject("one sending/priority per incoming head required", "CONTRACT_ERROR")
    for key, beta in fractions.items():
        if (
            not beta
            or any(not math.isfinite(x) or x < 0 for x in beta.values())
            or abs(math.fsum(beta.values()) - 1) > 1e-10
        ):
            reject("fixed turn fractions must sum to one", "CONTRACT_ERROR")
        if any(j not in receiving and j != -1 for j in beta):
            reject("missing downstream receiving rate", "CONTRACT_ERROR")
        if (
            not math.isfinite(sending[key])
            or sending[key] < 0
            or not math.isfinite(priorities[key])
            or priorities[key] <= 0
        ):
            reject("finite nonnegative sending and positive priority required", "CONTRACT_ERROR")
    if any(not math.isfinite(x) or x < 0 for x in receiving.values()):
        reject("finite nonnegative receiving required", "CONTRACT_ERROR")
    return _rates(fractions, sending, receiving, priorities)


def validate_signal_conflicts(groups, conflicts, dt_s=1.0, event_budget=100000):
    """Exact aligned-grid conflict check over the joint repeat period.

    Signal boundaries must align with dt. Half-open green windows are checked
    in every constant phase interval. A missing signal means always green.
    Oversized joint periods fail explicitly rather than sampling and certifying.
    """
    if (
        not math.isfinite(dt_s)
        or dt_s <= 0
        or isinstance(event_budget, bool)
        or not isinstance(event_budget, int)
        or event_budget < 1
    ):
        reject("positive signal step and event budget required", "CONTRACT_ERROR")
    groups = tuple(groups)
    registry = {g.id: g for g in groups}
    if len(registry) != len(groups):
        reject("duplicate signal group", "CONTRACT_ERROR")
    for g in groups:
        s = g.signal
        if s and (
            not all(math.isfinite(x) for x in (s.cycle_s, s.green_s, s.offset_s))
            or s.cycle_s <= 0
            or round(s.cycle_s / dt_s) < 1
            or not 0 <= s.green_s <= s.cycle_s
            or any(
                abs(x / dt_s - round(x / dt_s)) > 1e-9 for x in (s.cycle_s, s.green_s, s.offset_s)
            )
        ):
            reject("signal boundaries must align with step", "CONTRACT_ERROR")
    checks = 0
    for a, b in conflicts:
        if a not in registry or b not in registry or a == b or registry[a].head != registry[b].head:
            reject("conflict needs two incoming groups at the same node", "CONTRACT_ERROR")
        ga, gb = registry[a], registry[b]
        period = math.lcm(*(round(g.signal.cycle_s / dt_s) if g.signal else 1 for g in (ga, gb)))
        checks += period
        if checks > event_budget:
            reject("signal conflict verification budget exceeded", "BLOCKED_RESOURCE")
        if any(
            _signal_green(ga.signal, (k + 0.5) * dt_s)
            and _signal_green(gb.signal, (k + 0.5) * dt_s)
            for k in range(period)
        ):
            reject("conflicting movements have simultaneous green", "CONTRACT_ERROR")
    return dict(status="PASS", intervals_checked=checks)
