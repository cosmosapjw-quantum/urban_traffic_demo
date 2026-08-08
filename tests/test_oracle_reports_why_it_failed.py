"""A failed measurement must say what failed, and a partial golden is not one.

CI ran `tools/regen_osmnx_oracle.py --check` and printed::

    MISMATCH city set changed: stored ['barcelona.osm', ...] != current []
    1 mismatch(es); the oracle does not reproduce

That diagnosis is wrong in a specific, expensive way. The city set had not
changed -- the fixtures were all present and byte-identical. Every one of the
seven measurements raised::

    ImportError: scipy must be installed as an optional dependency
                 to calculate entropy.

because the `oracle` extra pinned `osmnx` and `networkx` but not `scipy`, which
`osmnx.bearing.orientation_entropy` needs. It passed locally only because the
JAX/Torch extras happen to drag scipy in, so the dependency was satisfied by
accident on the one machine that ever ran it.

`collect()` records each failure in `payload["failed"]` under a comment reading
"recorded, never silenced". `_check()` never reads that key, so the record was
written and thrown away, and the operator was pointed at the fixtures instead of
at the missing dependency. Recording a reason nobody prints IS silencing it.

These tests need no oracle extra: the script imports osmnx and networkx inside
its functions, so the module loads anywhere and these run in the default job --
which is where a dependency-resolution defect should be caught.
"""

from __future__ import annotations

