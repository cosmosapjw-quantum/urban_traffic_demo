"""Capture the pre-V2 morphology numbers, before the instrument is touched.

`compute_street_network_morphometrics` currently defaults to
``simplify_interstitial_nodes=False``. PR-A removes that default in favour of a
required measurement specification, and one of the new specs
(``RUNTIME_COMPILED_DIAGNOSTIC``) must reproduce today's default *exactly* —
otherwise removing the default silently changes every runtime metadata payload
that embeds these metrics.

The fixture this writes is the evidence for that claim. It has to be captured
from a tree where the default still exists, so this is an ordered step that runs
once, before the signature changes. Running it afterwards would capture the new
behaviour and lock in whatever we happened to implement, which proves nothing.

Usage::

    .venv/bin/python tools/capture_pre_v2_morphology_baseline.py

Writes ``tests/data/morphology_pre_v2_baseline.json``.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from metroflow.benchmarks.morphology_control_table import (
    CONTROL_TABLE_SCENARIO_ID,
    build_arm_topology,
    build_osm_topology,
)
from metroflow.city.morphology_metrics import compute_street_network_morphometrics
from metroflow.city.morphology_reference import MORPHOLOGY_ARCHETYPES

# One seed is enough: the fixture pins a *measurement definition*, not a
# generator. Six styles across five arms exercise every shape of compiled
# geometry the default path sees (lattice, sidecar, planarized, realistic,
# grown) plus the real-data control.
BASELINE_SEED = 29
BASELINE_STYLES = tuple(MORPHOLOGY_ARCHETYPES)
LEGACY_ARMS = ("standard", "sidecar_local_fabric", "sidecar_local_fabric_planar")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_OUTPUT = _REPO_ROOT / "tests" / "data" / "morphology_pre_v2_baseline.json"
_OSM_DIR = _REPO_ROOT / "artifacts" / "osm_control"


def _head_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _measure(topology: Any) -> dict[str, Any]:
    """Measure on the CURRENT default path, with no keyword argument.

    Passing no kwarg is the whole point: this records what every existing
    caller of the bare signature gets today.
    """

    return dict(compute_street_network_morphometrics(topology).as_dict())


def collect_baseline() -> dict[str, Any]:
    """Measure every arm that can produce a topology; record what could not."""

    records: list[dict[str, Any]] = []
    skipped: list[str] = []

    def record(arm: str, case: str, build) -> None:
        try:
            topology = build()
        except Exception as exc:  # noqa: BLE001 - recorded, never silenced
            skipped.append(f"{arm}:{case}:{type(exc).__name__}:{exc}")
            return
        try:
            metrics = _measure(topology)
        except Exception as exc:  # noqa: BLE001 - recorded, never silenced
            skipped.append(f"{arm}:{case}:measure:{type(exc).__name__}:{exc}")
            return
        records.append({"arm": arm, "case": case, "metrics": metrics})

    for arm in (*LEGACY_ARMS, "realistic_synthetic_v1", "growth_fabric_v1"):
        for style_id in BASELINE_STYLES:
            record(
                arm,
                f"{style_id}/{BASELINE_SEED}",
                lambda arm=arm, style_id=style_id: build_arm_topology(
                    arm=arm, style_id=style_id, seed=BASELINE_SEED
                ),
            )

    for path in sorted(_OSM_DIR.glob("*.osm")):
        record("osm", path.name, lambda path=path: build_osm_topology(path))

    return {
        "schema_version": "morphology_pre_v2_baseline_v1",
        "captured_at_commit": _head_commit(),
        "measurement": (
            "compute_street_network_morphometrics(topology) with no keyword "
            "argument, i.e. the pre-V2 default simplify_interstitial_nodes=False"
        ),
        "seed": BASELINE_SEED,
        "scenario_id": CONTROL_TABLE_SCENARIO_ID,
        "styles": list(BASELINE_STYLES),
        "evidence_status": "baseline_capture_not_validation",
        "records": records,
        "skipped": skipped,
    }


def main() -> None:
    baseline = collect_baseline()
    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    # allow_nan=False: a non-finite here would be unreadable by any strict
    # parser and would silently poison the comparison it exists to support.
    _OUTPUT.write_text(
        json.dumps(baseline, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {_OUTPUT.relative_to(_REPO_ROOT)}")
    print(f"  commit  {baseline['captured_at_commit']}")
    print(f"  records {len(baseline['records'])}")
    print(f"  skipped {len(baseline['skipped'])}")
    for entry in baseline["skipped"]:
        print(f"    - {entry}")


if __name__ == "__main__":
    main()
