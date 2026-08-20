"""The required CI verdict must not depend on the day its runner resolves tools."""

from __future__ import annotations

import re
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
_REQUIRED_PINS = {
    "maturin": "1.14.1",
    "networkx": "3.6.1",
    "numpy": "2.5.1",
    "osmnx": "2.1.1",
    "pytest": "9.0.2",
    "ruff": "0.16.2",
    "scipy": "1.18.0",
}


def _constraint_pins(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.partition("#")[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s;]+)", line)
        assert match is not None, f"CI constraint is not an exact pin: {raw_line!r}"
        pins[match.group(1).lower().replace("_", "-")] = match.group(2)
    return pins


def test_ci_constraints_pin_every_verdict_bearing_direct_dependency() -> None:
    """Removing or ranging a direct tool pin reopens the audited CI drift."""
    pins = _constraint_pins(_REPO_ROOT / "ci-constraints.txt")

    assert {name: pins.get(name) for name in _REQUIRED_PINS} == _REQUIRED_PINS


def test_every_ci_install_consumes_constraints_on_one_python_patch() -> None:
    """A job bypassing the constraints would make the final aggregate non-frozen."""
    workflow = (_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "ubuntu-latest" not in workflow
    assert workflow.count("runs-on: ubuntu-24.04") == 5
    assert workflow.count('python-version: "3.12.14"') == 4
    assert not re.search(r"uses: actions/(?:checkout|setup-python)@v\d", workflow)
    assert len(re.findall(r"uses: actions/(?:checkout|setup-python)@[0-9a-f]{40}", workflow)) == 8
    assert workflow.count("fetch-depth: 0") == 4, (
        "historical provenance tests require the reachable Git history in every checkout"
    )

    editable_installs = [
        line.strip()
        for line in workflow.splitlines()
        if "python -m pip install" in line and " -e " in line
    ]
    assert len(editable_installs) == 3
    assert all("-c ci-constraints.txt" in line for line in editable_installs)
