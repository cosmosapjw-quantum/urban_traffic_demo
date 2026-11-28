"""Frontend contract: no legacy scientific modules or fallback on native path."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def call(args, *, code=None, directory=None):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    env.pop("METROFLOW_ENABLE_PYTHON_ORACLE", None)
    env.pop("METROFLOW_NATIVE_BIN_DIR", None)
    if directory is not None:
        env["METROFLOW_NATIVE_BIN_DIR"] = str(directory)
    prefix = [sys.executable, "-S"]
    return subprocess.run(
        prefix + (["-c", code] if code else ["-m", "metroflow.v1", *args]),
        env=env, text=True, capture_output=True, timeout=30,
    )


def test_native_facade_is_lazy_and_capabilities_name_real_default():
    r = call([], code=(
        "import sys,runpy; import metroflow.v1 as v; "
        "assert 'metroflow.v1.runtime' not in sys.modules; "
        "assert 'metroflow.v1.city' not in sys.modules; "
        "assert 'metroflow.v1.scenarios' not in sys.modules; "
        "sys.argv=['metroflow.v1','capabilities']; "
        "runpy.run_module('metroflow.v1',run_name='__main__')"
    ))
    assert r.returncode == 0, r.stderr
    result = json.loads(r.stdout)
    assert result["default_manifest_runner"] == "RUST_NATIVE"
    assert "d08" in result["native_commands"]


def test_native_run_fails_closed_without_backend(tmp_path):
    r = call(["run", "--manifest", "missing.json", "--until", "10",
              "--checkpoint", "state.bin", "--out", "result.json"], directory=tmp_path)
    assert r.returncode == 127
    assert "metroflow-native-run" in r.stderr
    assert "no Python fallback" in r.stderr


def test_native_alias_passes_exit_code_and_arguments(tmp_path):
    binary = tmp_path / "metroflow-akm-d08"
    binary.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\nexit 37\n")
    binary.chmod(0o755)
    r = call(["native", "d08", "1", "0", "7", "3"], directory=tmp_path)
    assert r.returncode == 37
    assert r.stdout.splitlines() == ["1", "0", "7", "3"]
