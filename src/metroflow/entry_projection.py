"""Positive entry-time projection, with exact point and movement-support barriers.

The input is a finite positive measure of uniform intervals, categorized by
tag and remaining route. Each protected time segment becomes one FIFO cohort;
its per-category entry mean and original birth moment are retained. This loses
sub-segment ordering. The reported W1 cost bounds this local time projection,
not nonlinear downstream delay. Width zero calls the unchanged exact oracle.
"""
from bisect import bisect_right
from collections import defaultdict
from dataclasses import replace
import math
import struct


def validate_projection_width(width_s):
    if isinstance(width_s, bool) or not isinstance(width_s, (int, float)):
        raise ValueError("entry projection width must be a finite nonnegative number")
    width_s = float(width_s)
    if not math.isfinite(width_s) or width_s < 0:
        raise ValueError("entry projection width must be finite and nonnegative")
    return width_s


def projection_identity(identity, width_s):
    width_s = validate_projection_width(width_s)
    if width_s == 0:
        return identity
    return identity + ":entry_projection_support_v1:" + struct.pack(">d", width_s).hex()


def projection_diagnostics(width_s):
    return dict(policy="entry_projection_support_v1" if width_s else "exact_intervals",
                width_s=width_s, input_parts=0, output_parts=0, cohorts=0,
                protected_support_boundaries=0, local_w1_bound_veh_s=0.0,
                scope="latest validated proposed road transition; may precede coupled rollback; "
                      "local entry-measure transport cost, not network travel-time error",
                checkpointed=False)


def project_entry_packets(parts, target_m, record_budget, width_s):
    """Return packets and one-operation diagnostics without mutating the input.

    Endpoint sweep costs O(P log P). Integration visits input/protected-segment
    overlaps; it never constructs the all-endpoint elementary packet expansion.
    Output is O(sum of category counts over protected segments). Many genuine
    support changes or categories still require many records and can hit budget.
    """
    from .active_suffix.common import BudgetExceeded
    from .packet_network import Packet, combine, interval_packets

    width_s = validate_projection_width(width_s)
    if (isinstance(record_budget, bool) or not isinstance(record_budget, int)
            or record_budget <= 0 or not math.isfinite(target_m)):
        raise ValueError("positive record budget and finite target required")
    parts = tuple(parts)
    stats = projection_diagnostics(width_s)
    stats["input_parts"] = len(parts)
    for p in parts:
        if (not p.remaining or not math.isfinite(p.mass) or p.mass <= 0
                or not math.isfinite(p.birth_moment) or p.birth_moment < 0
                or p.entry_start_s is None or p.entry_end_s is None
                or not math.isfinite(p.entry_start_s) or not math.isfinite(p.entry_end_s)
                or not 0 <= p.entry_start_s <= p.entry_end_s):
            raise ValueError("invalid positive entry measure")
    if width_s == 0:
        out = interval_packets(parts, target_m, record_budget) if parts else ()
        stats.update(output_parts=sum(len(p.parts) for p in out), cohorts=len(out))
        return out, stats
    if not parts:
        return (), stats

    changes = defaultdict(lambda: defaultdict(int))
    atoms = defaultdict(list)
    for p in parts:
        a, b = p.entry_start_s, p.entry_end_s
        if a == b:
            atoms[a].append(p)
        else:
            movement = p.remaining[1] if len(p.remaining) > 1 else None
            changes[a][movement] += 1
            changes[b][movement] -= 1
    boundaries = set(atoms)
    active = {}
    runs = []
    run_start = None
    event_times = sorted(changes)
    for time in event_times:
        before = frozenset(active)
        for movement, delta in changes[time].items():
            count = active.get(movement, 0) + delta
            if count < 0:
                raise ArithmeticError("negative movement support count")
            if count:
                active[movement] = count
            else:
                active.pop(movement, None)
        after = frozenset(active)
        if before != after:
            boundaries.add(time)
            if before:
                runs.append((run_start, time))
            run_start = time if after else None
            if event_times[0] < time < event_times[-1]:
                stats["protected_support_boundaries"] += 1
    if active:
        raise ArithmeticError("unclosed movement support")

    # Generate the global mesh only where positive interval mass is present.
    # Large empty time gaps therefore incur no grid allocation.
    for left, right in runs:
        if left + width_s == left or right - width_s == right:
            raise ArithmeticError("entry projection grid is below time resolution")
        ratio = left / width_s
        if not math.isfinite(ratio):
            raise ArithmeticError("entry projection grid ratio overflow")
        index = math.floor(ratio) + 1
        edge = index * width_s
        if edge <= left:  # rounding at an exactly represented mesh boundary
            index += 1
            edge = index * width_s
        previous = left
        while edge < right:
            if not math.isfinite(edge) or edge <= previous:
                raise ArithmeticError("entry projection grid cannot resolve width")
            boundaries.add(edge)
            if len(boundaries) > 2 * len(parts) + record_budget + 1:
                raise BudgetExceeded("entry projection grid record budget")
            previous = edge
            index += 1
            edge = index * width_s
    edges = sorted(boundaries)
    groups = defaultdict(dict)
    group_count = 0
    for p in parts:
        a, b = p.entry_start_s, p.entry_end_s
        if a == b:
            continue
        k = bisect_right(edges, a) - 1
        while k + 1 < len(edges) and edges[k] < b:
            lo, hi = max(a, edges[k]), min(b, edges[k+1])
            if hi > lo:
                fraction = (hi - lo) / (b - a)
                mass = p.mass * fraction
                if mass == 0:
                    raise ArithmeticError("positive entry projection mass underflow")
                key = p.tag, p.remaining
                if key not in groups[k]:
                    group_count += 1
                    if group_count > record_budget:
                        raise BudgetExceeded("entry projection record budget")
                    # Reference oracle retains summands for math.fsum. Native
                    # implementation uses a bounded compensated accumulator.
                    groups[k][key] = [p, [], [], [], lo, hi]
                data = groups[k][key]
                data[1].append(mass)
                data[2].append(p.birth_moment * fraction)
                data[3].append(mass * ((lo - edges[k]) + (hi - lo) / 2))
                data[4] = min(data[4], lo)
                data[5] = max(data[5], hi)
            k += 1

    output = []
    bounds = []
    records = 0
    for k, time in enumerate(edges):
        if time in atoms:
            rows = combine(atoms[time])
            records += len(rows)
            if records > record_budget:
                raise BudgetExceeded("entry projection point record budget")
            output.append(Packet(target_m, rows))
        if k not in groups:
            continue
        rows = []
        for key, (p, masses, births, relative, lo, hi) in sorted(groups[k].items()):
            mass, birth = math.fsum(masses), math.fsum(births)
            mean = time + math.fsum(relative) / mass
            if (not all(map(math.isfinite, (mass, birth, mean)))
                    or not lo <= mean <= hi):
                raise ArithmeticError("nonfinite or out-of-support projection moment")
            rows.append(replace(p, mass=mass, birth_moment=birth,
                                entry_start_s=mean, entry_end_s=mean))
            bound = (hi - lo) / 2 * mass
            if not math.isfinite(bound):
                raise ArithmeticError("entry projection local transport bound overflow")
            if bound:
                bounds.append(math.nextafter(bound, math.inf))
        records += len(rows)
        if records > record_budget:
            raise BudgetExceeded("entry projection record budget")
        output.append(Packet(target_m, tuple(rows)))
    stats.update(output_parts=records, cohorts=len(output),
                 local_w1_bound_veh_s=math.fsum(bounds))
    return tuple(output), stats
