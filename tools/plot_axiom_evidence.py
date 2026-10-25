"""Diagnostic plots from executed evidence; matplotlib is outside the solver."""

from pathlib import Path
import json
import math
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main(root):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from metroflow.environment.terrain import Terrain
    from metroflow.restored_city import Junction, Section, RoadMap
    from metroflow.restored_geometry import ground_profile, elevation
    from metroflow.frontage_growth import _projection
    from metroflow.sight_frontage import SightRule

    root = Path(root)
    out = root / "figures"
    out.mkdir(parents=True, exist_ok=True)
    local = json.loads((root / "traffic/LOCAL_KINETIC.json").read_text())
    fig, ax = plt.subplots(figsize=(9, 5))
    for key, label, ls in [
        ("equal_gaps", "Car: all gaps 20 m", "-"),
        ("dispersed_gaps", "Car: equal mass at gaps 5 / 35 m", "--"),
        ("freight", "Freight: equal mass at gaps 5 / 35 m", ":"),
    ]:
        ax.plot(
            [r["time_s"] for r in local["series"]],
            [r[key][1] for r in local["series"]],
            ls,
            label=label,
        )
    ax.set(
        xlabel="Time [s]",
        ylabel="Mean continuous speed [m/s]",
        title="Conditional gap statistics change acceleration\nFrozen-gap reference, not self-consistent platoon dynamics",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "conditional_speed.png", dpi=150)
    plt.close(fig)
    pair = json.loads((root / "traffic/PAIRED_INFORMATION.json").read_text())
    fig, ax = plt.subplots(figsize=(9, 5))
    for name, label, ls in [
        ("global", "Global current state", "-"),
        ("within", "Finite-delivery reports", "--"),
        ("outside", "Outside radius: static prior", ":"),
    ]:
        ax.step(
            [r["decision_time_s"] for r in pair["series"]],
            [r["short_route_share"][str((name, True))] for r in pair["series"]],
            where="post",
            ls=ls,
            label=label,
        )
    ax.axvline(2.0, ls=":", lw=0.8)
    ax.axvline(10.0, ls="--", lw=0.8)
    ax.set(
        xlabel="Decision time [s]",
        ylabel="Short-route preference probability",
        ylim=(-0.05, 1.05),
        title="Remote closure at 2 s; first causal decision change at 10 s\nZero-demand paired-world control isolates information",
    )
    ax.legend(loc="center right")
    fig.tight_layout()
    fig.savefig(out / "causal_information.png", dpi=150)
    plt.close(fig)
    t = Terrain(4, 100.0, tuple(z for _ in range(5) for z in (0.0, 0.0, 8.0, 0.0, 0.0)))
    pts, length, grade = ground_profile(t, ((0.0, 200.0), (400.0, 200.0)))
    road = Section("street", "a", "b", pts, "collector", "surface", 1, 1, length, grade)
    city = RoadMap("crest", t, (Junction("a", pts[0]), Junction("b", pts[-1])), (road,))
    p = _projection((230.0, 240.0), road.points)
    check = next(c for c in SightRule().assess(city, road, p) if c.reason == "sight_obstructed")
    xx = [check.eye[0] + (check.target[0] - check.eye[0]) * k / 200 for k in range(201)]
    hh = [elevation(t, x, 200.0) for x in xx]
    line = [check.eye[2] + (check.target[2] - check.eye[2]) * k / 200 for k in range(201)]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(xx, hh, label="Declared terrain profile")
    ax.plot(xx, line, "--", label="Driver-eye to obstacle line")
    ax.scatter([check.eye[0], check.target[0]], [check.eye[2], check.target[2]], marker="o")
    ax.set(
        xlabel="Position along approach [m]",
        ylabel="Height [m]",
        title=f"New frontage rejected at a hidden crest\nExact terrain clearance: {check.clearance_m:.3f} m",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "sight_rejection.png", dpi=150)
    plt.close(fig)
    (root / "SIGHT_COUNTEREXAMPLE.json").write_text(
        json.dumps(
            dict(
                required_m=check.required_m,
                clearance_m=check.clearance_m,
                eye=check.eye,
                target=check.target,
                reason=check.reason,
                terrain_height_m=hh,
                position_m=xx,
            ),
            indent=2,
        )
    )
    tt = [k / 20 for k in range(201)]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(
        tt, [8 + 12 * math.exp(-t / 2) for t in tt], "--", label="Instant-response shortcut U p(t)"
    )
    ax.plot(
        tt,
        [8 + 36 * math.exp(-t / 3) - 24 * math.exp(-t / 2) for t in tt],
        label="Exact finite-response mean m(t)",
    )
    ax.set(
        xlabel="Time [s]",
        ylabel="Mean speed [m/s]",
        title="Same equilibrium mean does not imply the same transient\nFixed rates: alpha=0.2/s, nu=0.3/s, response time=3 s",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "finite_response.png", dpi=150)
    plt.close(fig)
    print(json.dumps(dict(figures=[p.name for p in sorted(out.glob("*.png"))]), indent=2))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "artifacts/axiom_gap_20261024")
