"""The OSMnx oracle must reproduce from a pinned version, or it is not a pin.

A golden file nobody re-derives is the same hand-transcribed table
`morphology_reference.py` already is. These tests re-run OSMnx against the
committed fixtures and compare, so the reference stays falsifiable.

OSMnx is a test-only dependency (`pip install -e ".[dev,oracle]"`). When it is
absent these tests SKIP, which is visible in the report. They never pass by
falling back to some other measurement — a silent fallback for an explicitly
selected backend is forbidden by the claim ledger, and the same reasoning
applies to an oracle.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

osmnx = pytest.importorskip("osmnx", reason="oracle extra not installed")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GOLDEN = _REPO_ROOT / "tests" / "data" / "osmnx_morphology_oracle.json"


def _regen_module():
    """Load the regeneration script by path; `tools/` is not an importable package."""

    spec = importlib.util.spec_from_file_location(
        "regen_osmnx_oracle", _REPO_ROOT / "tools" / "regen_osmnx_oracle.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _golden() -> dict:
    return json.loads(_GOLDEN.read_text(encoding="utf-8"))


def test_the_pinned_osmnx_version_is_the_one_installed() -> None:
    """A golden measured by a different OSMnx is not this golden."""

    assert _golden()["oracle"]["osmnx_version"] == osmnx.__version__


def test_the_golden_records_the_conventions_it_was_measured_under() -> None:
    """An oracle whose definition is unstated cannot adjudicate a definition."""

    oracle = _golden()["oracle"]

    assert oracle["options"]["statistic"] == "BOEING_2019_HO"
    assert oracle["options"]["weight"] is None, "H_o is unweighted; weighting it would be H_w"
    assert oracle["options"]["undirected"] is True
    assert oracle["options"]["num_bins"] == 36
    assert oracle["options"]["retain_all"] is True, (
        "osm_import keeps every component; dropping them here would compare two "
        "different graphs and call the difference a metric disagreement"
    )
    assert "self-loops excluded" in oracle["conventions"]
    assert "ODbL" in _golden()["attribution"]


def test_the_oracle_reproduces_from_the_committed_fixtures() -> None:
    """Re-derive every value rather than trusting the stored numbers."""

    import math

    current = _regen_module().collect()
    stored = _golden()

    assert set(current["cities"]) == set(stored["cities"])
    for name, record in stored["cities"].items():
        assert current["cities"][name]["source_sha256"] == record["source_sha256"]
        for metric, value in record["metrics"].items():
            assert math.isclose(
                current["cities"][name]["metrics"][metric], value, abs_tol=1e-9
            ), f"{name}.{metric} does not reproduce"


def test_osmnx_reads_two_extracts_our_own_importer_rejects() -> None:
    """Localizes paris and prague to our lane parser, not to their geometry.

    The extracts README records these as import failures. The oracle shows the
    files themselves are fine: OSMnx builds a graph from both. So the defect is
    in `osm_import`'s lane interpretation, and fixing it widens the reference
    base from five cities to seven — worth more than any threshold change, given
    every band currently rests on n=5.
    """

    golden = _golden()

    assert {"paris.osm", "prague.osm"} <= set(golden["cities"])
    assert golden["failed"] == {}
