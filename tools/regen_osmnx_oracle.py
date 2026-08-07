"""Measure the committed OSM fixtures with OSMnx, as an independent oracle.

The repo asserts its morphology metrics are "OSMnx-equivalent". Nothing checked
that. This script produces the reference the check needs: the seven metrics
computed by OSMnx itself on the same `.osm` files, pinned to an exact OSMnx
version.

It exists so the instrument can be validated against something that is not the
instrument. Generating it AFTER implementing a measurement specification would
be circular -- the golden would record whatever we happened to implement and
prove nothing -- so this lands first, and the specification is written to match
it.

OSMnx's conventions, read from `osmnx.bearing._extract_edge_bearings` rather
than assumed:

- one bearing per *simplified undirected edge*, taken from its endpoint chord
- self-loops excluded, because their bearing is undefined
- reciprocal bearings added, so the distribution is bidirectional
- unweighted when `weight=None`; this is Boeing's H_o, not H_w

Fully offline: `graph_from_xml` parses local bytes and has no HTTP client in its
call chain, so this respects the same no-network rule as `osm_import`
(spec 039 FR-001). Data is (c) OpenStreetMap contributors under ODbL; the
derived values here inherit that licence and the attribution recorded in
`artifacts/osm_control/README.md`.

Usage::

    .venv/bin/python -m pip install -e ".[dev,oracle]"
    .venv/bin/python tools/regen_osmnx_oracle.py            # write the golden
    .venv/bin/python tools/regen_osmnx_oracle.py --check    # verify it reproduces
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import warnings
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_OSM_DIR = _REPO_ROOT / "artifacts" / "osm_control"
_GOLDEN = _REPO_ROOT / "tests" / "data" / "osmnx_morphology_oracle.json"

ORIENTATION_BIN_COUNT = 36

# Boeing's phi. OSMnx has no orientation_order function, so the closed form is
# applied to OSMnx's entropy rather than to ours. It is a pure function of
# entropy, which is why it is derived here instead of measured: the published
# Boeing table is itself self-consistent under this formula to 7e-4.
_GRID_ENTROPY = math.log(4.0)
_MAX_ENTROPY = math.log(float(ORIENTATION_BIN_COUNT))


def _orientation_order(entropy: float) -> float:
    value = 1.0 - ((entropy - _GRID_ENTROPY) / (_MAX_ENTROPY - _GRID_ENTROPY)) ** 2
    return min(max(value, 0.0), 1.0)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def measure(path: Path) -> dict[str, Any]:
    """Measure one extract exactly as OSMnx would, with every option recorded."""

    import networkx as nx
    import osmnx as ox

    # retain_all=True keeps every weakly connected component, matching
    # `metroflow.map.osm_import`, which does not drop any. Dropping them here
    # would compare two different graphs and call the difference a metric
    # disagreement.
    graph = ox.graph_from_xml(str(path), simplify=True, retain_all=True)
    nx.set_node_attributes(graph, ox.stats.count_streets_per_node(graph), name="street_count")

    stats = ox.stats.basic_stats(graph)
    proportions = stats["streets_per_node_proportions"]

    undirected = ox.convert.to_undirected(graph)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        bearings = ox.bearing.add_edge_bearings(undirected)
        entropy = float(
            ox.bearing.orientation_entropy(bearings, num_bins=ORIENTATION_BIN_COUNT)
        )

    lengths = [float(data["length"]) for _u, _v, data in undirected.edges(data=True)]

    components = list(nx.connected_components(undirected))
    largest = max((len(item) for item in components), default=0)

    return {
        "metrics": {
            "orientation_entropy": entropy,
            "orientation_order": _orientation_order(entropy),
            "median_segment_length_m": float(statistics.median(lengths)),
            "circuity": float(stats["circuity_avg"]),
            "mean_node_degree": float(stats["streets_per_node_avg"]),
            "dead_end_share": float(proportions.get(1, 0.0)),
            "four_way_share": float(proportions.get(4, 0.0)),
        },
        # Recorded so a future disagreement can be localized to the graph rather
        # than argued about as a metric difference.
        "graph": {
            "node_count": int(stats["n"]),
            "directed_edge_count": int(stats["m"]),
            "undirected_edge_count": undirected.number_of_edges(),
            "street_segment_count": int(stats["street_segment_count"]),
            "self_loop_proportion": float(stats["self_loop_proportion"]),
            "weak_component_count": len(components),
            "largest_component_node_share": (largest / len(undirected)) if len(undirected) else 0.0,
        },
        "source_sha256": _sha256(path),
    }


def collect() -> dict[str, Any]:
    import networkx as nx
    import osmnx as ox

    cities: dict[str, Any] = {}
    failed: dict[str, str] = {}
    for path in sorted(_OSM_DIR.glob("*.osm")):
        try:
            cities[path.name] = measure(path)
        except Exception as exc:  # noqa: BLE001 - recorded, never silenced
            failed[path.name] = f"{type(exc).__name__}: {exc}"

    return {
        "schema_version": "osmnx_morphology_oracle_v1",
        "oracle": {
            "osmnx_version": ox.__version__,
            "networkx_version": nx.__version__,
            "options": {
                "simplify": True,
                "retain_all": True,
                "undirected": True,
                "num_bins": ORIENTATION_BIN_COUNT,
                "min_length": 0,
                "weight": None,
                "statistic": "BOEING_2019_HO",
            },
            "conventions": (
                "One bearing per simplified undirected edge, taken from its "
                "endpoint chord; self-loops excluded; reciprocal bearings added; "
                "unweighted. orientation_order is Boeing's closed form applied to "
                "this entropy, since OSMnx provides no such function."
            ),
        },
        "attribution": (
            "Derived from OpenStreetMap data, (c) OpenStreetMap contributors, "
            "ODbL. See artifacts/osm_control/README.md."
        ),
        "evidence_status": "instrument_oracle_not_traffic_validation",
        "cities": cities,
        "failed": failed,
    }


def _write(payload: dict[str, Any]) -> None:
    _GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    _GOLDEN.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _check(payload: dict[str, Any]) -> int:
    if not _GOLDEN.exists():
        print(f"no golden at {_GOLDEN.relative_to(_REPO_ROOT)}; run without --check first")
        return 1
    stored = json.loads(_GOLDEN.read_text(encoding="utf-8"))

    problems: list[str] = []
    if stored["oracle"] != payload["oracle"]:
        problems.append(
            f"oracle provenance changed: stored {stored['oracle']} != current {payload['oracle']}"
        )
    if set(stored["cities"]) != set(payload["cities"]):
        problems.append(
            f"city set changed: stored {sorted(stored['cities'])} "
            f"!= current {sorted(payload['cities'])}"
        )
    for name in sorted(set(stored["cities"]) & set(payload["cities"])):
        left = stored["cities"][name]
        right = payload["cities"][name]
        if left["source_sha256"] != right["source_sha256"]:
            problems.append(f"{name}: fixture bytes changed")
        for metric, value in left["metrics"].items():
            current = right["metrics"][metric]
            if not math.isclose(value, current, rel_tol=0.0, abs_tol=1e-9):
                problems.append(f"{name}.{metric}: stored {value!r} != current {current!r}")

    for problem in problems:
        print(f"MISMATCH {problem}")
    if problems:
        print(f"{len(problems)} mismatch(es); the oracle does not reproduce")
        return 1
    print(f"oracle reproduces: {len(payload['cities'])} cities, all metrics within 1e-9")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="recompute and compare against the committed golden instead of writing it",
    )
    args = parser.parse_args()

    try:
        payload = collect()
    except ImportError as exc:
        print(f"oracle extra not installed ({exc}); pip install -e '.[dev,oracle]'")
        return 1

    if args.check:
        return _check(payload)

    _write(payload)
    print(f"wrote {_GOLDEN.relative_to(_REPO_ROOT)}")
    print(f"  osmnx    {payload['oracle']['osmnx_version']}")
    print(f"  measured {len(payload['cities'])} cities")
    for name, reason in payload["failed"].items():
        print(f"  FAILED   {name}: {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
