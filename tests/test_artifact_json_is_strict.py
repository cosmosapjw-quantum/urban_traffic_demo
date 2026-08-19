"""Every committed artifact must be readable by a spec-conformant JSON parser.

`json.load` accepts bare `NaN` and `Infinity`; RFC 8259 does not, and neither
does `JSON.parse`. An artifact that only Python can read is not an artifact
anyone else can audit — which matters exactly when an external reviewer is
reading the tree.

The historical v1 control table was written before artifact writers rejected
non-finite JSON. Its diagnostics are normalized with an original-byte receipt;
no committed JSON file is exempt from this gate.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]

_NORMALIZED_V1 = "artifacts/runtime_spine_review/morphology-control-table-20260807.json"


def _tracked_json() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "*.json"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(result.stdout.split())


@pytest.mark.parametrize("relative_path", _tracked_json())
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
    assert _NORMALIZED_V1 in tracked


def test_normalized_v1_artifact_preserves_original_byte_provenance() -> None:
    artifact_path = _REPO_ROOT / _NORMALIZED_V1
    manifest_path = artifact_path.with_suffix(".manifest.json")
    artifact_bytes = artifact_path.read_bytes()
    artifact = json.loads(
        artifact_bytes,
        parse_constant=lambda token: pytest.fail(f"non-RFC-8259 literal {token!r}"),
    )
    manifest = json.loads(manifest_path.read_bytes())

    assert manifest["files"][artifact_path.name] == hashlib.sha256(
        artifact_bytes
    ).hexdigest()
    normalization = manifest["normalization"]
    assert normalization == {
        "original_sha256": "0e848a99d7af97220ae16335b84609f18c65feeb4a6ff80ed49a1c6d847fc550",
        "source_commit": "c00c9e9f79a45b6c5d90b5db5c136e56d1cf3ff4",
        "transformation": "non-finite diagnostics to null with explicit status",
    }
    normalized_coverage = (
        b'      "theoretical_coverage": null,\n'
        b'      "theoretical_coverage_status": "undefined_unbounded_range",\n'
    )
    normalized_maximum = (
        b'      "theoretical_max": null,\n'
        b'      "theoretical_max_status": "unbounded",\n'
    )
    assert artifact_bytes.count(normalized_coverage) == 3
    assert artifact_bytes.count(normalized_maximum) == 3
    original_bytes = artifact_bytes.replace(
        normalized_coverage,
        b'      "theoretical_coverage": NaN,\n',
    ).replace(
        normalized_maximum,
        b'      "theoretical_max": Infinity,\n',
    )
    assert hashlib.sha256(original_bytes).hexdigest() == normalization["original_sha256"]
    for metric in ("circuity", "mean_node_degree", "median_segment_length_m"):
        diagnostics = artifact["envelope_diagnostics"][metric]
        assert diagnostics["theoretical_coverage"] is None
        assert diagnostics["theoretical_coverage_status"] == "undefined_unbounded_range"
        assert diagnostics["theoretical_max"] is None
        assert diagnostics["theoretical_max_status"] == "unbounded"
