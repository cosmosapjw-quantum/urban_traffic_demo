"""V03 physics counterexample suite for the native road owner and Python oracle.

Each case runs the independent Python scientific oracle (PacketNetwork) and the
native Rust road (NativeRoadNetwork / V1Road / NativeWholeEngine) on the exact
path (entry projection width h=0) and the named approximation
``entry_projection_support_v1`` (h>0). Tolerances are the PLAN numerical policy
only: mass relative 1e-9 and residence relative 1e-8, each scaled by
max(1, accumulated quantity); bit equality only where the code claims it
(h=0 interval endpoints, checkpoint roundtrip and replay).

Requires the extension built from this tree; an import failure is NOT_RUN, not
a behavioural RED.
"""
from collections import defaultdict
from dataclasses import asdict
import math

import pytest

from _metroflow_rust import NativeWholeEngine

from metroflow.active_suffix.common import BudgetExceeded
from metroflow.entry_projection import project_entry_packets
from metroflow.foundation_kinetics import VehicleClass
from metroflow.ordered_lane import Lane
from metroflow.ordered_network import Group, Route
from metroflow.packet_network import PacketNetwork, Part, interval_packets
from metroflow.v1.kinetics import ClassMass
from metroflow.v1.native_road import NativeRoadNetwork
from metroflow.v1.transport import FiniteResponseMotion

MASS_REL = 1e-9       # PLAN numerical_policy.mass_relative_tolerance
RESIDENCE_REL = 1e-8  # PLAN numerical_policy.residence_relative_tolerance
WIDTHS = (0.0, 0.25, 1.0)  # exact path and PLAN candidate projection widths

CAR = VehicleClass("car", preferred_mps=10)
BUS = VehicleClass("bus", preferred_mps=8, response_s=3, length_m=12)
FREIGHT = VehicleClass("freight", preferred_mps=7, length_m=9)
MOTION = FiniteResponseMotion(
    tuple(ClassMass(c, 1, latent=p, gap_scale_m=4)
          for c, p in ((CAR, .8), (BUS, .6), (FREIGHT, .9))),
    (("car", 8.), ("bus", 3.), ("freight", 5.)))
GAP_M = 2.0


def lane(length=10., entry=2., exit_=1.):
    return Lane(length_m=length, speed_mps=9, entry_rate=entry, exit_rate=exit_)


def network(groups, routes, classes, *, width=0., windows=(), budget=10000, space=200.):
    return PacketNetwork(
        groups, tuple(Route(k, v) for k, v in routes.items()), dt_s=1., windows=windows,
        record_budget=budget, vehicle_classes=classes,
        space_capacities_m={g.id: space.get(g.id, 200.) if isinstance(space, dict) else space
                            for g in groups},
        standing_gap_m=GAP_M, motion=MOTION, preserve_entry_intervals=True,
        entry_projection_width_s=width)


def tol(scale, rel=MASS_REL):
    return rel * max(1.0, abs(scale))


