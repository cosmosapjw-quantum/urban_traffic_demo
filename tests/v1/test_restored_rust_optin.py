"""Explicit opt-in oracle for the legacy restored Rust road grammar."""
import dataclasses
import json
import math
import os
from pathlib import Path
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("METROFLOW_ENABLE_PYTHON_ORACLE") != "1"
    or not os.environ.get("METROFLOW_RESTORED_RUST_DIR"),
    reason="explicit oracle and native generated inputs required",
)

def compare(a, b, path=""):
    if isinstance(a, dict):
        assert isinstance(b, dict) and a.keys() == b.keys(), path
        for k in a:
            compare(a[k], b[k], path + "/" + k)
    elif isinstance(a, (list, tuple)):
        assert isinstance(b, list) and len(a) == len(b), (path, len(a), len(b))
        for i, (x, y) in enumerate(zip(a, b)):
            compare(x, y, path + "/" + str(i))
    elif isinstance(a, float):
        assert math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-8), (path, a, b)
    else:
        assert a == b, (path, a, b)

@pytest.mark.parametrize("style", ["grid_core", "organic", "superblock_mixed", "ring_radial"])
@pytest.mark.parametrize("interchanges", [False, True])
def test_native_restored_grammar(style, interchanges):
    from metroflow.restored_city import generate
    old = dataclasses.asdict(generate(style, n=12, seed=17, interchanges=interchanges))
    new = json.loads((Path(os.environ["METROFLOW_RESTORED_RUST_DIR"]) /
                      f"restored_{style}-{str(interchanges).lower()}.json").read_text())
    compare(old, new)
