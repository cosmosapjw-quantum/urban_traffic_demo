"""Fail-closed previous-source checkpoint gate for exact-view V03 probe."""
import hashlib
from pathlib import Path

import pytest

from tools.research.v03_exact_view_cross_binary_probe_20261120 import validate_old_source


def historical(path: Path) -> dict:
    b = path.read_bytes()
    return {
        "status": "EXECUTED_SOURCE_BOUND_25650_SCOPED",
        "reached_end_s": 25650.0,
        "original_matrix_sha256": "f" * 64,
        "original_8GiB_process_cap_bytes": 8 * 1024**3,
        "original_native_cap_bytes": 5242806391,
        "checkpoint_bytes": len(b),
        "final_checkpoint_sha256": hashlib.sha256(b).hexdigest(),
        "source_sha256": "1" * 64,
        "loaded_native_sha256": "2" * 64,
        "original_driver_identity": "3" * 64,
    }


def test_original_checkpoint_identity_verifies_exact_bytes(tmp_path):
    p = tmp_path / "original.bin"
    p.write_bytes(b"legacy original packet state\x00\x01\xff")
    validate_old_source(historical(p), p, "f" * 64)


@pytest.mark.parametrize("mutation", ("matrix", "budget", "time", "state", "binary"))
def test_checkpoint_gate_rejects_metadata_or_wire_substitution(tmp_path, mutation):
    p = tmp_path / "original.bin"
    p.write_bytes(b"original source state")
    data = historical(p)
    if mutation == "matrix":
        data["original_matrix_sha256"] = "e" * 64
    elif mutation == "budget":
        data["original_native_cap_bytes"] += 1
    elif mutation == "time":
        data["reached_end_s"] = 25700.
    elif mutation == "state":
        p.write_bytes(b"different original s")
    elif mutation == "binary":
        data.pop("loaded_native_sha256")
    with pytest.raises(ValueError):
        validate_old_source(data, p, "f" * 64)
