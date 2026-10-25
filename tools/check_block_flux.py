"""Analytic and structural controls, not an external-model benchmark."""

from pathlib import Path
from dataclasses import replace
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from metroflow.ordered_lane import Lane
from metroflow.ordered_network import Group, Route, Network
from metroflow.active_suffix.routing import braess_reference


def main(out):
    rows = []
    for dt in (1.0, 0.5, 0.25, 0.125):
        groups = (
            Group("a", "O", "M", Lane(103.0, 10.0, 10.0, 10.0, 30.0, interaction_rate=0.0)),
            Group("b", "M", "D", Lane(107.0, 10.0, 10.0, 10.0, 30.0, interaction_rate=0.0)),
        )
        model = Network(groups, (Route("r", ("a", "b")),), dt_s=dt)
        state = model.initial()
        for i in range(round(50 / dt)):
            state, _ = model.step(state, (("r", 0.1),) if i == 0 else ())
        rows.append(
            dict(
                dt_s=dt,
                completed=state.completed,
                mean_s=state.system_vehicle_seconds / state.completed,
                source_wait_s=state.source_wait_seconds / state.completed,
                handoff_wait_s=state.transfer_hold_seconds / state.completed,
                sum_road_residence_s=sum(s.network_vehicle_seconds for s in state.lanes)
                / state.completed,
                road_distance_m=sum(s.vehicle_metres for s in state.lanes) / state.completed,
            )
        )
        assert abs(state.completed - 0.1) < 1e-12
        assert abs(rows[-1]["road_distance_m"] - 210.0) < 1e-8
    # Scale all lane supplies/storage and source mass, preserving N/K dynamics.
    scale_error = 0.0
    base = Lane(50.0, 10.0, 1.0, 1.0, 20.0)
    groups = (Group("a", "O", "M", base), Group("b", "M", "D", base))
    large = tuple(
        replace(g, physics=replace(g.physics, entry_rate=1000.0, exit_rate=1000.0, storage=20000.0))
        for g in groups
    )
    ma, mb = Network(groups, (Route("r", ("a", "b")),)), Network(large, (Route("r", ("a", "b")),))
    a, b = ma.initial(), mb.initial()
    counts = []
    for i in range(100):
        a, _ = ma.step(a, (("r", 10.0),) if i == 0 else ())
        b, _ = mb.step(b, (("r", 10000.0),) if i == 0 else ())
        scale_error = max(
            scale_error,
            abs(a.completed - b.completed / 1000),
            *(abs(x.occupancy - y.occupancy / 1000) for x, y in zip(a.lanes, b.lanes)),
        )
        counts.append((sum(len(x.inside) for x in a.lanes), sum(len(x.inside) for x in b.lanes)))
    before = braess_reference()
    after = braess_reference(shortcut=True)
    result = dict(
        time_refinement=rows,
        scaled_observable_max_error=scale_error,
        max_records_base=max(x for x, y in counts),
        max_records_scaled=max(y for x, y in counts),
        braess_static_minutes=[before["mean_cost_min"], after["mean_cost_min"]],
        scope="same homogeneous laws at scaled supply/storage/mass, not heterogeneous people",
    )
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "artifacts/block_flux_20261025/CONTROLS.json")