def assert_plan_close(actual, expected, path="state"):
    """Native-vs-oracle comparison at the PLAN mass tolerance (strictest)."""
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys(), path
        for key in expected:
            assert_plan_close(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(expected, (tuple, list)):
        assert len(actual) == len(expected), path
        for i, (a, e) in enumerate(zip(actual, expected)):
            assert_plan_close(a, e, f"{path}[{i}]")
    elif isinstance(expected, float):
        assert abs(actual - expected) <= tol(expected), (path, actual, expected)
    else:
        assert actual == expected, path


def observables(state):
    """Physical observables, independent of how a law is cut into records.

    Packet/record structure is NOT compared: equal real-arithmetic measures can
    be split into different numbers of records (see the ulp-contiguity case).
    """
    cells = []
    for c in state.cells:
        per_tag = defaultdict(lambda: [[], [], []])
        for packet in c.packets:
            for p in packet.parts:
                per_tag[p.tag][0].append(p.mass)
                per_tag[p.tag][1].append(p.birth_moment)
                per_tag[p.tag][2].append(p.mass * (p.entry_start_s + (p.entry_end_s - p.entry_start_s) / 2))
        cells.append(dict(
            scalars=[c.progress_m, c.activity, c.admitted, c.completed, c.entry_moment,
                     c.exit_moment, c.vehicle_metres, c.speed_mps],
            latent=dict(c.latent),
            tags={k: [math.fsum(x) for x in v] for k, v in sorted(per_tag.items())}))
    waiting = defaultdict(float)
    for i, q in enumerate(state.pending):
        for packet in q:
            for p in packet.parts:
                waiting[i, p.tag] += p.mass
    return dict(time=state.time_s, cells=cells, pending=dict(sorted(waiting.items())),
                totals=[state.released, state.completed, state.birth_moment, state.exit_moment,
                        state.source_wait_seconds, state.transfer_hold_seconds,
                        state.pre_entry_seconds],
                classes=[asdict(x) for x in state.class_ledger])


def event_observables(events):
    out = defaultdict(lambda: [[], [], []])
    for e in events:
        k = e.tag, e.source, e.destination
        out[k][0].append(e.mass)
        out[k][1].append(e.birth_moment)
        out[k][2].append(e.mass * (e.start_s + (e.end_s - e.start_s) / 2))
    return {k: [math.fsum(x) for x in v] for k, v in sorted(out.items(), key=str)}


def stored_by(state, key):
    out = defaultdict(float)
    for c in state.cells:
        for packet in c.packets:
            for p in packet.parts:
                out[key(p)] += p.mass
    for q in state.pending:
        for packet in q:
            for p in packet.parts:
                out[key(p)] += p.mass
    return out


class Ledger:
    """Independent per-tag book: released offers, sink completions, residence."""

    def __init__(self, ref):
        self.ref = ref
        self.released = defaultdict(float)
        self.completed = defaultdict(float)

    def record(self, offers, events):
        for tag, mass, *_ in offers:
            self.released[tag] += mass
        for e in events:
            if e.destination is None:
                self.completed[e.tag] += e.mass

    def check(self, state):
        self.ref.check(state)  # network/cell/class mass 1e-9 and residence 1e-8
        stored = stored_by(state, lambda p: p.tag)
        for tag in set(self.released) | set(stored):
            released = self.released[tag]
            gap = released - self.completed[tag] - stored[tag]
            assert abs(gap) <= tol(released), (tag, gap)
        residence = (math.fsum(c.residence(state.time_s) for c in state.cells)
                     + state.source_wait_seconds + state.transfer_hold_seconds
                     + state.pre_entry_seconds)
        assert abs(residence - state.system_vehicle_seconds) <= tol(residence, RESIDENCE_REL)


def run_pair(ref, schedule, ticks, dts=None):
    """Advance oracle and native in lockstep; compare every tick; return histories."""
    native = NativeRoadNetwork(ref)
    states = {"py": ref.initial(), "rs": native.initial()}
    books = {"py": Ledger(ref), "rs": Ledger(ref)}
    history = {"py": [], "rs": []}
    for k in range(ticks):
        dt = 1.0 if dts is None else dts[k]
        offers = list(schedule.get(k, ()))
        for name, model in (("py", ref), ("rs", native)):
            states[name], events = model.advance_interval(states[name], dt, offers)
            books[name].record(offers, events)
            books[name].check(states[name])
            history[name].append((states[name], events))
        assert_plan_close(observables(states["rs"]), observables(states["py"]), f"tick{k}")
        assert_plan_close(event_observables(history["rs"][-1][1]),
                          event_observables(history["py"][-1][1]), f"events{k}")
    return history, books


def tag_events(history, tag, source=None):
    return [e for _, events in history for e in events
            if e.tag == tag and (source is None or e.source == source)]


# 1. Tiny blocked-turn mass behind flowing traffic -----------------------------

@pytest.mark.parametrize("width", WIDTHS)
def test_tiny_blocked_turn_mass_is_neither_overtaken_nor_dropped(width):
    groups = (Group("u", "o", "j0", lane(entry=4., exit_=2.)),
              Group("a", "j0", "j", lane(entry=4., exit_=1.5)),
              Group("b", "j", "d1", lane(entry=4., exit_=4.)),
              Group("c", "j", "d2", lane(entry=4., exit_=4.)))
    routes = {"flow": ("u", "a", "b"), "blocked": ("u", "a", "c"), "late": ("u", "a", "b")}
    ref = network(groups, routes, {k: CAR for k in routes}, width=width,
                  windows=(("c", 0., 40., 0.),))
    tiny = 1e-12
    schedule = {0: [("flow", 3., 0.)], 2: [("blocked", tiny, 2. * tiny)], 3: [("late", 3., 9.)]}
    history, books = run_pair(ref, schedule, 90)
    for name in ("py", "rs"):
        h = history[name]
        # Not dropped: the tiny tag's own book closes relative to its own mass.
        done = 0.0
        for k, (state, events) in enumerate(h):
            done += math.fsum(e.mass for e in events if e.tag == "blocked" and not e.destination)
            held = stored_by(state, lambda p: p.tag)["blocked"]
            if k >= 2:
                assert abs(held + done - tiny) <= MASS_REL * tiny, (name, k)
        assert books[name].completed["blocked"] == pytest.approx(tiny, rel=MASS_REL)
        blocked_out = tag_events(h, "blocked", "a")
        late_out = tag_events(h, "late", "a")
        flow_out = tag_events(h, "flow", "a")
        assert blocked_out and late_out and flow_out
        # Closed turn holds the tiny head; FIFO holds the later lane mass behind it.
        assert min(e.start_s for e in blocked_out) >= 40. - 1e-9
        assert min(e.start_s for e in late_out) >= max(e.end_s for e in blocked_out) - 1e-9
        # Earlier open-only traffic is not poisoned by the later tiny closed-turn mass.
        assert max(e.end_s for e in flow_out) < 40.
        assert books[name].completed["late"] == pytest.approx(3., rel=MASS_REL)


# 2. Route divergence and reconvergence ---------------------------------------

ULP_SUPPORT_XFAIL = pytest.mark.xfail(strict=True, reason=(
    "DEFECT (consequence of the ulp event-boundary rounding below): at t=5 s the "
    "oracle emits y->m intervals [..,5.579099720472453] and [5.5790997204724535,..] "
    "(1-ulp gap) while native emits them contiguous. entry_projection_support_v1 "
    "treats the 1-ulp empty support as a protected boundary, so the two backends "
    "cut different projection cohorts; the cut changes exit timing and the bus "
    "latent in m differs by 1.1e-3 relative at t=9 s (PLAN mass tol 1e-9). "
    "Projection support detection is discontinuous in ulp-level event times."))


@pytest.mark.parametrize("width", (0.0, pytest.param(0.25, marks=ULP_SUPPORT_XFAIL), 1.0))
def test_divergence_reconvergence_preserves_tags_and_route_offsets(width):
    groups = (Group("s", "o", "j1", lane(entry=4., exit_=2.)),
              Group("x", "j1", "j2", lane(length=14., entry=3., exit_=1.2)),
              Group("y", "j1", "j2", lane(length=6., entry=3., exit_=.9)),
              Group("m", "j2", "j3", lane(entry=2., exit_=1.4)),
              Group("t", "j3", "d", lane(entry=4., exit_=4.)))
    routes = {"left": ("s", "x", "m", "t"), "right": ("s", "y", "m", "t"),
              "left2": ("s", "x", "m", "t"),  # equal path, distinct label
              "mid": ("x", "m", "t"),          # same suffix at a different offset
              "short": ("m", "t")}
    classes = {k: CAR for k in routes} | {"right": BUS}
    ref = network(groups, routes, classes, width=width)
    schedule = {0: [("left", 2., 0.), ("right", 1.5, 0.), ("left2", .5, 0.)],
                1: [("mid", 1., .5), ("short", .75, .25)],
                4: [("left", 1., 4.), ("right", .25, 1.)]}
    history, books = run_pair(ref, schedule, 80)
    native = NativeRoadNetwork(ref)
    index = ref.index
    tags = native.tags
    for name in ("py", "rs"):
        for state, events in history[name]:
            for e in events:  # every transfer is a consecutive pair on its own route
                path = routes[e.tag]
                k = path.index(e.source)
                assert path[k + 1:k + 2] == ((e.destination,) if e.destination else ())
            for g, c in zip(ref.groups, state.cells):
                for packet in c.packets:
                    for p in packet.parts:
                        assert p.remaining[0] == g.id
                        assert routes[p.tag][-len(p.remaining):] == p.remaining
        for tag, mass in books[name].released.items():
            assert books[name].completed[tag] == pytest.approx(mass, rel=MASS_REL)
    # Raw native offsets: offset indexes this part's own route at this cell.
    native.initial()
    for k in range(25):
        native.native.step(1., native._offers(schedule.get(k, ())))
        _, _, cells, pending, _, _ = native.native.snapshot()
        for i, (_, packets, _) in enumerate(cells):
            for _, parts in packets:
                for tag, offset, *_ in parts:
                    assert index[routes[tags[tag]][offset]] == i


# 3. Partial head service over many sub-steps ---------------------------------

@pytest.mark.parametrize("width", WIDTHS)
def test_repeated_partial_head_service_conserves_mass_birth_and_entry_moments(width):
    groups = (Group("a", "o", "j", lane(entry=2., exit_=.3)),
              Group("b", "j", "d", lane(length=2000., entry=50., exit_=50.)))
    ref = network(groups, {"car": ("a", "b"), "van": ("a", "b")},
                  {"car": CAR, "van": CAR}, width=width)
    births = {"car": 4. * 3., "van": 1.5 * 1.}  # original birth first moments [veh*s]
    offers = [("car", 4., births["car"]), ("van", 1.5, births["van"])]
    dts = [.1] * 350
    history, books = run_pair(ref, {50: offers}, len(dts), dts)  # offered at t=5 s
    for name in ("py", "rs"):
        last, _ = history[name][-1]
        assert last.completed == 0  # nothing has crossed the 2 km link yet
        moved = tag_events(history[name], "car") + tag_events(history[name], "van")
        assert len({(e.start_s, e.end_s) for e in moved}) > 50  # truly many partial services
        for tag, mass in (("car", 4.), ("van", 1.5)):
            out = [e for e in moved if e.tag == tag]
            in_a = [p for pk in last.cells[0].packets for p in pk.parts if p.tag == tag]
            in_a += [p for q in last.pending for pk in q for p in pk.parts if p.tag == tag]
            in_b = [p for pk in last.cells[1].packets for p in pk.parts if p.tag == tag]
            # Mass and birth moment: served + held upstream == offered.
            assert math.fsum([e.mass for e in out] + [p.mass for p in in_a]) == pytest.approx(
                mass, rel=MASS_REL)
            birth = math.fsum([e.birth_moment for e in out] + [p.birth_moment for p in in_a])
            assert abs(birth - births[tag]) <= tol(births[tag])
            # Mean birth per vehicle is invariant under proportional head service.
            for p in in_a:
                assert p.birth_moment / p.mass == pytest.approx(births[tag] / mass, rel=MASS_REL)
            # Downstream entry measure: mass, birth and entry first moment survive
            # the exact interval split (h=0) and the conservative projection (h>0).
            for value, expected in (
                    (math.fsum(p.mass for p in in_b), math.fsum(e.mass for e in out)),
                    (math.fsum(p.birth_moment for p in in_b), math.fsum(e.birth_moment for e in out)),
                    (math.fsum(p.mass * (p.entry_start_s + (p.entry_end_s - p.entry_start_s) / 2)
                               for p in in_b),
                     math.fsum(e.mass * (e.start_s + (e.end_s - e.start_s) / 2) for e in out))):
                assert abs(value - expected) <= tol(expected), (name, tag, value, expected)


# 4. Mixed vehicle classes in one packet --------------------------------------

@pytest.mark.parametrize("width", WIDTHS)
def test_mixed_class_packet_keeps_class_ledgers_and_physical_footprints(width):
    groups = (Group("a", "o", "j", lane(entry=3., exit_=.8)),
              Group("b", "j", "d", lane(entry=3., exit_=2.)))
    classes = {"car": CAR, "bus": BUS, "freight": FREIGHT}
    ref = network(groups, {k: ("a", "b") for k in classes}, classes, width=width,
                  space={"a": 30., "b": 200.})
    offered = {"car": 3., "bus": 1., "freight": 1.}  # 46 m of footprint > 30 m
    history, books = run_pair(ref, {0: [(k, m, 0.) for k, m in offered.items()]}, 80)
    footprint = {k: c.length_m + GAP_M for k, c in classes.items()}
    total = sum(offered.values())
    for name in ("py", "rs"):
        space_bound_seen = False
        for state, events in history[name]:
            for g, c in zip(ref.groups, state.cells):
                used = math.fsum(p.mass * footprint[p.tag] for pk in c.packets for p in pk.parts)
                assert used == pytest.approx(ref.occupied_space(c), rel=MASS_REL, abs=MASS_REL)
                assert used <= ref.space_capacities_m[g.id] * (1 + MASS_REL)
                space_bound_seen |= g.id == "a" and used > 30. * (1 - 1e-6)
            for ledger in state.class_ledger:
                held = stored_by(state, lambda p: classes[p.tag].name)[ledger.name]
                assert abs(ledger.released - ledger.completed - held) <= tol(ledger.released)
            # One exchangeable packet is served proportionally: class shares fixed.
            batches = defaultdict(dict)
            for e in events:
                if e.source == "a":
                    batches[e.start_s, e.end_s][e.tag] = e.mass
            for batch in batches.values():
                served = math.fsum(batch.values())
                for tag, mass in offered.items():
                    assert batch[tag] / served == pytest.approx(mass / total, rel=MASS_REL)
        assert space_bound_seen  # the 30 m footprint limit was actually binding
        final = history[name][-1][0]
        for ledger in final.class_ledger:
            assert ledger.completed == pytest.approx(offered[ledger.name], rel=MASS_REL)


# 5. Irregular interval splitting ----------------------------------------------

IRREGULAR = (Part("a", ("r", "x"), 1.3, .2, 0.11, 0.37),
             Part("b", ("r", "y"), .7, .1, 0.2, 0.93),
             Part("a", ("r", "x"), .4, .05, 0.37, 0.37),  # point atom at an edge
             Part("c", ("r", "x"), 2.1, .3, 0.5501, 1.7),
             Part("b", ("r", "y"), .9, .02, 1.25, 1.31))


def _moments(parts):
    out = defaultdict(lambda: [[], [], []])
    for p in parts:
        k = p.tag, p.remaining
        out[k][0].append(p.mass)
        out[k][1].append(p.birth_moment)
        out[k][2].append(p.mass * (p.entry_start_s + (p.entry_end_s - p.entry_start_s) / 2))
    return {k: tuple(math.fsum(v) for v in vs) for k, vs in out.items()}


def test_irregular_exact_split_keeps_every_input_edge_and_moments():
    packets = interval_packets(IRREGULAR, 5., 1000)
    edges = sorted({x for p in IRREGULAR for x in (p.entry_start_s, p.entry_end_s)})
    out = [p for pk in packets for p in pk.parts]
    # Every output interval is an elementary slice between adjacent input edges.
    for p in out:
        if p.entry_start_s != p.entry_end_s:
            k = edges.index(p.entry_start_s)
            assert edges[k + 1] == p.entry_end_s
    spans = [(min(p.entry_start_s for p in pk.parts), max(p.entry_end_s for p in pk.parts))
             for pk in packets]
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:]))  # FIFO, no overlap
    for key, expected in _moments(IRREGULAR).items():
        for value, want in zip(_moments(out)[key], expected):
            assert abs(value - want) <= tol(want)


