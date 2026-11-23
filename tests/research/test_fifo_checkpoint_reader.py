"""Wire-level negative controls for the bounded original-head sampler."""
import importlib.util
from pathlib import Path
import struct

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "fifo_checkpoint_sampler", ROOT / "tools/research/sample_v03_fifo_checkpoint.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
Reader = MODULE.Reader


def encode_row(tag, offset, mass, birth, a, b):
    data = struct.pack("<QQdd", tag, offset, mass, birth)
    for endpoint in (a, b):
        data += struct.pack("<Q", endpoint is not None)
        if endpoint is not None:
            data += struct.pack("<d", endpoint)
    return data


def test_fixed_wire_rows_preserve_order_and_signed_zero():
    raw = encode_row(3, 2, 0.5, 17.0, -0.0, 4.0)
    raw += encode_row(8, 0, 1.25, 20.0, 3.0, 4.5)
    reader = Reader(raw)
    rows = reader.rows(2, True)
    assert reader.pos == 128
    assert [(r["tag"], r["offset"], r["mass"], r["birth"]) for r in rows] == [
        (3, 2, 0.5, 17.0), (8, 0, 1.25, 20.0)]
    assert struct.pack("<d", rows[0]["a"]) == struct.pack("<d", -0.0)


def test_variable_options_fall_back_without_losing_next_row_alignment():
    raw = encode_row(3, 2, 0.5, 17.0, None, None)
    raw += encode_row(8, 0, 1.25, 20.0, 3.0, 4.5)
    reader = Reader(raw)
    rows = reader.rows(2, True)
    assert reader.pos == len(raw) == 112
    assert rows[0]["a"] is None and rows[0]["b"] is None
    assert rows[1] == dict(tag=8, offset=0, mass=1.25, birth=20.0, a=3.0, b=4.5)
    skipped = Reader(raw)
    assert skipped.rows(2, False) == []
    assert skipped.pos == len(raw)


def test_invalid_option_tag_is_rejected():
    raw = struct.pack("<QQddQ", 1, 0, 2.0, 3.0, 2)
    with pytest.raises(ValueError, match="invalid endpoint option"):
        Reader(raw).rows(1, True)


def test_truncation_never_returns_partial_row():
    raw = encode_row(1, 0, 2.0, 3.0, 0.0, 1.0)
    for cut in (0, 7, 32, 40, 55, 63):
        with pytest.raises(ValueError, match="truncated checkpoint"):
            Reader(raw[:cut]).rows(1, True)


def test_identity_size_and_row_count_bounds_reject_malformed_input():
    with pytest.raises(ValueError, match="identity size"):
        Reader(struct.pack("<Q", 4097)).text()
    with pytest.raises(ValueError, match="invalid row count"):
        Reader(b"").rows(100_000_001, False)
