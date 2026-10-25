"""Render the actual frozen atlas; visual evidence does not substitute for gates."""

from pathlib import Path
import argparse
import json


def draw(path, zoom=False):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    from matplotlib.collections import PolyCollection
    import numpy as np

    path = Path(path)
    data = json.loads(path.read_text())
    roadmap = data["roadmap"]
    land = data["landscape"]
    L = land["terrain"]["n"] * land["terrain"]["spacing_m"]
    nodes = {n["id"]: n["xyz"] for n in roadmap["nodes"]}
    fig, ax = plt.subplots(figsize=(12, 11))
    terrain = land["terrain"]
    n = terrain["n"]
    x = np.linspace(0, L, n + 1)
    z = np.asarray(terrain["heights_m"]).reshape(n + 1, n + 1)
    cs = ax.contour(x, x, z, levels=9, linewidths=0.35, alpha=0.28)
    ax.clabel(cs, fontsize=6, fmt="%d m")
    polys = []
    codes = []
    uses = ("residential", "mixed", "commercial", "industrial", "buffer", "open_space")
    for b in data["blocks"]:
        if len(b["boundary"]) != len(set(b["boundary"])):
            continue
        polys.append([nodes[k][:2] for k in b["boundary"]])
        codes.append(uses.index(b["use"]))
    if polys:
        pc = PolyCollection(polys, array=np.asarray(codes), alpha=0.16, linewidths=0)
        pc.set_clim(0, 5)
        ax.add_collection(pc)
        bar = fig.colorbar(pc, ax=ax, fraction=0.022, pad=0.02, ticks=range(6))
        bar.ax.set_yticklabels(uses, fontsize=7)
        bar.set_label("Block use (not population density)", fontsize=8)
    for regions, hatch, label in (
        (land["water"], "///", "Water"),
        (land["protected"], "xx", "Protected land"),
    ):
        for k, r in enumerate(regions):
            ax.add_patch(
                Polygon(
                    r["points"], fill=False, hatch=hatch, lw=0.7, label=label if k == 0 else None
                )
            )
    for h, width in (("local", 0.42), ("collector", 0.85), ("arterial", 1.9)):
        xx = []
        yy = []
        for s in roadmap["sections"]:
            if s["hierarchy"] != h or s["facility"] == "bridge":
                continue
            xx.extend(p[0] for p in s["points"])
            xx.append(float("nan"))
            yy.extend(p[1] for p in s["points"])
            yy.append(float("nan"))
        ax.plot(xx, yy, lw=width, label=h)
    xx = []
    yy = []
    for s in roadmap["sections"]:
        if s["facility"] == "bridge":
            xx.extend(p[0] for p in s["points"])
            xx.append(float("nan"))
            yy.extend(p[1] for p in s["points"])
            yy.append(float("nan"))
    if xx:
        ax.plot(xx, yy, lw=2.4, ls="--", label="Bridge")
    ax.scatter(
        [nodes[k][0] for k in data["centers"]],
        [nodes[k][1] for k in data["centers"]],
        marker="*",
        s=100,
        label="Declared centers",
        zorder=9,
    )
    if zoom:
        center = nodes[data["centers"][0]]
        radius = 0.13 * L
        ax.set_xlim(center[0] - radius, center[0] + radius)
        ax.set_ylim(center[1] - radius, center[1] + radius)
    else:
        ax.set_xlim(0, L)
        ax.set_ylim(0, L)
    summary = data["summary"]
    ax.set_aspect("equal")
    ax.set(
        xlabel="Local x [m]",
        ylabel="Local y [m]",
        title=f"{path.stem}: {L / 1000:g} × {L / 1000:g} km synthetic landscape\n{summary['nodes']:,} junctions / {summary['physical_links']:,} road segments; {summary['resident_stock']:,} residents placed",
    )
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    destination = path.parent / "figures"
    destination.mkdir(exist_ok=True)
    stem = path.stem + ("_detail" if zoom else "")
    fig.savefig(destination / (stem + ".png"), dpi=160)
    fig.savefig(destination / (stem + ".svg"))
    plt.close(fig)
    return str(destination / (stem + ".png"))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("path")
    p.add_argument("--zoom", action="store_true")
    a = p.parse_args()
    print(draw(a.path, a.zoom))