@pytest.mark.parametrize("width", (.25, .3, 1.))
def test_irregular_projection_keeps_support_boundaries_atoms_and_moments(width):
    packets, stats = project_entry_packets(IRREGULAR, 5., 1000, width)
    out = [p for pk in packets for p in pk.parts]
    for key, expected in _moments(IRREGULAR).items():
        for value, want in zip(_moments(out)[key], expected):
            assert abs(value - want) <= tol(want)
    # Movement support {x}/{x,y} changes at .2,.93,1.25,1.31 (and starts/ends).
    boundaries = (0.11, 0.2, 0.93, 1.25, 1.31, 1.7)
    for pk in packets:
        means = [p.entry_start_s for p in pk.parts]
        assert all(p.entry_start_s == p.entry_end_s for p in pk.parts)
        seg = {sum(t >= b for b in boundaries) for t in means}
        assert len(seg) == 1 or means == [0.37] * len(means), (means, seg)
    assert [p for p in out if p.tag == "a" and p.mass == .4] == [IRREGULAR[2]]  # atom exact
    assert 0 < stats["local_w1_bound_veh_s"] <= width / 2 * math.fsum(
        p.mass for p in IRREGULAR) * (1 + 1e-12)


@pytest.mark.parametrize("width", WIDTHS)
def test_irregular_merging_intervals_native_matches_oracle_and_keeps_fifo(width):
    groups = (Group("u1", "o1", "j", lane(entry=3., exit_=.73)),
              Group("u2", "o2", "j", lane(length=17., entry=3., exit_=1.37), priority=2.),
              Group("m", "j", "k", lane(length=500., entry=1.6, exit_=1.)),
              Group("x", "k", "d", lane(entry=3., exit_=3.)))
    routes = {"p": ("u1", "m", "x"), "q": ("u2", "m", "x"), "r": ("u1", "m", "x")}
    ref = network(groups, routes, {"p": CAR, "q": FREIGHT, "r": BUS}, width=width)
    dts = [.37, 1.13, .29, .71, 2.03, .5, 1.61, .07, .93] * 6
    schedule = {0: [("p", 2., 0.), ("q", 1.5, 0.)], 3: [("r", .6, .5)], 7: [("q", .8, 3.)]}
    history, _ = run_pair(ref, schedule, len(dts), dts)
    for name in ("py", "rs"):
        into_m = [e for _, events in history[name] for e in events if e.destination == "m"]
        cell = history[name][-1][0].cells[ref.index["m"]]
        assert cell.packets
        spans = [(min(p.entry_start_s for p in pk.parts), max(p.entry_end_s for p in pk.parts))
                 for pk in cell.packets]
        assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:]))  # FIFO entry order
        if width == 0:
            # Exact path: retained endpoints are bitwise transfer event times.
            event_times = {t for e in into_m for t in (e.start_s, e.end_s)}
            for pk in cell.packets:
                for p in pk.parts:
                    assert p.entry_start_s in event_times and p.entry_end_s in event_times
            assert any(pk.parts[0].entry_start_s < pk.parts[0].entry_end_s for pk in cell.packets)