import importlib.util
import json
import tomllib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _regen_module():
    spec = importlib.util.spec_from_file_location(
        "regen_osmnx_oracle_under_test", _REPO_ROOT / "tools" / "regen_osmnx_oracle.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _stored_oracle_block() -> dict:
    golden = json.loads(
        (_REPO_ROOT / "tests" / "data" / "osmnx_morphology_oracle.json").read_text(
            encoding="utf-8"
        )
    )
    return golden["oracle"]


_SCIPY_REASON = "ImportError: scipy must be installed as an optional dependency"


def test_check_prints_the_recorded_reason_each_measurement_failed(capsys) -> None:
    """The operator must be told `scipy`, not told the fixtures changed.

    Fails today because `_check` inspects only `cities`, so the sole output is
    the city-set line -- which blames the input data for a missing dependency.
    """

    module = _regen_module()
    payload = {
        "oracle": _stored_oracle_block(),
        "cities": {},
        "failed": {"barcelona.osm": _SCIPY_REASON, "seoul.osm": _SCIPY_REASON},
    }

    exit_code = module._check(payload)
    printed = capsys.readouterr().out

    assert exit_code == 1
    assert "barcelona.osm" in printed and "seoul.osm" in printed
    assert "scipy" in printed, (
        "the recorded reason was thrown away; the operator cannot see why it failed"
    )


def test_a_check_that_measured_nothing_does_not_report_success(
    tmp_path, monkeypatch, capsys
) -> None:
    """Coverage loss must not be maskable by a golden that also lost it.

    Regenerate the golden in an environment missing scipy and BOTH sides hold
    zero cities. The set comparison then agrees, the per-city loop has nothing
    to iterate, and today `_check` prints "oracle reproduces: 0 cities" and
    returns 0 -- a green parity gate over an empty measurement.

    Pointing `_GOLDEN` at such a file is what makes this test load-bearing: read
    against the real committed golden it would return 1 for the unrelated reason
    that seven cities went missing, and pass while proving nothing.
    """

    module = _regen_module()
    empty_golden = tmp_path / "osmnx_morphology_oracle.json"
    empty_golden.write_text(
        json.dumps({"oracle": _stored_oracle_block(), "cities": {}, "failed": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "_GOLDEN", empty_golden)
    monkeypatch.setattr(module, "_REPO_ROOT", tmp_path)

    # `failed` is empty on purpose. With a recorded failure the reason loop
    # would fail the check on its own and this test would lock nothing about
    # measuring nothing -- the fixtures simply being gone raises no exception.
    payload = {"oracle": _stored_oracle_block(), "cities": {}, "failed": {}}

    assert module._check(payload) == 1, "a check that measured nothing must not pass"
    assert "no fixture was measured" in capsys.readouterr().out


def test_a_partial_golden_is_never_written(tmp_path, monkeypatch, capsys) -> None:
    """Writing 6 of 7 cities and exiting 0 mints a smaller oracle in silence.

    The next `--check` then passes against the reduced set, so the coverage loss
    becomes the new reference. Today `main()` writes the file and returns 0.
    """

    module = _regen_module()
    golden = tmp_path / "osmnx_morphology_oracle.json"
    monkeypatch.setattr(module, "_GOLDEN", golden)
    monkeypatch.setattr(
        module,
        "collect",
        lambda: {
            "schema_version": "osmnx_morphology_oracle_v1",
            "oracle": _stored_oracle_block(),
            "cities": {"barcelona.osm": {}},
            "failed": {"seoul.osm": _SCIPY_REASON},
        },
    )
    monkeypatch.setattr("sys.argv", ["regen_osmnx_oracle.py"])

    exit_code = module.main()

    assert exit_code == 1, "a partial measurement must not exit 0"
    assert not golden.exists(), "a golden missing a city must not be committed as the oracle"
    assert "seoul.osm" in capsys.readouterr().out


def test_a_missing_dependency_is_reported_once_not_once_per_fixture() -> None:
    """A missing import is an environment fault, not seven fixture faults.

    Recording `ImportError` per fixture is what produced the misdirection: seven
    identical entries about scipy, filed under the names of seven innocent
    `.osm` files. Let it propagate so `main()`'s existing handler names the
    install command instead.

    Skips without the oracle extra: `collect()` imports osmnx at its top, and a
    silent substitute for an explicitly selected backend is forbidden.
    """

    pytest.importorskip("osmnx", reason="oracle extra not installed")
    module = _regen_module()

    def _raise_missing_scipy(_path):
        raise ImportError("scipy must be installed as an optional dependency")

    original = module.measure
    module.measure = _raise_missing_scipy
    try:
        with pytest.raises(ImportError, match="scipy"):
            module.collect()
    finally:
        module.measure = original


def _pyproject() -> dict:
    return tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_the_oracle_extra_declares_every_dependency_the_oracle_uses() -> None:
    """scipy is a hard requirement of the oracle, not an optional nicety.

    `osmnx.bearing.orientation_entropy` raises ImportError without it, and
    orientation entropy is the metric the whole parity claim rests on. Leaving
    it undeclared means the extra installs an oracle that cannot measure.
    """

    extras = _pyproject()["project"]["optional-dependencies"]
    assert any(
        requirement.split("=")[0].split("<")[0].split(">")[0].strip() == "scipy"
        for requirement in extras["oracle"]
    ), "the oracle extra installs osmnx without scipy, so entropy raises ImportError"


def test_the_lint_gate_declares_its_rules_instead_of_inheriting_them() -> None:
    """An undeclared rule set is a gate whose meaning changes under us.

    `[tool.ruff]` set only `line-length` and `exclude`, so the enabled rules were
    whatever that day's ruff defaulted to. ruff was unpinned in `[dev]`, so CI
    installed 0.16.2 while this machine had 0.15.7 -- same config, same code,
    **0 findings locally against 529 in CI**. Declaring the selection makes the
    gate mean one thing across versions; pinning the version makes its fixes and
    formatting reproducible.
    """

    config = _pyproject()["tool"]["ruff"]
    selected = config.get("lint", {}).get("select")
    assert selected, "ruff's rule selection is inherited from its defaults, which drift"

    dev = _pyproject()["project"]["optional-dependencies"]["dev"]
    ruff_pins = [item for item in dev if item.replace("-", "_").startswith("ruff")]
    assert ruff_pins and all("==" in pin for pin in ruff_pins), (
        f"ruff must be pinned exactly so the gate is reproducible; got {ruff_pins}"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__]))
