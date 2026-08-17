"""Scalable city validation receipt registry.

Provides frozen receipt records, thread-safe registration, lookup, and
schema/seal constants for the Task 3 → Task 5 validation pipeline.

PR92 scope: records, annotations, scalar/dataclass/enum/mapping grammar,
base stream/seal.  H-002 ordering, P/R registry, and Task C are deferred
to later PRs.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

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
