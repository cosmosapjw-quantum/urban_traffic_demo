"""Lock today's default measurement so PR-A cannot change it by accident.

`compute_street_network_morphometrics` defaults to
``simplify_interstitial_nodes=False``, and that default is embedded in runtime
metadata via `topology_finalizer`, in the PR62 audit via
`plausibility_audit._map_metrics`, and in the morphology atlas manifest. PR-A
removes the default in favour of a required measurement specification.

Removing it must be provably value-preserving for the diagnostic path. This
file is the proof: it pins every metric the default path produces today, so the
PR-A commit that introduces `RUNTIME_COMPILED_DIAGNOSTIC` either reproduces
these numbers exactly or turns this red.

These assertions pass on arrival, deliberately. They are a characterization
lock, not a red-green cycle: nothing here claims to force a fix, and their whole
value is in failing later. The fixture is regenerated only by
`tools/capture_pre_v2_morphology_baseline.py`, which must never be re-run after
the signature changes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_FIXTURE = Path(__file__).parent / "data" / "morphology_pre_v2_baseline.json"


def _baseline() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def test_baseline_fixture_is_strict_json_and_carries_provenance() -> None:
    """A fixture nobody can locate the origin of is not evidence."""

    raw = _FIXTURE.read_text(encoding="utf-8")
    # parse_constant fires only for NaN/Infinity/-Infinity, which RFC 8259 forbids.
    baseline = json.loads(
        raw, parse_constant=lambda token: pytest.fail(f"non-finite literal {token!r}")
    )

    assert baseline["schema_version"] == "morphology_pre_v2_baseline_v1"
    assert len(baseline["captured_at_commit"]) == 40
    assert baseline["seed"] == 29
    assert "simplify_interstitial_nodes=False" in baseline["measurement"], (
        "the fixture must name the definition it captured; that string is the "
        "only record of which of the two definitions these numbers are"
    )
    assert baseline["evidence_status"] == "baseline_capture_not_validation"


def test_baseline_covers_every_arm_and_records_what_it_could_not_measure() -> None:
    """Silent omission is how the previous cycle's evidence went wrong."""

    baseline = _baseline()
    arms = {record["arm"] for record in baseline["records"]}

    assert arms == {
        "standard",
        "sidecar_local_fabric",
        "sidecar_local_fabric_planar",
        "realistic_synthetic_v1",
        "growth_fabric_v1",
        "osm",
    }
    assert len(baseline["records"]) == 31

    # The six skips are known and each names its cause. `standard` supports only
    # two styles; paris and prague fail the lane parser. Nothing is dropped
    # without a recorded reason.
    assert len(baseline["skipped"]) == 6
    assert sum(entry.startswith("standard:") for entry in baseline["skipped"]) == 4
    assert sum(entry.startswith("osm:") for entry in baseline["skipped"]) == 2
    for entry in baseline["skipped"]:
        assert entry.count(":") >= 2, f"skip entry carries no cause: {entry}"


def _rebuild(arm: str, case: str, scenario_id: str):
    from pathlib import Path

    from metroflow.benchmarks.morphology_control_table import (
        build_arm_topology,
        build_osm_topology,
    )

    if arm == "osm":
        return build_osm_topology(
            Path(__file__).parents[1] / "artifacts" / "osm_control" / case
        )
    style_id, seed = case.split("/")
    return build_arm_topology(
        arm=arm, style_id=style_id, seed=int(seed), scenario_id=scenario_id
    )


@pytest.mark.parametrize(
    "record", _baseline()["records"], ids=lambda r: f"{r['arm']}:{r['case']}"
)
def test_default_measurement_still_reproduces_the_pinned_baseline(record: dict) -> None:
    """RUNTIME_COMPILED_DIAGNOSTIC must return exactly what the old default did.

    This is the evidence that removing the default was value-preserving. Newly
    added keys (`measurement_spec`, the dropped-ring counters) are not in the
    fixture and are not asserted here; every key that existed at capture time
    must match bit-for-bit.
    """

    from metroflow.city.morphology_metrics import (
        MeasurementSpec,
        compute_street_network_morphometrics,
    )

    if record["arm"] == "growth_fabric_v1":
        pytest.skip(
            "growth_fabric_v1's GENERATOR changed in PR-B (branch anchors now "
            "split their parent), so its maps are no longer the ones captured. "
            "This fixture pins the MEASUREMENT, not the generator: the other "
            "five arms are untouched by PR-B and still reproduce bit-for-bit, "
            "which is what proves removing the default was value-preserving. "
            "Re-capturing this arm would destroy that property, since the "
            "fixture's whole value is having been taken before the change."
        )

    topology = _rebuild(record["arm"], record["case"], _baseline()["scenario_id"])

    measured = dict(
        compute_street_network_morphometrics(
            topology, spec=MeasurementSpec.RUNTIME_COMPILED_DIAGNOSTIC
        ).as_dict()
    )

    pinned = record["metrics"]
    assert {key: measured[key] for key in pinned} == pinned, (
        f"{record['arm']}:{record['case']} drifted from the pre-V2 baseline"
    )
