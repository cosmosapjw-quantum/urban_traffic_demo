"""Scalable city validation receipt registry.

Provides frozen receipt records, thread-safe registration, lookup, and
schema/seal constants for the Task 3 → Task 5 validation pipeline.

PR92 scope: records, annotations, scalar/dataclass/enum/mapping grammar,
base stream/seal.  H-002 ordering, P/R registry, and Task C are deferred
to later PRs.
"""

from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from fractions import Fraction
from typing import Mapping

import numpy as np

# ---------------------------------------------------------------------------
# Seal schema constants — must match tools/run_task45_validation_performance.py
# ---------------------------------------------------------------------------
_NETWORK_SEAL_SCHEMA = "scalable_network_current_content_v1"
_BLOCKS_SEAL_SCHEMA = "scalable_blocks_current_content_v1"
_COMPILED_SEAL_SCHEMA = "scalable_compiled_current_content_v1"
_COMPILED_AGGREGATE_SEAL_SCHEMA = "scalable_compiled_aggregate_current_v1"
_STATIC_SEAL_SCHEMA = "scalable_static_current_content_v1"
_TASK5_INVOCATION_SEAL_SCHEMA = "scalable_task5_invocation_current_v1"
_TASK5_NETWORK_PROJECTION_SCHEMA = "scalable_task5_network_projection_v1"
_TASK5_BLOCKS_PROJECTION_SCHEMA = "scalable_task5_blocks_projection_v1"
_TASK5_COMPILED_PROJECTION_SCHEMA = "scalable_task5_compiled_projection_v1"

# Receipt policy version constants
_NETWORK_RECEIPT_POLICY_VERSION = "scalable_network_receipt_policy_v1"
_BLOCKS_RECEIPT_POLICY_VERSION = "scalable_blocks_receipt_policy_v1"
_COMPILED_RECEIPT_POLICY_VERSION = "scalable_compiled_receipt_policy_v1"
_STATIC_RECEIPT_POLICY_VERSION = "scalable_static_receipt_policy_v1"
_TASK5_SNAPSHOT_POLICY_VERSION = "scalable_task5_snapshot_policy_v1"

_COMPILED_CONTENT_SEAL_SCHEMAS = tuple(
    (name, _COMPILED_SEAL_SCHEMA)
    for name in (
        "compiled.csr_arrays",
        "compiled.csr_entities",
        "compiled.csr_mappings",
        "compiled.geometry_catalog",
        "compiled.header",
        "compiled.metadata",
        "compiled.node_interface_catalog",
        "compiled.numeric_and_crosswalks",
        "compiled.section_catalog",
        "compiled.topology_entities",
    )
) + (
    ("task5.blocks_projection", _TASK5_BLOCKS_PROJECTION_SCHEMA),
    ("task5.compiled_projection", _TASK5_COMPILED_PROJECTION_SCHEMA),
    ("task5.network_projection", _TASK5_NETWORK_PROJECTION_SCHEMA),
)

_STATIC_CONTENT_SEAL_SCHEMAS = tuple(
    (name, _STATIC_SEAL_SCHEMA)
    for name in (
        "static.block_access_index",
        "static.block_land_use",
        "static.capacity_certificate",
        "static.fingerprint_set",
        "static.header",
        "static.immutable_csr_arrays",
        "static.immutable_csr_entities",
        "static.immutable_csr_header",
        "static.immutable_csr_mappings",
        "static.numeric_and_crosswalks",
        "static.poi_catalog",
        "static.routing_dependency_key",
        "static.taz_catalog",
    )
)


# ---------------------------------------------------------------------------
# Receipt record
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class _ValidationReceipt:
    """Immutable receipt proving a validation step was completed.

    Each receipt records the pipeline stage name, the schema version and
    fingerprint of the validated artifact, the policy versions active at
    validation time, and the source-seal and content-seal schemas that
    were verified.
    """

    stage_name: str
    schema_version: str
    fingerprint: str
    policy_versions: tuple[tuple[str, str], ...]
    source_seal_schemas: tuple[tuple[str, str], ...]
    content_seal_schemas: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class _VerifiedTask5SourceSnapshot:
    """Immutable snapshot proving Task 5 source inputs were verified.

    Captures the network, blocks, and compiled fingerprints along with
    their receipt references, at the point the Task 5 static authority
    was built.
    """

    network_fingerprint: str
    blocks_fingerprint: str
    compiled_fingerprint: str
    network_receipt: _ValidationReceipt
    blocks_receipt: _ValidationReceipt
    compiled_receipt: _ValidationReceipt