@pytest.mark.parametrize("backend", ("py", "rs"))
@pytest.mark.xfail(strict=True, reason=(
    "DEFECT (oracle and native, representation): consecutive junction events "
    "use end=(t+cursor)+h but the next start=t+(cursor+h); the two roundings "
    "differ by 1 ulp, so transfer intervals into one destination overlap (or "
    "gap) by an ulp although they are sequential in real arithmetic. The exact "
    "interval law (h=0) then cuts an extra ulp-wide sliver packet holding every "
    "category (spurious records and ulp-scale FIFO overlap; mass error ~1e-15). "
    "Python and Rust round differently, so record counts diverge."))
def test_transfer_intervals_into_one_destination_are_contiguous_not_overlapping(backend):
    groups = (Group("s", "o", "j1", lane(entry=4., exit_=2.)),
              Group("x", "j1", "j2", lane(length=14., entry=3., exit_=1.2)),
              Group("y", "j1", "j2", lane(length=6., entry=3., exit_=.9)),
              Group("m", "j2", "j3", lane(entry=2., exit_=1.4)),
              Group("t", "j3", "d", lane(entry=4., exit_=4.)))
    routes = {"left": ("s", "x", "m", "t"), "right": ("s", "y", "m", "t"),
              "left2": ("s", "x", "m", "t"), "mid": ("x", "m", "t"), "short": ("m", "t")}
    ref = network(groups, routes, {k: CAR for k in routes} | {"right": BUS})
    model = ref if backend == "py" else NativeRoadNetwork(ref)
    schedule = {0: [("left", 2., 0.), ("right", 1.5, 0.), ("left2", .5, 0.)],
                1: [("mid", 1., .5), ("short", .75, .25)],
                4: [("left", 1., 4.), ("right", .25, 1.)]}
    state = model.initial()
    overlaps = []
    for k in range(80):
        state, events = model.advance_interval(state, 1., schedule.get(k, ()))
        spans = defaultdict(set)
        for e in events:
            if e.destination:  # one destination is fed by exactly one junction loop
                spans[e.destination].add((e.start_s, e.end_s))
        for dest, rows in spans.items():
            rows = sorted(rows)
            overlaps += [(k, dest, a, b) for a, b in zip(rows, rows[1:]) if b[0] < a[1]]
    assert not overlaps, overlaps[:3]


