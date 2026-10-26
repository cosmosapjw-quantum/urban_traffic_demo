"""Small adversarial controls. Numerical evidence, not empirical validation."""

from pathlib import Path
from dataclasses import replace
from collections import Counter
import json
import math
import platform
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from metroflow.audit_observables import (
    speed_measure,
    ring_requirements,
    ovm_modes,
    edie_observables,
)
from metroflow.active_suffix import Road, Demand, Config
from metroflow.active_suffix.packed import PackedModel
from metroflow.active_suffix.node import allocate
from metroflow.environment.terrain import Terrain, Rect, compile_network, synthetic_terrain
from metroflow.environment.landuse import zone_city


def overtaking():
    roads = (
        Road("r", "O", "J", 100.0, 10.0, 1.0, 30.0),
        Road("a", "J", "A", 10.0, 10.0, 1.0, 30.0),
        Road("b", "J", "B", 10.0, 10.0, 1.0, 30.0),
    )
    demands = (Demand("O", "A", 0.0, 1.0, 0.1), Demand("O", "B", 10.0, 11.0, 0.1))
    model = PackedModel(
        roads,
        demands,
        Config(dt_s=1.0, paths_per_od=1, interaction_rate_s=0.0, route_refresh_s=10.0),
    )
    state = model.initial()
    a = list(state.activity)
    a[model.index["r"]] = 0.1
    state = replace(state, activity=tuple(a))
    rows = []
    for _ in range(60):
        previous = state
        state = model.step(state)
        for key in ("r", "a", "b"):
            delta = state.link_outflow[model.index[key]] - previous.link_outflow[model.index[key]]
            if delta > 1e-12:
                rows.append(dict(end_of_interval_s=state.tick, link=key, mass=delta))
    # The identities are aggregate route classes, not newly-created per-car IDs.
    return dict(
        status="CONFIRMED_OPEN",
        scope="single shared no-passing link reference; not a universal multi-lane constraint",
        first_early_destination_s=min(r["end_of_interval_s"] for r in rows if r["link"] == "a"),
        first_late_destination_s=min(r["end_of_interval_s"] for r in rows if r["link"] == "b"),
        early_release_interval_s=[0, 1],
        late_release_interval_s=[10, 11],
        events=rows,
        completed_mass=state.completed,
        not_fixed=True,
    )


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    industrial = []
    for n in (8, 12):
        size = 100.0 * n
        t = Terrain(
            n,
            100.0,
            (0.0,) * ((n + 1) ** 2),
            protected=(Rect(0.70 * size, 0.0, size, 0.21 * size),),
        )
        city = zone_city(t, compile_network(t), 0, 0)
        counts = Counter(z.use for z in city.zones)
        industrial.append(dict(n=n, industrial=counts["industrial"], buffer=counts["buffer"]))
        assert counts["industrial"] == counts["buffer"] == 0
    stock = []
    for seed in (7, 17, 41):
        t = synthetic_terrain(n=12, seed=seed)
        city = zone_city(t, compile_network(t), 100000, 40000)
        stock.append(
            dict(
                seed=seed,
                residents=sum(z.residents for z in city.zones),
                jobs=sum(z.jobs for z in city.zones),
                zones=dict(Counter(z.use for z in city.zones)),
            )
        )
        assert stock[-1]["residents"] == 100000 and stock[-1]["jobs"] == 40000
    blocked = allocate(
        {("in", "blocked"): 5.0, ("in", "open"): 5.0}, {"in": 10.0}, {"blocked": 0.0, "open": 10.0}
    )
    waves = [dict(k=k, **ovm_modes(1.0, 2.0, k)) for k in (0.001, 2 * math.pi / 100, 0.5, 1.0)]
    receipt = dict(
        scope="literature-grounded numerical audit on isolated source snapshot",
        python=platform.python_version(),
        sampling=dict(
            equal_spatial=speed_measure((5.0, 15.0), (0.5, 0.5), 100.0, measure="space"),
            equal_entrance=speed_measure((5.0, 15.0), (0.5, 0.5), 100.0, measure="entry"),
        ),
        observation=edie_observables(6000.0, 60000.0, 1000.0, 60.0),
        ring=ring_requirements((100000.0,), (20.0,), (10.0,), (10.0,), 5.0, 1000.0),
        wrong_marginal=ring_requirements(
            (1.0, 1.0), (20.0, 20.0), (5.0, 15.0), (5.0, 5.0), 5.0, 50.0
        ),
        nominal_stability=dict(
            assumptions="continuous time, homogeneous ring, no delay, inactive acceleration and safety limits",
            modes=waves,
            relative_damping_candidate=ovm_modes(1.0, 2.0, 2 * math.pi / 100, 1.0),
            candidate_added_to_solver=False,
        ),
        node=dict(
            current_independent_movement_flow={j: v for (i, j), v in blocked.items()},
            declared_shared_lane_full_FIFO_reference={"blocked": 0.0, "open": 0.0},
            status="MODELLING_ASSUMPTION_UNRESOLVED",
            solver_changed=False,
        ),
        overtaking=overtaking(),
        fixed_industry=industrial,
        stock_regression=stock,
        empirical_validation="NOT_RUN",
        whole_repository_CI="NOT_RUN",
    )
    (out / "AUDIT_EXPERIMENTS.json").write_text(
        json.dumps(receipt, indent=2, allow_nan=False) + "\n"
    )
    print(json.dumps(receipt, indent=2, allow_nan=False))
    return receipt


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "artifacts/literature_audit_20261024")
