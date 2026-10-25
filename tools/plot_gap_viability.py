"""Render actual run JSON and the specified terrain counterexample; no solver dependency."""

from pathlib import Path
import sys
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main(root):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from metroflow.stopping_envelope import hold_brake, motion
    from metroflow.restored_city import RoadMap, Junction, Section
    from metroflow.environment.terrain import Terrain, Rect

    def roadmap(data):
        t = data["terrain"]
        terrain = Terrain(
            t["n"],
            t["spacing_m"],
            tuple(t["heights_m"]),
            tuple(Rect(**r) for r in t["water"]),
            tuple(Rect(**r) for r in t["protected"]),
            tuple(t["bridge_rows"]),
        )
        nodes = tuple(Junction(n["id"], tuple(n["xyz"]), n["layer"]) for n in data["nodes"])
        sections = tuple(
            Section(**(r | {"points": tuple(tuple(p) for p in r["points"])}))
            for r in data["sections"]
        )
        return RoadMap(
            data["style"], terrain, nodes, sections, tuple(tuple(x) for x in data["rejected"])
        )

    from render_restored_city import draw

    root = Path(root)
    out = root / "figures"
    out.mkdir(parents=True, exist_ok=True)
    result = json.loads((root / "traffic/TRAFFIC_RESULTS.json").read_text())
    fig, ax = plt.subplots(figsize=(9, 5))
    for key, label, ls in [
        ("0.0", "Filtered: current leader report", "-"),
        ("2.0", "Filtered: 2 s old report", "--"),
    ]:
        rows = result["scenarios"][key]["trace"]
        ax.plot([r["time_s"] for r in rows], [r["gap_m"] for r in rows], ls, label=label)
    rows = result["unfiltered"]["trace"]
    ax.plot(
        [r["time_s"] for r in rows],
        [r["gap_m"] for r in rows],
        ":",
        label="Same nominal law, no safety filter; ends at overlap",
    )
    ax.axhline(2.0, ls="--", lw=0.8, label="Declared 2 m minimum")
    ax.set(
        xlabel="Time [s]",
        ylabel="Conditional gap [m]",
        title="Evolving gap under leader braking and restart\nFresh gap sensing; finite bounds; one weighted phase node",
    )
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "gap_braking.png", dpi=150)
    plt.close(fig)
    tt = [i / 100 for i in range(751)]
    closure = [hold_brake(20.0, -8.0, 0.5, 8.0, t)[0] - motion(15.0, -2.0, t)[0] for t in tt]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(tt, closure, label="Follower travel minus leader travel")
    ax.axhline(0.0, ls=":", lw=0.8)
    ax.scatter([5 / 6], [25 / 12])
    ax.annotate(
        "Maximum closure 2.0833 m at 0.8333 s",
        xy=(5 / 6, 25 / 12),
        xytext=(2.0, -8.0),
        arrowprops=dict(arrowstyle="->"),
    )
    ax.set(
        xlabel="Time [s]",
        ylabel="Closing displacement [m]",
        title="Final stopping positions miss a transient approach",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "transient_closure.png", dpi=150)
    plt.close(fig)
    sight = json.loads((root / "SIGHT_PROFILE.json").read_text())
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(sight["x"], sight["height"], label="Terrain along the road")
    for key, label, ls in [
        ("far", "Furthest observer: clear", "--"),
        ("blocked", "Closer observer: occluded", ":"),
    ]:
        eye = sight[key]["eye"]
        target = sight[key]["target"]
        ax.plot([eye[0], target[0]], [eye[2], target[2]], ls, label=label)
    ax.set(
        xlim=(245.0, 305.0),
        xlabel="Road position [m]",
        ylabel="Height [m]",
        title="A clear distant view does not ensure visibility throughout approach\nObserver positions are sampled; each terrain ray is checked continuously",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "approach_occlusion.png", dpi=150)
    plt.close(fig)
    data = json.loads((root / "map/organic_accelerating_scan.json").read_text())
    draw(
        roadmap(data["city"]),
        out / "generated_organic.png",
        "Existing curved-grid form with reaction/sight-screened access roads\nSame accepted geometry as the parent on this fixed input",
    )
    return sorted(str(p) for p in out.glob("*.png"))


if __name__ == "__main__":
    print(
        json.dumps(
            main(sys.argv[1] if len(sys.argv) > 1 else "artifacts/gap_viability_20261024"), indent=2
        )
    )