# 6. Empty time gaps between arrivals ------------------------------------------

@pytest.mark.parametrize("width", WIDTHS)
def test_empty_gap_is_time_translation_invariant_and_allocates_nothing(width):
    groups = (Group("a", "o", "j", lane(entry=1.5, exit_=.6)),
              Group("b", "j", "d", lane(entry=1.5, exit_=.9)))
    ref = network(groups, {"car": ("a", "b"), "bus": ("a", "b")},
                  {"car": CAR, "bus": BUS}, width=width)
    wave = [("car", 1.7, 0.), ("bus", .3, 0.)]
    # 40 unit ticks, one empty 360 s interval, 40 unit ticks: second wave at 400 s.
    dts = [1.] * 40 + [360.] + [1.] * 40
    history, books = run_pair(ref, {0: wave, 41: [("car", 1.7, 1.7 * 400.), ("bus", .3, .3 * 400.)]},
                              len(dts), dts)
    for name in ("py", "rs"):
        h = history[name]
        assert h[40][0].time_s == 400.
        empty = h[39][0]
        assert sum(len(c.packets) for c in empty.cells) == 0 and not any(empty.pending)
        assert h[40][1] == ()
        assert h[40][0].cells == empty.cells or all(
            not c.packets for c in h[40][0].cells)
        first = [e for _, ev in h[:40] for e in ev]
        second = [e for _, ev in h[41:] for e in ev]
        assert len(first) == len(second) > 0
        for a, b in zip(first, second):
            assert (a.tag, a.source, a.destination) == (b.tag, b.source, b.destination)
            assert abs(b.mass - a.mass) <= tol(a.mass)
            assert abs((b.start_s - 400.) - a.start_s) <= tol(b.start_s)
            assert abs((b.end_s - 400.) - a.end_s) <= tol(b.end_s)
        assert books[name].completed["car"] == pytest.approx(3.4, rel=MASS_REL)
    native = NativeRoadNetwork(ref)
    state = native.initial()
    state, _ = native.advance_interval(state, 360.)
    assert native.projection_diagnostics()["input_parts"] == 0


