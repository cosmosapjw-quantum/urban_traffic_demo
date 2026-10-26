"""Test that new physical access roads contribute delay, not zero-cost teleport."""

from pathlib import Path
import sys
import json
import math

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from metroflow.restored_city import generate
from metroflow.restored_zoning import attach_zones
from metroflow.restored_traffic import compile_traffic
from metroflow.frontage_growth import Site, grow_access
from metroflow.active_suffix import Demand, Config
from metroflow.active_suffix.packed import PackedModel
from run_interval_research import run


def main():
    out = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path("artifacts/frontage_interval_20261024/coupling.json")
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for style in ("grid_core", "organic"):
        old = generate(style)
        zones, _ = attach_zones(old)
        selected = sorted(
            (z for z in zones.zones if z.residents > 0),
            key=lambda z: (-(z.residents + z.jobs), z.id),
        )[:8]
        growth = grow_access(
            old,
            tuple(Site(z.id, (z.x_m, z.y_m), z.residents + z.jobs) for z in selected),
            budget_m=900.0,
            max_roads=4,
            max_length_m=350.0,
        )
        a, b = growth.admitted[:2]
        network = compile_traffic(growth.city, signals=False)
        cfg = Config(dt_s=2.0, paths_per_od=1, interaction_rate_s=0.0)
        model = PackedModel(
            network.roads,
            (Demand(a[1], b[1], 0.0, 8.0, 0.01),),
            cfg,
            allowed_turns=network.allowed_turns,
        )
        initial = model.initial()
        path = model.remaining_path(initial, initial.source_roots[0][0])
        rd = {r.id: r for r in model.roads}
        exact = sum(rd[k].length_m / rd[k].free_speed_mps for k in path)
        quantized = sum(
            math.ceil(rd[k].length_m / rd[k].free_speed_mps / cfg.dt_s - 1e-12) * cfg.dt_s
            for k in path
        )
        report, _ = run(model, quantized + 50.0, wall_limit_s=15.0)
        assert report["status"] == "CLEARED_SCOPED"
        assert path[0].startswith("access:") and path[-1].startswith("access:")
        assert abs(report["mean_s"] - quantized) < 1e-8
        assert 0 <= quantized - exact < len(path) * cfg.dt_s
        rows.append(
            dict(
                style=style,
                origin=a[1],
                destination=b[1],
                path=path,
                exact_frozen_freeflow_s=exact,
                quantized_freeflow_s=quantized,
                mean_s=report["mean_s"],
                physical_access_delays_s=[
                    rd[path[0]].length_m / rd[path[0]].free_speed_mps,
                    rd[path[-1]].length_m / rd[path[-1]].free_speed_mps,
                ],
                completed=report["completed"],
                peak_records=report["peak_records"],
                max_mass_error=report["max_mass_error"],
            )
        )
    out.write_text(json.dumps(rows, indent=2, allow_nan=False))
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