# ---------------------------------------------------------------------------
# Registry — module-level, thread-safe via one RLock
# ---------------------------------------------------------------------------
_registry_lock = threading.RLock()
_registry: dict[str, _ValidationReceipt] = {}


def _register_validation_receipt(receipt: _ValidationReceipt) -> None:
    """Register a validated receipt by its stage name.

    Raises ``ValueError`` if a receipt for the same stage is already
    registered with a different fingerprint.
    """
    if not isinstance(receipt, _ValidationReceipt):
        raise TypeError(
            f"expected _ValidationReceipt, got {type(receipt).__name__}"
        )
    with _registry_lock:
        existing = _registry.get(receipt.stage_name)
        if existing is not None:
            if existing.fingerprint != receipt.fingerprint:
                raise ValueError(
                    f"receipt for stage {receipt.stage_name!r} already "
                    f"registered with fingerprint {existing.fingerprint!r}, "
                    f"cannot replace with {receipt.fingerprint!r}"
                )
            # Same fingerprint — idempotent, no-op
            return
        _registry[receipt.stage_name] = receipt


def _lookup_validation_receipt(
    stage_name: str,
    expected_schema_version: str,
    expected_fingerprint: str,
    *,
    expected_policy_versions: tuple[tuple[str, str], ...] = (),
    expected_source_seal_schemas: tuple[tuple[str, str], ...] = (),
    expected_content_seal_schemas: tuple[tuple[str, str], ...] = (),
) -> _ValidationReceipt:
    """Look up and verify a previously registered receipt.

    Raises ``KeyError`` if no receipt is registered, ``ValueError`` if
    the receipt does not match the expected schema version, fingerprint,
    policy versions, or seal schemas.
    """
    with _registry_lock:
        receipt = _registry.get(stage_name)
    if receipt is None:
        raise KeyError(f"no receipt registered for stage {stage_name!r}")
    if receipt.schema_version != expected_schema_version:
        raise ValueError(
            f"receipt schema version mismatch for {stage_name!r}: "
            f"expected {expected_schema_version!r}, "
            f"got {receipt.schema_version!r}"
        )
    if receipt.fingerprint != expected_fingerprint:
        raise ValueError(
            f"receipt fingerprint mismatch for {stage_name!r}: "
            f"expected {expected_fingerprint!r}, "
            f"got {receipt.fingerprint!r}"
        )
    if expected_policy_versions:
        if receipt.policy_versions != expected_policy_versions:
            raise ValueError(
                f"receipt policy version mismatch for {stage_name!r}: "
                f"expected {expected_policy_versions!r}, "
                f"got {receipt.policy_versions!r}"
            )
    if expected_source_seal_schemas:
        if receipt.source_seal_schemas != expected_source_seal_schemas:
            raise ValueError(
                f"receipt source seal schema mismatch for {stage_name!r}: "
                f"expected {expected_source_seal_schemas!r}, "
                f"got {receipt.source_seal_schemas!r}"
            )
    if expected_content_seal_schemas:
        if receipt.content_seal_schemas != expected_content_seal_schemas:
            raise ValueError(
                f"receipt content seal schema mismatch for {stage_name!r}: "
                f"expected {expected_content_seal_schemas!r}, "
                f"got {receipt.content_seal_schemas!r}"
            )
    return receipt


def _clear_validation_receipts_for_test() -> None:
    """Clear all registered receipts.  For testing only."""
    with _registry_lock:
        _registry.clear()


# ---------------------------------------------------------------------------
# H-002-R1 Normalized-Value Ordering and Canonical Serialization
# ---------------------------------------------------------------------------