# 7. Floating-point underflow ---------------------------------------------------

def _subnormal_trial(model, offers, ticks=80):
    state = model.initial()
    done = 0.0
    for k in range(ticks):
        state, events = model.advance_interval(state, 1., offers if k == 0 else ())
        done += math.fsum(e.mass for e in events if e.tag == "tiny" and e.destination is None)
    held = stored_by(state, lambda p: p.tag)["tiny"]
    return done, held, state


def _subnormal_network(width=0.):
    groups = (Group("a", "o", "j", lane(entry=1., exit_=1.)),
              Group("b", "j", "d", lane(entry=50., exit_=50.)))
    return network(groups, {"big": ("a", "b"), "tiny": ("a", "b")},
                   {"big": CAR, "tiny": CAR}, width=width)


@pytest.mark.parametrize("backend", ("py", "rs"))
def test_lone_subnormal_mass_is_carried_exactly_or_fails_explicitly(backend):
    """Observed: neither backend can transport a lone 1-ulp vehicle mass, and
    both refuse explicitly (oracle: ValueError from the T02 gap law at the first
    motion tick; native: ArithmeticError 'event resolution exhausted' at the
    junction, h=mass/rate=0). Explicit refusal is not silent pruning."""
    ref = _subnormal_network()
    model = ref if backend == "py" else NativeRoadNetwork(ref)
    tiny = math.ulp(0.)
    state = model.initial()
    state, _ = model.advance_interval(state, 1., [("tiny", tiny, 0.)])
    snapshot = state
    try:
        done, held = 0.0, 0.0
        for _ in range(40):
            state, events = model.advance_interval(state, 1.)
            done += math.fsum(e.mass for e in events if not e.destination)
        held = stored_by(state, lambda p: p.tag)["tiny"]
    except (ArithmeticError, ValueError):
        ref.check(snapshot)  # immutable committed state is still valid
        assert stored_by(snapshot, lambda p: p.tag)["tiny"] == tiny
        return
    assert done + held == tiny


