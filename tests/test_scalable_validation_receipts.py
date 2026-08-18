"""Tests for scalable_validation_receipts — Task B base grammar.

PR92 behavior clusters:
  1. Receipt record is frozen/slotted/copyable
  2. Registry register/lookup/clear lifecycle
  3. Lookup verifies schema/fingerprint/policy/seal parity
  4. Duplicate registration: same fingerprint is idempotent, different raises
  5. Schema literal parity with tools/run_task45_validation_performance.py
  6. VerifiedTask5SourceSnapshot is frozen/slotted
"""

from __future__ import annotations

import copy
import importlib

import pytest

from metroflow.city.scalable_validation_receipts import (
    _ValidationReceipt,
    _VerifiedTask5SourceSnapshot,
    _clear_validation_receipts_for_test,
    _lookup_validation_receipt,
    _register_validation_receipt,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    """Ensure a clean receipt registry for every test."""
    _clear_validation_receipts_for_test()
    yield
    _clear_validation_receipts_for_test()


def _make_receipt(
    *,
    stage: str = "network",
    schema: str = "v1",
    fp: str = "abc123",
    policies: tuple[tuple[str, str], ...] = (),
    source_seals: tuple[tuple[str, str], ...] = (),
    content_seals: tuple[tuple[str, str], ...] = (),
) -> _ValidationReceipt:
    return _ValidationReceipt(
        stage_name=stage,
        schema_version=schema,
        fingerprint=fp,
        policy_versions=policies,
        source_seal_schemas=source_seals,
        content_seal_schemas=content_seals,
    )


# ---- 1. Receipt record is frozen/slotted/copyable ----


def test_receipt_is_frozen_dataclass() -> None:
    receipt = _make_receipt()
    with pytest.raises(AttributeError):
        receipt.stage_name = "other"  # type: ignore[misc]


def test_receipt_has_slots() -> None:
    receipt = _make_receipt()
    assert hasattr(receipt, "__slots__")
    assert not hasattr(receipt, "__dict__")


def test_receipt_is_deepcopyable() -> None:
    receipt = _make_receipt(
        policies=(("receipt_policy", "v1"),),
        content_seals=(("net.current", "schema_v1"),),
    )
    copied = copy.deepcopy(receipt)
    assert copied == receipt
    assert type(copied) is _ValidationReceipt


# ---- 2. Registry register/lookup/clear lifecycle ----


def test_register_then_lookup_returns_same_receipt() -> None:
    receipt = _make_receipt()
    _register_validation_receipt(receipt)
    found = _lookup_validation_receipt(
        "network",
        "v1",
        "abc123",
    )
    assert found is receipt


def test_lookup_missing_stage_raises_key_error() -> None:
    with pytest.raises(KeyError, match="no receipt registered"):
        _lookup_validation_receipt("missing", "v1", "x")


def test_clear_removes_all_registered_receipts() -> None:
    _register_validation_receipt(_make_receipt(stage="a", fp="1"))
    _register_validation_receipt(_make_receipt(stage="b", fp="2"))
    _clear_validation_receipts_for_test()
    with pytest.raises(KeyError):
        _lookup_validation_receipt("a", "v1", "1")
    with pytest.raises(KeyError):
        _lookup_validation_receipt("b", "v1", "2")


# ---- 3. Lookup verifies schema/fingerprint/policy/seal parity ----


def test_lookup_rejects_schema_version_mismatch() -> None:
    _register_validation_receipt(_make_receipt())
    with pytest.raises(ValueError, match="schema version mismatch"):
        _lookup_validation_receipt("network", "wrong_schema", "abc123")


def test_lookup_rejects_fingerprint_mismatch() -> None:
    _register_validation_receipt(_make_receipt())
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        _lookup_validation_receipt("network", "v1", "wrong_fp")


def test_lookup_rejects_policy_version_mismatch() -> None:
    _register_validation_receipt(
        _make_receipt(policies=(("receipt_policy", "v1"),))
    )
    with pytest.raises(ValueError, match="policy version mismatch"):
        _lookup_validation_receipt(
            "network",
            "v1",
            "abc123",
            expected_policy_versions=(("receipt_policy", "v2"),),
        )


def test_lookup_rejects_source_seal_schema_mismatch() -> None:
    _register_validation_receipt(
        _make_receipt(source_seals=(("net.current", "schema_v1"),))
    )
    with pytest.raises(ValueError, match="source seal schema mismatch"):
        _lookup_validation_receipt(
            "network",
            "v1",
            "abc123",
            expected_source_seal_schemas=(("net.current", "schema_v2"),),
        )


def test_lookup_rejects_content_seal_schema_mismatch() -> None:
    _register_validation_receipt(
        _make_receipt(content_seals=(("net.current", "schema_v1"),))
    )
    with pytest.raises(ValueError, match="content seal schema mismatch"):
        _lookup_validation_receipt(
            "network",
            "v1",
            "abc123",
            expected_content_seal_schemas=(("net.current", "schema_v2"),),
        )


# ---- 4. Duplicate registration: idempotent vs different fingerprint ----


def test_register_same_fingerprint_is_idempotent() -> None:
    receipt = _make_receipt()
    _register_validation_receipt(receipt)
    _register_validation_receipt(receipt)  # No error
    found = _lookup_validation_receipt("network", "v1", "abc123")
    assert found is receipt


def test_register_conflicting_content_for_same_fingerprint_raises() -> None:
    _register_validation_receipt(_make_receipt(fp="first", schema="v1"))
    with pytest.raises(ValueError, match="conflicting receipt"):
        _register_validation_receipt(_make_receipt(fp="first", schema="v2"))


def test_register_multiple_fingerprints_coexist() -> None:
    r1 = _make_receipt(stage="network", fp="fp_alpha")
    r2 = _make_receipt(stage="network", fp="fp_beta")
    _register_validation_receipt(r1)
    _register_validation_receipt(r2)
    assert _lookup_validation_receipt("network", "v1", "fp_alpha") is r1
    assert _lookup_validation_receipt("network", "v1", "fp_beta") is r2



def test_register_rejects_non_receipt_type() -> None:
    with pytest.raises(TypeError, match="expected _ValidationReceipt"):
        _register_validation_receipt("not a receipt")  # type: ignore[arg-type]


# ---- 5. Schema literal parity with validation performance tool ----


def test_schema_literals_match_validation_performance_tool() -> None:
    receipts = importlib.import_module(
        "metroflow.city.scalable_validation_receipts"
    )
    controller = importlib.import_module("tools.run_task45_validation_performance")

    expected_names = [
        "_NETWORK_SEAL_SCHEMA",
        "_BLOCKS_SEAL_SCHEMA",
        "_COMPILED_SEAL_SCHEMA",
        "_COMPILED_AGGREGATE_SEAL_SCHEMA",
        "_STATIC_SEAL_SCHEMA",
        "_TASK5_INVOCATION_SEAL_SCHEMA",
        "_TASK5_NETWORK_PROJECTION_SCHEMA",
        "_TASK5_BLOCKS_PROJECTION_SCHEMA",
        "_TASK5_COMPILED_PROJECTION_SCHEMA",
        "_NETWORK_RECEIPT_POLICY_VERSION",
        "_BLOCKS_RECEIPT_POLICY_VERSION",
        "_COMPILED_RECEIPT_POLICY_VERSION",
        "_STATIC_RECEIPT_POLICY_VERSION",
        "_TASK5_SNAPSHOT_POLICY_VERSION",
    ]
    for name in expected_names:
        assert getattr(receipts, name) == getattr(controller, name), (
            f"literal mismatch: {name}"
        )


# ---- 6. VerifiedTask5SourceSnapshot is frozen/slotted ----


def test_task5_snapshot_is_frozen() -> None:
    receipt = _make_receipt()
    snap = _VerifiedTask5SourceSnapshot(
        network_fingerprint="nfp",
        blocks_fingerprint="bfp",
        compiled_fingerprint="cfp",
        network_receipt=receipt,
        blocks_receipt=receipt,
        compiled_receipt=receipt,
    )
    with pytest.raises(AttributeError):
        snap.network_fingerprint = "other"  # type: ignore[misc]


def test_task5_snapshot_has_slots() -> None:
    receipt = _make_receipt()
    snap = _VerifiedTask5SourceSnapshot(
        network_fingerprint="nfp",
        blocks_fingerprint="bfp",
        compiled_fingerprint="cfp",
        network_receipt=receipt,
        blocks_receipt=receipt,
        compiled_receipt=receipt,
    )
    assert hasattr(snap, "__slots__")
    assert not hasattr(snap, "__dict__")


def test_task5_snapshot_is_deepcopyable() -> None:
    receipt = _make_receipt()
    snap = _VerifiedTask5SourceSnapshot(
        network_fingerprint="nfp",
        blocks_fingerprint="bfp",
        compiled_fingerprint="cfp",
        network_receipt=receipt,
        blocks_receipt=receipt,
        compiled_receipt=receipt,
    )
    copied = copy.deepcopy(snap)
    assert copied == snap
    assert type(copied) is _VerifiedTask5SourceSnapshot


# ---- 7. H-002-R1 Virtual Normalized-Value Ordering ----


def test_canonical_normalize_scalars() -> None:
    from fractions import Fraction
    from metroflow.city.scalable_validation_receipts import _canonical_normalize

    assert _canonical_normalize(None) is None
    assert _canonical_normalize(True) is True
    assert _canonical_normalize(42) == 42
    assert _canonical_normalize("hello") == "hello"
    assert _canonical_normalize(3.14) == ("float_hex", (3.14).hex())
    assert _canonical_normalize(Fraction(3, 7)) == ("fraction", 3, 7)


def test_canonical_normalize_rejects_non_finite_float() -> None:
    from metroflow.city.scalable_validation_receipts import _canonical_normalize

    with pytest.raises(ValueError, match="finite"):
        _canonical_normalize(float("nan"))
    with pytest.raises(ValueError, match="finite"):
        _canonical_normalize(float("inf"))


def test_canonical_normalize_frozenset_is_sorted() -> None:
    from metroflow.city.scalable_validation_receipts import _canonical_normalize

    res = _canonical_normalize(frozenset([10, 2]))
    assert res == ("frozenset", (2, 10))


def test_canonical_normalize_mapping_sorts_and_detects_collision() -> None:
    from metroflow.city.scalable_validation_receipts import _canonical_normalize

    res = _canonical_normalize({10: "ten", 2: "two"})
    assert res == ("dict", ((2, "two"), (10, "ten")))


def test_virtual_comparator_parity() -> None:
    from metroflow.city.scalable_validation_receipts import (
        _pair_lt,
        _virtual_eq,
        _virtual_lt,
    )

    assert _virtual_eq(42, 42)
    assert not _virtual_eq(42, 43)
    assert _virtual_lt(2, 10)
    assert not _virtual_lt(10, 2)
    assert _pair_lt((2, "b"), (2, "c"))
    assert _pair_lt((2, "z"), (3, "a"))


def test_materialized_canonical_bytes_deterministic() -> None:
    from metroflow.city.scalable_validation_receipts import materialized_canonical_bytes

    b1 = materialized_canonical_bytes({"b": 2, "a": 1})
    b2 = materialized_canonical_bytes({"a": 1, "b": 2})
    assert b1 == b2
    assert b1 == b'["dict",[["a",1],["b",2]]]'


# ---- 8. Deep Immutable Projection P ----


def test_deep_immutable_projection_idempotence() -> None:
    import numpy as np
    from metroflow.city.scalable_validation_receipts import _deep_immutable_projection

    data = {
        "scalar": 42,
        "arr": np.array([1, 2, 3], dtype=np.int32),
        "nested": {"list": [4, 5, 6], "tuple": (7, 8)},
        "set": {9, 10},
    }
    p1 = _deep_immutable_projection(data)
    p2 = _deep_immutable_projection(p1)

    # Check P(P(x)) == P(x)
    assert p1 == p2
    # Verify arrays are read-only
    for k, v in p1:  # type: ignore[union-attr]
        if k == "arr":
            assert not v.flags.writeable


def test_deep_immutable_projection_dataclass() -> None:
    from metroflow.city.scalable_validation_receipts import (
        _deep_immutable_projection,
    )

    receipt = _make_receipt()
    p1 = _deep_immutable_projection(receipt)
    p2 = _deep_immutable_projection(p1)
    assert p1 == receipt
    assert p2 == p1


# ---- 9. CSR 12-Row Contract ----


def test_csr_12_row_names() -> None:
    from metroflow.city.scalable_validation_receipts import _CSR_ARRAY_NAMES

    assert len(_CSR_ARRAY_NAMES) == 12
    assert "node_ids" in _CSR_ARRAY_NAMES
    assert "link_ids" in _CSR_ARRAY_NAMES
    assert "turn_is_forbidden" in _CSR_ARRAY_NAMES