def _canonical_normalize(value: object) -> object:
    """Recursively normalize a value into a canonical Python representation.

    - None, bool, int, str: unchanged
    - float: ('float_hex', value.hex()) if finite
    - Fraction: ('fraction', numerator, denominator)
    - Enum: string enum value
    - tuple: tuple of recursively normalized items
    - frozenset: ('frozenset', tuple(sorted(N(item))))
    - dict/mapping: ('dict', tuple(sorted_by_key_and_value(N(k), N(v)))) with key collision check
    """
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("canonical floats must be finite")
        return ("float_hex", value.hex())
    if isinstance(value, Fraction):
        return ("fraction", value.numerator, value.denominator)
    if isinstance(value, Enum):
        enum_val = value.value
        if type(enum_val) is not str:
            raise TypeError("reviewed enum values must be exact strings")
        return enum_val
    if type(value) is tuple:
        return tuple(_canonical_normalize(item) for item in value)
    if type(value) is frozenset:
        return (
            "frozenset",
            tuple(sorted(_canonical_normalize(item) for item in value)),  # type: ignore[type-var]
        )
    if isinstance(value, (dict, Mapping)):
        pairs = [
            (_canonical_normalize(k), _canonical_normalize(v))
            for k, v in value.items()
        ]
        sorted_pairs = sorted(pairs)  # sorts by (N(k), N(v))
        # Adjacent normalized-key collision check
        for i in range(len(sorted_pairs) - 1):
            if sorted_pairs[i][0] == sorted_pairs[i + 1][0]:
                raise ValueError(
                    f"normalized key collision in mapping: {sorted_pairs[i][0]!r}"
                )
        return ("dict", tuple(sorted_pairs))
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def _virtual_eq(x: object, y: object) -> bool:
    """Return True iff normalized values N(x) == N(y)."""
    return _canonical_normalize(x) == _canonical_normalize(y)


def _virtual_lt(x: object, y: object) -> bool:
    """Return True iff normalized value N(x) < N(y)."""
    return _canonical_normalize(x) < _canonical_normalize(y)  # type: ignore[operator]


def _pair_lt(
    p1: tuple[object, object], p2: tuple[object, object]
) -> bool:
    """Return True iff normalized pair (N(k1), N(v1)) < (N(k2), N(v2))."""
    return (_canonical_normalize(p1[0]), _canonical_normalize(p1[1])) < (  # type: ignore[operator]
        _canonical_normalize(p2[0]),
        _canonical_normalize(p2[1]),
    )


def materialized_canonical_bytes(value: object) -> bytes:
    """Return the reviewed, materialized canonical JSON representation."""
    return json.dumps(
        _canonical_normalize(value),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


# ---------------------------------------------------------------------------
# Deep Immutable Projection P and CSR 12-Row Contracts
# ---------------------------------------------------------------------------

_CSR_ARRAY_NAMES: tuple[str, ...] = (
    "node_ids",
    "link_ids",
    "link_src_node_index",
    "link_dst_node_index",
    "outgoing_indptr",
    "outgoing_link_indices",
    "incoming_indptr",
    "incoming_link_indices",
    "turn_from_link_index",
    "turn_to_link_index",
    "turn_base_priority",
    "turn_is_forbidden",
)


def _deep_immutable_projection(value: object) -> object:
    """Deep immutable projection P(x) such that P(P(x)) == P(x).

    - Scalars (None, bool, int, float, str, bytes, Fraction, Enum): unchanged
    - numpy.ndarray: read-only C-contiguous copy with writeable=False
    - list, tuple: tuple of deep-projected items
    - set, frozenset: frozenset of deep-projected items
    - dict, Mapping: tuple of (P(k), P(v)) pairs
    - dataclass: new instance with deep-projected fields
    """
    if value is None or type(value) in (bool, int, float, str, bytes, Fraction):
        return value
    if isinstance(value, Enum):
        return value
    if isinstance(value, np.ndarray):
        if not value.flags.writeable and value.flags.c_contiguous:
            return value
        arr = np.ascontiguousarray(value).copy()
        arr.flags.writeable = False
        return arr
    if isinstance(value, (list, tuple)):
        return tuple(_deep_immutable_projection(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_deep_immutable_projection(item) for item in value)
    if isinstance(value, (dict, Mapping)):
        return tuple(
            (_deep_immutable_projection(k), _deep_immutable_projection(v))
            for k, v in value.items()
        )
    if is_dataclass(value) and not isinstance(value, type):
        field_values = {
            f.name: _deep_immutable_projection(getattr(value, f.name))
            for f in fields(value)
        }
        return type(value)(**field_values)
    return value
