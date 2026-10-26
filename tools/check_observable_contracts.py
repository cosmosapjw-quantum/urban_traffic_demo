"""Fresh observable-level transformations of a frozen city experiment."""

from pathlib import Path
from dataclasses import replace
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from metroflow.ordered_lane import Lane
from metroflow.ordered_network import Group, Route
from metroflow.packet_network import PacketNetwork
from metroflow.active_suffix.common import Signal


def main(out):
    path = Path("artifacts/block_flux_20261025/plan_polycentric_river_dt1.json")
    data = json.loads(path.read_text())
    groups = tuple(
        Group(
            g["id"],
            g["tail"],
            g["head"],
            Lane(**g["physics"]),
            g["priority"],
            Signal(**g["signal"]) if g["signal"] else None,
        )
        for g in data["groups"]
    )
    routes = tuple(Route(r["tag"], tuple(r["groups"])) for r in data["routes"])
    gs = {g.id: f"renamed_group_{len(groups) - i:04}" for i, g in enumerate(groups)}
    ns = {
        n: f"renamed_node_{i:04}"
        for i, n in enumerate(sorted({v for g in groups for v in (g.tail, g.head)}, reverse=True))
    }
    ts = {r.tag: f"renamed_observer_{len(routes) - i:04}" for i, r in enumerate(routes)}
    alt_groups = tuple(
        replace(g, id=gs[g.id], tail=ns[g.tail], head=ns[g.head]) for g in reversed(groups)
    )
    alt_routes = tuple(Route(ts[r.tag], tuple(gs[k] for k in r.groups)) for r in reversed(routes))
    a = PacketNetwork(groups, routes, record_budget=20000)
    b = PacketNetwork(alt_groups, alt_routes, record_budget=20000)
    x, y = a.initial(), b.initial()
    max_occ = max_done = max_res = max_tag_mass = max_tag_moment = 0.0
    tagmass = {r.tag: 0.0 for r in routes}
    altmass = dict(tagmass)
    tagmoment = dict(tagmass)
    altmoment = dict(tagmass)
    inverse = {v: k for k, v in ts.items()}
    count_equal = True
    for k in range(300):
        offers = tuple((tag, m / 60) for tag, m in data["amounts"]) if k < 60 else ()
        x, ex = a.step(x, offers)
        y, ey = b.step(y, tuple((ts[tag], m) for tag, m in reversed(offers)))
        for ev in ex:
            if ev.destination is None:
                tagmass[ev.tag] += ev.mass
                tagmoment[ev.tag] += ev.mass * (ev.start_s + ev.end_s) / 2
        for ev in ey:
            if ev.destination is None:
                tag = inverse[ev.tag]
                altmass[tag] += ev.mass
                altmoment[tag] += ev.mass * (ev.start_s + ev.end_s) / 2
        max_occ = max(
            max_occ,
            max(abs(x.cells[a.index[g]].occupancy - y.cells[b.index[gs[g]]].occupancy) for g in gs),
        )
        max_done = max(max_done, abs(x.completed - y.completed))
        max_res = max(max_res, abs(x.system_vehicle_seconds - y.system_vehicle_seconds))
        max_tag_mass = max(max_tag_mass, max(abs(tagmass[t] - altmass[t]) for t in ts))
        max_tag_moment = max(max_tag_moment, max(abs(tagmoment[t] - altmoment[t]) for t in ts))
        count_equal &= a.counts(x) == b.counts(y)
    assert a.identity != b.identity
    assert max_occ < 1e-9 and max_done < 1e-9 and max_res < 1e-7 and max_tag_moment < 1e-7
    result = dict(
        kind="representation relabeling, not a new physical network",
        steps=300,
        groups=len(groups),
        routes=len(routes),
        ids_changed=True,
        raw_identity_changes=True,
        max_occupancy_difference=max_occ,
        max_completed_difference=max_done,
        max_system_residence_difference=max_res,
        max_tag_mass_difference=max_tag_mass,
        max_tag_exit_moment_difference=max_tag_moment,
        record_counts_equal=count_equal,
        completed=x.completed,
        status="PASS_SCOPED",
    )
    # Physical similarity across different capacities/masses, not a fixed-city gauge.
    base = (
        Group("a", "O", "M", Lane(20.0, 10.0, 1.0, 1.0, 30.0)),
        Group("b", "M", "D", Lane(20.0, 10.0, 1.0, 1.0, 30.0)),
    )
    scaled = tuple(
        replace(g, physics=replace(g.physics, entry_rate=1000.0, exit_rate=1000.0, storage=30000.0))
        for g in base
    )
    r = (Route("flow", ("a", "b")),)
    m, n = PacketNetwork(base, r), PacketNetwork(scaled, r)
    p, q = m.initial(), n.initial()
    error = 0.0
    same = True
    for k in range(120):
        p, _ = m.step(p, (("flow", 10.0),) if k == 0 else ())
        q, _ = n.step(q, (("flow", 10000.0),) if k == 0 else ())
        error = max(
            error,
            abs(q.completed / 1000 - p.completed),
            *(abs(v.occupancy / 1000 - u.occupancy) for u, v in zip(p.cells, q.cells)),
        )
        same &= m.counts(p) == n.counts(q)
    assert error < 1e-10
    result["scaled_family"] = dict(
        factor=1000,
        max_normalized_difference=error,
        same_record_counts=same,
        scope="mass, storage and service rates jointly scaled; not fixed-road increased demand",
    )
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main(
        sys.argv[1]
        if len(sys.argv) > 1
        else "artifacts/symmetry_observables_20261025/TRANSFORMS.json"
    )