@pytest.mark.parametrize("backend", ("py", "rs"))
@pytest.mark.xfail(strict=True, reason=(
    "DEFECT (oracle and native, h=0): proportional partial service/admission "
    "drops a positive part whose scaled mass underflows. packet_network._portion "
    "and v1_road.rs portion() keep a part only if mass*f > 0, so a 1-ulp "
    "subnormal part sharing a packet with 2 veh at f=0.5 rounds to 0 in both the "
    "served and the remaining portion and vanishes without error; the 1e-9 "
    "absolute ledger floor cannot see it. entry_projection raises "
    "ArithmeticError for the same underflow."))
def test_subnormal_part_in_partially_served_packet_does_not_silently_vanish(backend):
    ref = _subnormal_network()
    model = ref if backend == "py" else NativeRoadNetwork(ref)
    tiny = math.ulp(0.)
    try:
        done, held, _ = _subnormal_trial(model, [("big", 2., 0.), ("tiny", tiny, 0.)])
    except ArithmeticError:
        return  # explicit failure is an acceptable contract
    assert done + held > 0, "positive subnormal mass vanished silently"


@pytest.mark.parametrize("backend", ("py", "rs"))
@pytest.mark.parametrize("width", (.25, 1.))
def test_projection_underflow_fails_explicitly_or_carries_exactly(backend, width):
    """Observed: h=0.25 refuses ('projection ... underflow'), h=1 carries exactly."""
    ref = _subnormal_network(width)
    model = ref if backend == "py" else NativeRoadNetwork(ref)
    tiny = math.ulp(0.)
    state = model.initial()
    state, _ = model.advance_interval(state, 1., [("big", 1., 0.), ("tiny", tiny, 0.)])
    done = 0.0
    for _ in range(40):
        try:
            state, events = model.advance_interval(state, 1.)
        except ArithmeticError as exc:
            assert "underflow" in str(exc)
            assert exc.checkpoint == state
            ref.check(exc.checkpoint)
            assert stored_by(state, lambda p: p.tag)["tiny"] + done == tiny
            return
        done += math.fsum(e.mass for e in events if e.tag == "tiny" and not e.destination)
    assert done + stored_by(state, lambda p: p.tag)["tiny"] == tiny


# 8. Checkpoint save/load/resume equality --------------------------------------

def _road_checkpoint_case(width):
    groups = (Group("a", "o", "j", lane(entry=2., exit_=.7)),
              Group("b", "j", "d", lane(entry=1., exit_=.9)),
              Group("c", "j", "e", lane(entry=1., exit_=1.1)))
    routes = {"car": ("a", "b"), "bus": ("a", "c"), "freight": ("a", "b")}
    return network(groups, routes, {"car": CAR, "bus": BUS, "freight": FREIGHT}, width=width)


@pytest.mark.parametrize("width", WIDTHS)
def test_road_checkpoint_roundtrip_and_resumed_trajectory_are_bit_identical(width):
    ref = _road_checkpoint_case(width)
    offers = {0: [("car", 2., 0.), ("bus", .5, 0.)], 2: [("freight", 1., 1.)], 5: [("car", .3, 1.)]}
    native = NativeRoadNetwork(ref)
    state = native.initial()
    for k in range(9):
        state, _ = native.advance_interval(state, 1., offers.get(k, ()))
    raw = native.native.snapshot()
    # Raw native tuple roundtrip into a fresh owner (bit equality).
    fresh = NativeRoadNetwork(ref)
    fresh.native.restore(raw)
    assert fresh.native.snapshot() == raw
    # Python dataclass boundary roundtrip into another fresh owner.
    other = NativeRoadNetwork(ref)
    other.restore(state)
    assert other.native.snapshot() == raw
    a, b, c = state, fresh.snapshot(), other.snapshot()
    assert a == b == c
    for k in range(9, 40):
        step = offers.get(k, ())
        a, ea = native.advance_interval(a, 1., step)
        b, eb = fresh.advance_interval(b, 1., step)
        c, ec = other.advance_interval(c, 1., step)
        assert a == b == c and ea == eb == ec
    assert native.native.snapshot() == fresh.native.snapshot() == other.native.snapshot()
    # Oracle restore from the native checkpoint continues to the same physics.
    oracle, _ = ref.advance_interval(state, 1.)
    resumed, _ = NativeRoadNetwork(ref).advance_interval(state, 1.)
    assert_plan_close(asdict(resumed), asdict(oracle))


def _assert_unit_ledgers(report):
    for unit, row in report["ledger"].items():
        scale = max(abs(row["requested"]), abs(row["released"]))
        assert abs(row["requested"] - row["released"] - row["pending"]) <= tol(scale), unit
        assert abs(row["released"] - row["completed"] - row["active"]) <= tol(scale), unit
        assert row["active"] >= -tol(scale) and row["pending"] >= -tol(scale), unit


