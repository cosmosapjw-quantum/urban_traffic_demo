"""Render executed map/transport JSON; plotting dependencies are not solver inputs."""

from pathlib import Path
import json
import sys


def main(root):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.patches import Polygon

    root = Path(root)
    out = root / "figures"
    out.mkdir(parents=True, exist_ok=True)
    code = Path(__file__).resolve().parents[1]
    for case in ("polycentric_river", "valley_city"):
        atlas = json.loads(
            (code / f"artifacts/terrain_atlas_20261025/final/{case}.json").read_text()
        )
        result = json.loads((root / f"map_{case}.json").read_text())
        nodes = {n["id"]: n["xyz"] for n in atlas["roadmap"]["nodes"]}
        blocks = {b["id"]: b for b in atlas["blocks"]}
        access = {a["block"]: a for a in result["access"]}
        opened = result["history"][-1]["commissioned"]
        increments = {
            b["id"]: n - b["residents"]
            for b, n in zip(atlas["blocks"], result["history"][-1]["residents"])
        }
        for zoom in (False, True):
            fig, ax = plt.subplots(figsize=(10, 9))
            ax.add_collection(
                LineCollection(
                    [[p[:2] for p in s["points"]] for s in atlas["roadmap"]["sections"]],
                    linewidths=0.55,
                    label="Inherited public streets",
                )
            )
            for k, r in enumerate(atlas["landscape"]["water"]):
                ax.add_patch(
                    Polygon(
                        r["points"],
                        fill=False,
                        hatch="///",
                        linewidth=0.6,
                        label="Water exclusion" if k == 0 else None,
                    )
                )
            for i, key in enumerate(opened):
                b = blocks[key]
                a = access[key]
                ax.add_patch(
                    Polygon(
                        [nodes[v][:2] for v in b["boundary"]],
                        fill=False,
                        hatch=".",
                        linewidth=1.2,
                        label="Blocks with new occupancy" if i == 0 else None,
                    )
                )
                pts = a["points"]
                ax.plot(
                    [p[0] for p in pts],
                    [p[1] for p in pts],
                    lw=3.0,
                    ls="--",
                    label="Commissioned private access" if i == 0 else None,
                )
                ax.scatter([pts[0][0]], [pts[0][1]], marker="x", s=50)
                ax.annotate(
                    f"+{increments[key]} persons\n{a['length_m']:.1f} m access",
                    xy=pts[0][:2],
                    xytext=(14, 16),
                    textcoords="offset points",
                    fontsize=8,
                    arrowprops=dict(arrowstyle="->", lw=0.7),
                )
            if zoom:
                key = opened[0]
                boundary = [nodes[v] for v in blocks[key]["boundary"]]
                xx = [p[0] for p in boundary]
                yy = [p[1] for p in boundary]
                margin = max(60.0, 0.15 * max(max(xx) - min(xx), max(yy) - min(yy)))
                ax.set_xlim(min(xx) - margin, max(xx) + margin)
                ax.set_ylim(min(yy) - margin, max(yy) + margin)
                title = f"{case}: one representative activity point per block\nShort access is not the complete within-block travel distribution"
            else:
                ax.set_xlim(0, 8000)
                ax.set_ylim(0, 8000)
                title = f"{case}: fixed 100,000-resident background, +1,500 residents\nNew private access {result['growth_access_m']:.1f} m; public road geometry unchanged"
            ax.set_aspect("equal")
            ax.set(xlabel="x [m]", ylabel="y [m]", title=title)
            ax.legend(loc="upper right", fontsize=8)
            fig.tight_layout()
            fig.savefig(out / f"{case}_{'zoom' if zoom else 'growth'}.png", dpi=140)
            plt.close(fig)
    report = json.loads((root / "traffic_polycentric_river_dt1.json").read_text())
    trace = report["trace"] + [
        dict(
            time_s=report["end_s"],
            completed=report["completed"],
            active=report["active"],
            pending=report["pending"],
        )
    ]
    fig, ax = plt.subplots(figsize=(9, 5))
    for key, label in (
        ("completed", "Completed"),
        ("active", "In roads"),
        ("pending", "External source waiting"),
    ):
        ax.plot([r["time_s"] for r in trace], [r[key] for r in trace], label=label)
    ax.set(
        xlabel="Time [s]",
        ylabel="Vehicle equivalents",
        title="150 visits from new occupants, not the full 100k city traffic",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "visit_ledger.png", dpi=150)
    plt.close(fig)
    fields = ("road_vehicle_seconds", "source_wait_seconds", "transfer_hold_seconds")
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(
        ["Road residence", "Source waiting", "Numerical transfer"],
        [report[k] / report["completed"] for k in fields],
    )
    ax.set(
        ylabel="Mean contribution [s]",
        title=f"Cleared experiment: mean journey {report['mean_journey_s']:.3f} s",
    )
    fig.tight_layout()
    fig.savefig(out / "journey_decomposition.png", dpi=150)
    plt.close(fig)
    controls = json.loads((root / "CONTROLS.json").read_text())
    fig, ax = plt.subplots(figsize=(8, 5))
    rows = controls["time_refinement"]
    for key, label in (
        ("mean_s", "Full system mean"),
        ("sum_road_residence_s", "Road residence only"),
    ):
        ax.plot([r["dt_s"] for r in rows], [r[key] for r in rows], marker="o", label=label)
    ax.set(
        xlabel="Time step [s]",
        ylabel="Mean time [s]",
        title="Boundary splitting has an explicit time cost\n210 m, 10 m/s; no claim of general convergence",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "split_time_refinement.png", dpi=150)
    plt.close(fig)
    print(json.dumps({"figures": [p.name for p in sorted(out.glob("*.png"))]}, indent=2))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "artifacts/block_flux_20261025")
