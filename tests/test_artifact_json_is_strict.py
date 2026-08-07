"""Every committed artifact must be readable by a spec-conformant JSON parser.

`json.load` accepts bare `NaN` and `Infinity`; RFC 8259 does not, and neither
does `JSON.parse`. An artifact that only Python can read is not an artifact
anyone else can audit — which matters exactly when an external reviewer is
reading the tree.

One file currently violates this and is marked as a known defect rather than
quietly excluded. PR-A fixes the writer and removes the mark.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]

# `envelope_diagnostics` emits math.inf / math.nan verbatim for the metrics with
# an unbounded theoretical range. Serialized at
# benchmarks/morphology_control_table.py, and deliberately outside the
# fingerprint, so the values are not even hash-protected.
_KNOWN_NON_STRICT = "artifacts/runtime_spine_review/morphology-control-table-20260807.json"


def _tracked_json() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "*.json"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(result.stdout.split())


def _params():
    for path in _tracked_json():
        if path == _KNOWN_NON_STRICT:
            yield pytest.param(
                path,
                marks=pytest.mark.xfail(
                    strict=True,
                    reason=(
                        "envelope_diagnostics writes bare NaN/Infinity for "
                        "circuity, mean_node_degree and median_segment_length_m "
                        "(theoretical_coverage and theoretical_max). PR-A "
                        "serializes them as null with an explicit status field."
                    ),
                ),
            )
        else:
            yield path


@pytest.mark.parametrize("relative_path", list(_params()))
def test_tracked_artifact_parses_under_a_strict_json_reader(relative_path: str) -> None:
    raw = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")

    # parse_constant fires only for NaN, Infinity and -Infinity.
    json.loads(
        raw,
        parse_constant=lambda token: pytest.fail(
            f"{relative_path} contains the non-RFC-8259 literal {token!r}"
        ),
    )


def test_the_scan_actually_covers_the_repository() -> None:
    """A discovery bug here would make every assertion above vacuous."""

    tracked = _tracked_json()

    assert len(tracked) >= 40
    assert _KNOWN_NON_STRICT in tracked