@pytest.mark.parametrize("width", (0., .25))
def test_whole_engine_save_load_resume_is_identical_and_unit_ledgers_close(tmp_path, width):
    from test_native_engine import make_native, small_fixture

    city, legs, corridors = small_fixture()
    _, calendar, payload = make_native(city, legs, corridors)

    def engine():
        return NativeWholeEngine(calendar, payload, 256 * 1024**2,
                                 entry_projection_width_s=width)

    native = engine()
    middle = native.advance(native.initial(), 30.)
    before = native.report(middle)
    path = tmp_path / "middle.bin"
    native.save(str(path), middle)
    fresh = engine()
    restored = fresh.load(str(path))
    assert fresh.report(restored) == before
    again = tmp_path / "again.bin"
    fresh.save(str(again), restored)
    assert again.read_bytes() == path.read_bytes()
    a, b = native.advance(middle, 120.), fresh.advance(restored, 120.)
    ra, rb = native.report(a), fresh.report(b)
    assert ra == rb
    assert native.sample_legs(a, list(range(5))) == fresh.sample_legs(b, list(range(5)))
    left, right = tmp_path / "left.bin", tmp_path / "right.bin"
    native.save(str(left), a)
    fresh.save(str(right), b)
    assert left.read_bytes() == right.read_bytes()
    for report in (before, ra):
        _assert_unit_ledgers(report)
    assert set(ra["ledger"]) == {"persons", "vehicles", "cargo_kg"}
    assert ra["ledger"]["cargo_kg"]["completed"] == pytest.approx(100., rel=MASS_REL)
    assert native.report(middle) == before  # later advances leave the snapshot immutable


# 9. Allocation/budget failure and rollback ------------------------------------

@pytest.mark.parametrize("width", WIDTHS)
def test_byte_budget_failure_rolls_back_and_retry_matches_uninterrupted(width):
    ref = _road_checkpoint_case(width)
    offers = {0: [("car", 2., 0.), ("bus", .5, 0.)], 3: [("freight", 1., 2.)],
              4: [("car", .7, 2.), ("bus", .2, .1), ("freight", .3, .2)]}
    control = NativeRoadNetwork(ref)
    state = control.initial()
    for k in range(12):
        state, _ = control.advance_interval(state, 1., offers.get(k, ()))
    expected = control.native.snapshot()

    native = NativeRoadNetwork(ref)
    s = native.initial()
    for k in range(4):
        s, _ = native.advance_interval(s, 1., offers.get(k, ()))
    # A budget too small for the committed state is refused atomically ...
    limits = native.native.storage_limits()
    with pytest.raises(MemoryError, match="storage budget"):
        native.native.configure_storage_budget(1024)
    assert native.native.storage_limits() == limits
    # ... the smallest accepted budget holds the state but not the next tick.
    lo, hi = 1, 1 << 30
    while lo < hi:
        mid = (lo + hi) // 2
        try:
            native.native.configure_storage_budget(mid)
            hi = mid
        except MemoryError:
            lo = mid + 1
    native.native.configure_storage_budget(lo)
    raw, diagnostics = native.native.snapshot(), native.projection_diagnostics()
    with pytest.raises(BudgetExceeded, match="storage budget") as failure:
        native.advance_interval(s, 1., offers.get(4, ()))
    assert failure.value.checkpoint is s
    assert native.native.snapshot() == raw
    assert native.projection_diagnostics() == diagnostics
    native.native.configure_storage_budget(256 * 1024**2)
    for k in range(4, 12):
        s, _ = native.advance_interval(s, 1., offers.get(k, ()))
    assert native.native.snapshot() == expected


@pytest.mark.parametrize("width", WIDTHS)
def test_oracle_record_budget_failure_keeps_committed_state(width):
    ref = _road_checkpoint_case(width)
    tight = network(ref.groups, dict(ref.routes), dict(ref.vehicle_classes), width=width, budget=3)
    state = tight.initial()
    state, _ = tight.advance_interval(state, 1., [("car", 1., 0.)])
    with pytest.raises(BudgetExceeded) as failure:
        for _ in range(20):
            state, _ = tight.advance_interval(state, 1., [("bus", .5, 0.), ("freight", .5, 0.)])
    assert failure.value.checkpoint == state
    tight.check(failure.value.checkpoint)


def test_whole_engine_budget_failure_keeps_last_valid_checkpoint(tmp_path):
    from test_native_engine import make_native, small_fixture

    city, legs, corridors = small_fixture()
    limited, calendar, payload = make_native(city, legs, corridors, record_budget=1)
    initial = limited.initial()
    path = tmp_path / "valid.bin"
    limited.save(str(path), initial)
    saved = path.read_bytes()
    report = limited.report(initial)
    with pytest.raises(MemoryError, match="budget"):
        limited.advance(initial, 120.)
    assert limited.report(initial) == report
    limited.save(str(path), initial)
    assert path.read_bytes() == saved
    limited.check(initial)
    restored = limited.load(str(path))
    assert limited.report(restored) == report
