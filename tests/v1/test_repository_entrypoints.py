"""Public installed/source entry points under the repository's real conftest."""

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def isolated(code):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    return subprocess.run(
        [sys.executable, "-S", "-c", code], env=env, check=True, capture_output=True, text=True
    )


def test_facade_imports_scientific_path_without_optional_dependencies():
    result = isolated(
        "import sys; import metroflow.v1 as v; "
        "assert callable(v.compile_access); assert callable(v.JourneyModel); "
        "assert not ({'numpy','jax','torch','scipy'} & sys.modules.keys())"
    )
    assert result.returncode == 0


def test_module_cli_reports_real_capabilities():
    result = isolated(
        "import runpy,sys; sys.argv=['metroflow.v1','capabilities']; "
        "runpy.run_module('metroflow.v1',run_name='__main__')"
    )
    payload = json.loads(result.stdout)
    assert payload["api"] == "metroflow.v1"
    assert "JourneyModel" in payload["exports"]
    assert payload["full_day_runner"] == "SCOPED_SYNTHETIC_TWO_ZONE"
    assert payload["full_city_100k_runner"] == "NOT_VERIFIED"


def test_legacy_root_api_remains_available():
    from metroflow import WorldState, make_empty_world_state

    assert isinstance(make_empty_world_state(), WorldState)


def test_clean_checkout_can_rebuild_city_inputs_and_replay(tmp_path):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    subprocess.run(
        [
            sys.executable,
            "-S",
            str(ROOT / "tools/run_v1_foundation.py"),
            "--prepare-inputs",
            "--out",
            str(tmp_path),
        ],
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=45,
    )
    report = json.loads((tmp_path / "EXPERIMENTS.json").read_text())
    import pytest

    control, area = report["cases"]
    assert control["mean_journey_s"] == pytest.approx(302.22222222222223)
    assert area["mean_journey_s"] == pytest.approx(333.41106400500934)
    assert all(case["completed"] == pytest.approx(2.0) for case in report["cases"])
    assert all(case["max_residence_residual"] < 1e-10 for case in report["cases"])
