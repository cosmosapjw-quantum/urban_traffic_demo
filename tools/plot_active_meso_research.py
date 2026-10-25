#!/usr/bin/env python3
"""Optional matplotlib evidence renderer; never imported by scientific core."""

import argparse
import json
from pathlib import Path
import matplotlib.pyplot as plt


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--show", action="store_true")
    a = p.parse_args(argv)
    data = json.loads(a.input.read_text())
    a.output_dir.mkdir(parents=True, exist_ok=True)

    def save(fig, name, show=False):
        fig.tight_layout()
        fig.savefig(a.output_dir / name, dpi=160)
        if a.show and show:
            plt.show()
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5))
    for result in data["routing_response"]:
        h = result["history"]
        ax.plot([x["time_s"] for x in h], [x["shares"][0] for x in h], label=result["policy"])
    ax.set(
        xlabel="Time [s]",
        ylabel="Upper-route share of new normal-class departures",
        title="Feedback response: immediate best response vs relaxed cohort choice",
        ylim=(-0.03, 1.03),
    )
    ax.axvline(600.0, linestyle=":", label="Demand ends")
    ax.legend()
    save(fig, "route_response.png", True)
    result = next(x for x in data["diamond"] if x["dt"] == 1.0)
    h = result["history"]
    t = [x["time_s"] for x in h]
    fig, ax = plt.subplots(figsize=(10, 5))
    for field, label in [
        ("released", "Released"),
        ("completed", "Completed"),
        ("active", "On-network"),
        ("pending", "External backlog"),
    ]:
        ax.plot(t, [x[field] for x in h], label=label)
    ax.axvline(200.0, linestyle=":", label="Upper link closed")
    ax.axvline(400.0, linestyle="--", label="Reopened")
    ax.set(
        xlabel="Time [s]",
        ylabel="Vehicle-equivalent mass",
        title="Aggregate mass ledger, two driver cohorts",
    )
    ax.legend()
    save(fig, "mass_ledger.png")
    fig, ax = plt.subplots(figsize=(10, 5))
    for j, name in enumerate(("s-a", "a-t (incident)", "s-b", "b-t")):
        ax.plot(t, [x["occupancy"][j] / (25.0, 45.0, 35.0, 35.0)[j] for x in h], label=name)
    ax.axvline(200.0, linestyle=":")
    ax.axvline(400.0, linestyle="--")
    ax.set(
        xlabel="Time [s]",
        ylabel="Occupancy / finite storage",
        ylim=(-0.02, 1.02),
        title="Link storage and clearance; not a spatial shock-wave validation",
    )
    ax.legend()
    save(fig, "finite_storage.png")
    fig, ax = plt.subplots(figsize=(8, 5))
    vals = data["workload"]
    ax.plot([x["released_mass"] for x in vals], [x["median_elapsed_s"] for x in vals], marker="o")
    ax.set(
        xscale="log",
        xlabel="Total released mass, including external backlog [vehicles]",
        ylabel="400 steps, median of 3 runs [s]",
        title="Fixed cohort state: 311 scalar values, no per-car loop",
        ylim=(0, None),
    )
    save(fig, "workload_scaling.png")
    fig, ax = plt.subplots(figsize=(8, 5))
    b = data["braess_static"]
    values = [b["before"]["mean_cost_s"], b["after"]["mean_cost_s"]]
    ax.bar(["Without shortcut", "With shortcut"], values)
    for i, value in enumerate(values):
        ax.text(i, value + 2, f"{value:.3f} s", ha="center")
    ax.set(
        ylabel="Wardrop equilibrium mean cost [s]",
        ylim=(0, 225),
        title="Static affine-cost Braess oracle; not a dynamic kinetic result",
    )
    save(fig, "braess_static.png")
    if "map_integration" in data:
        h = data["map_integration"]["history"]
        fig, ax = plt.subplots(figsize=(9, 5))
        for field in ("released", "active", "completed", "pending"):
            ax.plot([x["time_s"] for x in h], [x[field] for x in h], label=field)
        ax.set(
            xlabel="Time [s]",
            ylabel="Vehicle-equivalent mass",
            title="Generated-map adapter: 3 OD cohorts including an infill-road probe",
        )
        ax.legend()
        save(fig, "generated_map_transport.png")


if __name__ == "__main__":
    main()
