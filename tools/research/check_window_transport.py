"""Fraction reference for conservative, windowed tag reconstruction on a FIFO merge."""
from collections import defaultdict, deque
from fractions import Fraction as F
import hashlib
import json
from time import perf_counter

ZERO = F(0)
ONE = F(1)


DELAYS = (1, 3, 7)


def delay_weights(label):
    a = F(1 + label % 3, 8)
    b = F(1 + label % 2, 8)
    return a, b, 1 - a - b


def observations(epoch, ticks):
    cuts = tuple(F(epoch <= ticks - d) for d in DELAYS)
    return (ONE, F(20 + epoch), F(epoch <= ticks // 2), ZERO, *cuts)


def initial_fibres(tags, ticks):
    """Two simultaneously ready heads with heterogeneous, partly overlapping labels."""
    roots = []
    for origin, total in enumerate((2 * ticks + 3, ticks + 2)):
        weights = [1 + ((7 * k + origin) % 11) for k in range(tags)]
        weight = sum(weights)
        heads = {}
        for k, n in enumerate(weights):
            label = k + origin * (tags // 2)
            mass = F(total * n, weight)
            birth = mass * (1 + (k + 5 * origin) % 17)
            heads[label] = (mass, birth)
        roots.append(heads)
    return roots


def next_admissions(left, right, queued, epoch):
    """One-second step. Shared receiver is constrained by free storage (veh).
    Weighted max-min merge with priorities 1:2 and separate sending limits.
    """
    free = max(ZERO, F(9) - queued)
    receiving = min(free, (F(9), F(4), F(0), F(7))[epoch % 4])
    a = min(left, (F(5), F(1), F(4))[epoch % 3])
    b = min(right, (F(2), F(7), F(1), F(3))[epoch % 4])
    if a + b <= receiving:
        return a, b
    level = min(receiving / 3, a, b / 2)
    da, db = level, 2 * level
    if da == a:
        db = min(b, receiving - da)
    elif db == b:
        da = min(a, receiving - db)
    return da, db


def sink_cap(epoch):
    return (F(0), F(1), F(3), F(2), F(4))[epoch % 5]


def eager(tags, ticks):
    bins = initial_fibres(tags, ticks) + [{} for _ in range(ticks)]
    pending = deque()
    rewards = [defaultdict(lambda: (ZERO, ZERO)) for _ in range(4 + len(DELAYS))]
    due = defaultdict(lambda: ZERO)
    tape_signature = []
    history = []

    def stock(i):
        return sum((v[0] for v in bins[i].values()), ZERO)

    def move(i, j, amount, epoch):
        old = stock(i)
        fraction = amount / old
        tape_signature.append((i, j, fraction, epoch))
        rows = []
        for k, (mass, birth) in list(bins[i].items()):
            x, y = fraction * mass, fraction * birth
            rows.append((k, x, y))
            if fraction == 1:
                del bins[i][k]
            else:
                bins[i][k] = mass - x, birth - y
            if j is not None:
                a, b = bins[j].get(k, (ZERO, ZERO))
                bins[j][k] = a + x, b + y
            else:
                for delay, weight in zip(DELAYS, delay_weights(k)):
                    if epoch + delay <= ticks:
                        due[k] += weight * x
                for field, multiplier in zip(rewards, observations(epoch, ticks)):
                    if multiplier:
                        a, b = field[k]
                        field[k] = a + multiplier * x, b + multiplier * y
        history.append(rows)

    for epoch in range(1, ticks + 1):
        cap = sink_cap(epoch)
        while cap > 0 and pending:
            head = pending[0]
            amount = min(cap, stock(head))
            move(head, None, amount, epoch)
            cap -= amount
            if not bins[head]:
                pending.popleft()
        occupancy = sum((stock(j) for j in pending), ZERO)
        left, right = next_admissions(stock(0), stock(1), occupancy, epoch)
        j = epoch + 1
        for i, amount in enumerate((left, right)):
            if amount:
                move(i, j, amount, epoch)
        if bins[j]:
            pending.append(j)
    for tab in bins:
        for k, (x, y) in tab.items():
            a, b = rewards[3][k]
            rewards[3][k] = a + x, b + y
    return tape_signature, rewards, due, sum(map(len, history))


def quotient(tags, ticks):
    roots = initial_fibres(tags, ticks)
    bins = [sum((v[0] for v in tab.values()), ZERO) for tab in roots] + [ZERO] * ticks
    pending = deque()
    queued = ZERO
    tape = []

    def move(i, j, amount, epoch):
        tape.append((i, j, amount / bins[i], epoch))
        bins[i] -= amount
        if j is not None:
            bins[j] += amount

    for epoch in range(1, ticks + 1):
        cap = sink_cap(epoch)
        while pending and cap > 0:
            i = pending[0]
            amount = min(cap, bins[i])
            move(i, None, amount, epoch)
            queued -= amount
            cap -= amount
            if bins[i] == 0:
                pending.popleft()
        offered = next_admissions(bins[0], bins[1], queued, epoch)
        j = epoch + 1
        for i, amount in enumerate(offered):
            if amount:
                move(i, j, amount, epoch)
                queued += amount
        if bins[j] > 0:
            pending.append(j)
    values = []
    for obs in range(4 + len(DELAYS)):
        lam = [F(obs == 3)] * len(bins)
        for i, j, f, t in reversed(tape):
            next_weight = lam[j] if j is not None else observations(t, ticks)[obs]
            lam[i] = (ONE - f) * lam[i] + f * next_weight
        value = defaultdict(lambda: (ZERO, ZERO))
        for i, tab in enumerate(roots):
            for k, (x, y) in tab.items():
                a, b = value[k]
                value[k] = a + lam[i]*x, b + lam[i]*y
        values.append(value)
    return tape, values


def check(tags, ticks):
    start = perf_counter()
    events, eager_fields, due, rows = eager(tags, ticks)
    eager_s = perf_counter() - start
    start = perf_counter()
    tape, fields = quotient(tags, ticks)
    compressed_s = perf_counter() - start
    assert tape == events
    roots = initial_fibres(tags, ticks)
    all_keys = sorted(set().union(*roots))
    digest = hashlib.sha256()
    for k in all_keys:
        assert sum((fields[4 + j][k][0] * w for j, w in enumerate(delay_weights(k))), ZERO) == due[k]
        attributes = (ONE, F(1+k%4), F(0 if k%3 else 20+k%401))
        for field, reference in zip(fields, eager_fields):
            assert field[k] == reference[k]
            for attr in attributes:
                digest.update(str(tuple(val*attr for val in field[k])).encode())
        original = [sum((tab.get(k, (ZERO, ZERO))[v] for tab in roots), ZERO) for v in range(2)]
        assert all(fields[0][k][v] + fields[3][k][v] == original[v] for v in range(2))
    return dict(tags_per_input=tags, seconds=ticks, physical_transfers=len(events),
                ordered_event_rows_eager=rows, passive_source_rows=2*tags,
                sparse_transfer_records=len(tape), payoff_masks_evaluated=4+len(DELAYS), delay_support_s=DELAYS,
                reverse_scalar_event_updates=(4+len(DELAYS))*len(tape), eager_s=round(eager_s, 4),
                reverse_pipeline_s=round(compressed_s, 4), joint_observer_sha256=digest.hexdigest())


def feedback_witness():
    # Same quotient totals, the bus threshold probes the identity of one active label.
    for bus_mass in (F(1,4), F(3,4)):
        car_mass = 1 - bus_mass
        assert bus_mass + car_mass == 1
        opens_gate = bus_mass > F(1,2)
        assert opens_gate == (bus_mass == F(3,4))
    return "equal physical total, different threshold state"


if __name__ == "__main__":
    sizes = ((8,8), (24,24), (48,48), (96,96))
    print(json.dumps(dict(runs=[check(*s) for s in sizes], feedback=feedback_witness()),
                     indent=2))
