#!/usr/bin/env python3
"""Create once, or verify, the Task 4/5 pre-optimization byte oracle."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import stat
import sys
import tempfile
from typing import Sequence

import numpy as np

from metroflow.city.graph import NodeKind, RoadClass
from metroflow.city.scalable_topology import FacilityKind, RoadHierarchy


_MANIFEST_SCHEMA = "scalable_task45_preoptimization_byte_oracle_v1"
_SERIALIZER_SCHEMA = "scalable_task45_output_payload_v1"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_MANIFEST_RELATIVE_PATH = (
    ".superpowers/sdd/scalable_synthetic_v2_implementation_plan/"
    "task-4-5-preoptimization-byte-oracle.json"
)
_PRODUCER_ARGV = (
    ".venv/bin/python",
    "tools/build_task45_preoptimization_oracle.py",
    "--output",
    _MANIFEST_RELATIVE_PATH,
)
_STYLES = (
    "grid_core",
    "organic",
    "polycentric_tod",
    "ring_radial",
    "river_constrained",
    "superblock_mixed",
)
_TARGET_POPULATION = 100_000
_URBANIZED_AREA_KM2 = 25.0
_SEED = 17
_REVIEWED_ENUM_TYPES = (RoadClass, NodeKind, FacilityKind, RoadHierarchy)
_MUTABLE_PRODUCTION_PATHS = (
    "src/metroflow/city/scalable_authority.py",
    "src/metroflow/city/scalable_blocks.py",
    "src/metroflow/city/scalable_topology.py",
    "src/metroflow/city/scalable_topology_adapter.py",
    "src/metroflow/city/scalable_validation_receipts.py",
)
_MUTABLE_PRE_STATE_SHA256 = {
    "src/metroflow/city/scalable_authority.py": (
        "04686b4b64661b39f5fe534ff7a7938a2837e9eab766a629da567596c1f2a6aa"
    ),
    "src/metroflow/city/scalable_blocks.py": (
        "3e5767e2a47b2f8c4cfcc7e83213528916ac6562fe3709fb3a81f823e6930a19"
    ),
    "src/metroflow/city/scalable_topology.py": (
        "e967ca4d628605abf418134d1b8b8be0d5746f712fa0cf4dcfe035f96f488521"
    ),
    "src/metroflow/city/scalable_topology_adapter.py": (
        "330f6cffdf506a04ba8298b2bce2791906a6966b2036a7ec4064f55143a2ac7a"
    ),
}
_IMMUTABLE_PROVENANCE_PATHS = (
    ".superpowers/sdd/scalable_synthetic_v2_implementation_plan/"
    "task-4-5-validation-performance-brief-rebind-independent-review.md",
    ".superpowers/sdd/scalable_synthetic_v2_implementation_plan/"
    "task-4-5-validation-performance-brief.md",
    "tests/test_task45_preoptimization_oracle_vectors.py",
    "tools/build_task45_preoptimization_oracle.py",
    "tools/run_task45_validation_performance.py",
)
_AUTHORIZED_NONSELF_PROVENANCE_SHA256 = {
    ".superpowers/sdd/scalable_synthetic_v2_implementation_plan/"
    "task-4-5-validation-performance-brief-rebind-independent-review.md": (
        "1111086d09bb6d31af496635e8349a6e77552ba2981c271da34215551f686681"
    ),
    ".superpowers/sdd/scalable_synthetic_v2_implementation_plan/"
    "task-4-5-validation-performance-brief.md": (
        "41585f436832e37d734b80bd52c195ca7b922170cadf4d2b69894bb8609fcf6c"
    ),
    "tests/test_task45_preoptimization_oracle_vectors.py": (
        "6c132bb0c452d20e7cd4a1350edc857e2cfb539e13456ca664295663506ff0c2"
    ),
    "tools/run_task45_validation_performance.py": (
        "d67a6a3aa281a9a05db1257e2656c582db3566f8187dc2e0db9f7f64ae54e4a1"
    ),
}
_ARRAY_CONTRACTS = (
    ("node_ids", np.dtype(np.int32), "nodes"),
    ("link_ids", np.dtype(np.int32), "links"),
    ("link_src_node_index", np.dtype(np.int32), "links"),
    ("link_dst_node_index", np.dtype(np.int32), "links"),
    ("outgoing_indptr", np.dtype(np.int32), "node_indptr"),
    ("outgoing_link_indices", np.dtype(np.int32), "links"),
    ("incoming_indptr", np.dtype(np.int32), "node_indptr"),
    ("incoming_link_indices", np.dtype(np.int32), "links"),
    ("turn_from_link_index", np.dtype(np.int32), "turns"),
    ("turn_to_link_index", np.dtype(np.int32), "turns"),
    ("turn_base_priority", np.dtype(np.float32), "turns"),
    ("turn_is_forbidden", np.dtype(np.bool_), "turns"),
)
_SHA256_TEXT = re.compile(r"[0-9a-f]{64}")
_CREATED_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z")


class _OracleFailure(RuntimeError):
    """A fail-closed oracle lifecycle error with a caller-selected exit code."""

    def __init__(self, message: str, *, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _canonical_normalize(value: object) -> object:
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("canonical floats must be finite")
        return ("float_hex", value.hex())
    if type(value) is Fraction:
        return ("fraction", value.numerator, value.denominator)
    if type(value) in _REVIEWED_ENUM_TYPES:
        enum_value = value.value
        if type(enum_value) is not str:
            raise TypeError("reviewed enum values must be exact strings")
        return enum_value
    if type(value) is tuple:
        return tuple(_canonical_normalize(item) for item in value)
    if type(value) is frozenset:
        return (
            "frozenset",
            tuple(sorted(_canonical_normalize(item) for item in value)),
        )
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def materialized_canonical_bytes(value: object) -> bytes:
    """Return the reviewed, materialized canonical JSON representation."""

    return json.dumps(
        _canonical_normalize(value),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _task4_profile(row: object) -> tuple[object, ...]:
    return (
        row.profile_id,
        row.lanes_per_direction,
        row.free_flow_speed_mps,
        row.capacity_veh_per_second,
        row.operational_road_class.value,
        row.section_roadside_profile,
        row.median_when_bidirectional,
    )


def _task4_road(row: object) -> tuple[object, ...]:
    return (
        row.physical_road_id,
        row.road_semantic_id,
        row.hierarchy.value,
        row.facility.value,
        row.profile_id,
        row.layer,
        row.layer_transition,
        row.access_directions,
        row.provenance,
        row.geometry_id,
        row.centerline_source_ref,
        row.forward_link_id,
        row.reverse_link_id,
        row.structure_group,
        row.structure_group_id,
        row.failure_group,
        row.bridge_group_id,
    )


def _task4_group(row: object) -> tuple[object, ...]:
    return (
        row.semantic_group,
        row.dense_group_id,
        row.member_physical_road_ids,
    )


def _task4_node(row: object) -> tuple[object, ...]:
    return (
        row.node_id,
        row.kind.value,
        row.x,
        row.y,
        row.zone_id,
        row.signal_group_id,
    )


def _task4_link(row: object) -> tuple[object, ...]:
    return (
        row.link_id,
        row.src_node_id,
        row.dst_node_id,
        row.road_class.value,
        row.length_m,
        row.free_flow_speed_mps,
        row.capacity_veh_per_tick,
        row.lanes,
        row.bridge_group_id,
        row.is_blockable,
        row.physical_road_id,
    )


def _task4_bridge(row: object) -> tuple[object, ...]:
    return (
        row.bridge_group_id,
        row.link_ids,
        row.barrier_id,
        row.crossing_name,
        row.bottleneck_rank_hint,
    )


def task4_output_payload(compiled: object) -> tuple[object, ...]:
    """Project the exact Task 4 public-output payload independently."""

    topology = compiled.topology
    return (
        compiled.schema_version,
        compiled.numeric_profile_policy_version,
        compiled.source_network_fingerprint,
        compiled.source_block_authority_fingerprint,
        compiled.terrain_fingerprint,
        compiled.scale_fingerprint,
        compiled.style_fingerprint,
        tuple(_task4_profile(row) for row in compiled.numeric_profiles),
        tuple(_task4_road(row) for row in compiled.road_crosswalk),
        tuple(_task4_group(row) for row in compiled.structure_group_crosswalk),
        tuple(_task4_group(row) for row in compiled.failure_group_crosswalk),
        tuple(_task4_node(row) for row in topology.nodes),
        tuple(_task4_link(row) for row in topology.links),
        tuple(_task4_bridge(row) for row in topology.bridge_crossings),
        compiled.road_geometry_fingerprint,
        compiled.road_section_fingerprint,
        compiled.node_interface_fingerprint,
        compiled.turn_authority_fingerprint,
        (
            compiled.source_node_count,
            compiled.source_physical_road_count,
            compiled.source_block_count,
            compiled.compiled_node_count,
            compiled.compiled_link_count,
            compiled.compiled_turn_count,
            compiled.permitted_turn_count,
            compiled.forbidden_u_turn_count,
            compiled.bridge_crossing_count,
            len(topology.road_geometry.assignments),
            len(topology.node_interfaces.interfaces),
        ),
        compiled.metadata_items,
    )


def _task5_profile(row: object) -> tuple[object, ...]:
    return (
        row.profile_id,
        row.lanes_per_direction,
        row.free_flow_speed_mps,
        row.capacity_veh_per_second,
        row.operational_road_class,
        row.section_roadside_profile,
        row.median_when_bidirectional,
    )


def _task5_road(row: object) -> tuple[object, ...]:
    return (
        row.physical_road_id,
        row.road_semantic_id,
        row.hierarchy,
        row.facility,
        row.profile_id,
        row.layer,
        row.layer_transition,
        row.access_directions,
        row.provenance,
        row.geometry_id,
        row.centerline_source_ref,
        row.forward_link_id,
        row.reverse_link_id,
        row.structure_group,
        row.structure_group_id,
        row.failure_group,
        row.bridge_group_id,
    )


def _task5_group(row: object) -> tuple[object, ...]:
    return (
        row.semantic_group,
        row.dense_group_id,
        row.member_physical_road_ids,
    )


def _task5_access(index: object) -> tuple[object, ...]:
    return (
        index.block_to_road_ids,
        index.block_to_node_ids,
        index.road_to_block_ids,
        index.node_to_block_ids,
        index.primary_access_by_block,
        index.incidence_visit_count,
    )


def _task5_fingerprint_set(value: object) -> tuple[object, ...]:
    return (
        value.schema_version,
        value.config,
        value.geometry,
        value.topology,
        value.link_attributes,
        value.turn_authority,
        value.blocks_access,
        value.land_use_zoning,
        value.routing_static,
        value.accessibility_static,
        value.replay_static,
        value.composite,
    )


def task5_output_payload(authority: object) -> tuple[object, ...]:
    """Project the exact Task 5 public-output payload independently."""

    return (
        authority.schema_version,
        (
            authority.scale_spec.target_population,
            authority.scale_spec.urbanized_area_km2.hex(),
        ),
        authority.style_id,
        authority.seed,
        authority.extent_mm,
        authority.width_m,
        authority.height_m,
        authority.centers_mm,
        authority.source_network_schema_version,
        authority.source_blocks_schema_version,
        authority.source_compiled_schema_version,
        authority.numeric_profile_policy_version,
        authority.source_network_fingerprint,
        authority.source_blocks_fingerprint,
        authority.source_compiled_fingerprint,
        authority.source_terrain_fingerprint,
        authority.source_scale_fingerprint,
        authority.source_style_fingerprint,
        authority.source_geometry_fingerprint,
        authority.source_section_fingerprint,
        authority.source_node_interface_fingerprint,
        authority.source_turn_authority_fingerprint,
        tuple(_task5_profile(row) for row in authority.numeric_profiles),
        tuple(_task5_road(row) for row in authority.road_crosswalk),
        tuple(_task5_group(row) for row in authority.structure_group_crosswalk),
        tuple(_task5_group(row) for row in authority.failure_group_crosswalk),
        _task5_access(authority.block_access_index),
        tuple(row.fingerprint for row in authority.block_land_use),
        authority.capacity_certificate.fingerprint,
        authority.taz_catalog.fingerprint,
        authority.poi_catalog.fingerprint,
        _task5_fingerprint_set(authority.fingerprints),
        authority.road_csr.content_fingerprint,
        authority.routing_dependency_key.fingerprint,
    )


def output_payload_bytes(task_name: str, payload: tuple[object, ...]) -> bytes:
    if task_name not in {"task4", "task5"}:
        raise ValueError("task_name must be task4 or task5")
    if type(payload) is not tuple:
        raise TypeError("output payload must be an exact tuple")
    return materialized_canonical_bytes((_SERIALIZER_SCHEMA, task_name, payload))


def output_payload_receipt(
    task_name: str,
    payload: tuple[object, ...],
) -> tuple[int, str]:
    canonical = output_payload_bytes(task_name, payload)
    return len(canonical), hashlib.sha256(canonical).hexdigest()


def array_sidecars(csr: object) -> tuple[tuple[str, int, str], ...]:
    counts = {
        "nodes": len(csr.nodes),
        "node_indptr": len(csr.nodes) + 1,
        "links": len(csr.links),
        "turns": len(csr.turns),
    }
    rows: list[tuple[str, int, str]] = []
    for name, expected_dtype, count_name in _ARRAY_CONTRACTS:
        value = getattr(csr, name)
        if type(value) is not np.ndarray:
            raise TypeError(f"{name} must be an exact ndarray")
        if value.dtype != expected_dtype:
            raise ValueError(f"{name} dtype mismatch")
        if value.shape != (counts[count_name],):
            raise ValueError(f"{name} shape mismatch")
        if not value.flags.c_contiguous:
            raise ValueError(f"{name} must be C-contiguous")
        current_bytes = value.tobytes(order="C")
        rows.append((name, value.nbytes, hashlib.sha256(current_bytes).hexdigest()))
    return tuple(rows)


def mapping_rows_sha256(csr: object) -> str:
    payload = (
        tuple(sorted(csr.node_id_to_index.items())),
        tuple(sorted(csr.link_id_to_index.items())),
        tuple(sorted(csr.turn_pair_to_index.items())),
        csr.topology_cache_key,
    )
    return hashlib.sha256(materialized_canonical_bytes(payload)).hexdigest()


def metadata_items_sha256(metadata_items: tuple[tuple[str, object], ...]) -> str:
    if type(metadata_items) is not tuple:
        raise TypeError("metadata_items must be an exact tuple")
    return hashlib.sha256(materialized_canonical_bytes(metadata_items)).hexdigest()


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(_REPOSITORY_ROOT).as_posix()
    except ValueError:
        return str(path)


def _read_regular_file(
    path: Path,
    *,
    exit_code: int,
    label: str,
) -> tuple[bytes, tuple[int, int, int, int, str]]:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags)
        status_before = os.fstat(descriptor)
        if not stat.S_ISREG(status_before.st_mode):
            raise OSError("opened object is not a regular file")
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            descriptor = None
            raw = handle.read()
            status_after = os.fstat(handle.fileno())
    except OSError as exc:
        raise _OracleFailure(
            f"{label} is not a regular non-symlink: {_display_path(path)}",
            exit_code=exit_code,
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    identity_fields_before = (
        status_before.st_dev,
        status_before.st_ino,
        status_before.st_size,
        status_before.st_mtime_ns,
    )
    identity_fields_after = (
        status_after.st_dev,
        status_after.st_ino,
        status_after.st_size,
        status_after.st_mtime_ns,
    )
    try:
        path_status = path.lstat()
    except OSError as exc:
        raise _OracleFailure(
            f"{label} changed while being read: {_display_path(path)}",
            exit_code=exit_code,
        ) from exc
    path_identity = (
        path_status.st_dev,
        path_status.st_ino,
        path_status.st_size,
        path_status.st_mtime_ns,
    )
    if (
        identity_fields_before != identity_fields_after
        or identity_fields_after != path_identity
        or stat.S_ISLNK(path_status.st_mode)
        or not stat.S_ISREG(path_status.st_mode)
    ):
        raise _OracleFailure(
            f"{label} changed while being read: {_display_path(path)}",
            exit_code=exit_code,
        )
    digest = hashlib.sha256(raw).hexdigest()
    return raw, (*identity_fields_after, digest)


def _sha256_file(path: Path, *, exit_code: int) -> str:
    _raw, identity = _read_regular_file(
        path,
        exit_code=exit_code,
        label="required file",
    )
    return identity[-1]


def _regular_file_digest(relative_path: str, *, exit_code: int) -> str:
    path = _REPOSITORY_ROOT / relative_path
    return _sha256_file(path, exit_code=exit_code)


def _reviewed_mutable_pre_state() -> tuple[tuple[str, str, str], ...]:
    return tuple(
        (
            path,
            "absent" if path.endswith("scalable_validation_receipts.py") else "file",
            ""
            if path.endswith("scalable_validation_receipts.py")
            else _MUTABLE_PRE_STATE_SHA256[path],
        )
        for path in _MUTABLE_PRODUCTION_PATHS
    )


def _mutable_production_state(*, create: bool) -> tuple[tuple[str, str, str], ...]:
    rows: list[tuple[str, str, str]] = []
    for relative_path in _MUTABLE_PRODUCTION_PATHS:
        path = _REPOSITORY_ROOT / relative_path
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            rows.append((relative_path, "absent", ""))
            continue
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise _OracleFailure(
                f"mutable production path has unsupported type: {relative_path}",
                exit_code=2 if create else 4,
            )
        rows.append(
            (
                relative_path,
                "file",
                _sha256_file(path, exit_code=2 if create else 4),
            )
        )
    result = tuple(rows)
    if create:
        if result != _reviewed_mutable_pre_state():
            raise _OracleFailure(
                "mutable production pre-state differs from the reviewed bytes",
                exit_code=2,
            )
    else:
        for path, state, _digest in result:
            if path.endswith("scalable_validation_receipts.py"):
                if state not in {"absent", "file"}:
                    raise _OracleFailure(
                        "receipt-module transition is unsupported",
                        exit_code=4,
                    )
            elif state != "file":
                raise _OracleFailure(
                    f"mutable production file is missing: {path}",
                    exit_code=4,
                )
    return result


def _immutable_provenance(*, exit_code: int) -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = []
    for path in sorted(_IMMUTABLE_PROVENANCE_PATHS):
        digest = _regular_file_digest(path, exit_code=exit_code)
        expected = _AUTHORIZED_NONSELF_PROVENANCE_SHA256.get(path)
        if expected is not None and digest != expected:
            raise _OracleFailure(
                f"immutable provenance is not authorized: {path}",
                exit_code=exit_code,
            )
        rows.append((path, digest))
    return tuple(rows)


def _immutable_production_census(*, exit_code: int) -> tuple[tuple[str, str, str], ...]:
    source_root = _REPOSITORY_ROOT / "src" / "metroflow"
    rows: list[tuple[str, str, str]] = []

    def _require_directory(path: Path) -> None:
        try:
            mode = path.lstat().st_mode
        except OSError as exc:
            raise _OracleFailure(
                f"immutable production directory disappeared: {path}",
                exit_code=exit_code,
            ) from exc
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise _OracleFailure(
                f"immutable production directory is a symlink or not a directory: {path}",
                exit_code=exit_code,
            )

    def _raise_walk_error(error: OSError) -> None:
        raise _OracleFailure(
            f"immutable production census failed: {error}",
            exit_code=exit_code,
        ) from error

    _require_directory(source_root)
    for directory, directory_names, file_names in os.walk(
        source_root,
        topdown=True,
        onerror=_raise_walk_error,
        followlinks=False,
    ):
        directory_path = Path(directory)
        _require_directory(directory_path)
        directory_names.sort()
        file_names.sort()
        for directory_name in directory_names:
            _require_directory(directory_path / directory_name)
        for filename in file_names:
            if not filename.endswith(".py"):
                continue
            path = Path(directory) / filename
            relative_path = path.relative_to(_REPOSITORY_ROOT).as_posix()
            if relative_path in _MUTABLE_PRODUCTION_PATHS:
                continue
            try:
                mode = path.lstat().st_mode
            except FileNotFoundError as exc:
                raise _OracleFailure(
                    f"immutable production candidate disappeared: {relative_path}",
                    exit_code=exit_code,
                ) from exc
            if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                raise _OracleFailure(
                    f"immutable production candidate is not a regular non-symlink: {relative_path}",
                    exit_code=exit_code,
                )
            rows.append(
                (
                    relative_path,
                    "file",
                    _sha256_file(path, exit_code=exit_code),
                )
            )
    rows.sort()
    return tuple(rows)


def _environment(*, exit_code: int) -> tuple[str, str, str, str, str, str]:
    try:
        relative_cwd = Path.cwd().resolve().relative_to(_REPOSITORY_ROOT).as_posix()
    except ValueError as exc:
        raise _OracleFailure(
            "current directory must be inside the repository",
            exit_code=exit_code,
        ) from exc
    if relative_cwd != ".":
        raise _OracleFailure(
            "current directory must be the repository root",
            exit_code=exit_code,
        )
    return (
        platform.python_implementation(),
        platform.python_version(),
        np.__version__,
        platform.platform(),
        sys.byteorder,
        relative_cwd,
    )


def _build_case(style_id: str) -> dict[str, object]:
    from metroflow.city.scale import CityScaleSpec
    from metroflow.city.scalable_authority import build_scalable_static_authority
    from metroflow.city.scalable_blocks import build_scalable_block_authority
    from metroflow.city.scalable_topology import build_scalable_street_network
    from metroflow.city.scalable_topology_adapter import compile_scalable_topology

    scale = CityScaleSpec(_TARGET_POPULATION, _URBANIZED_AREA_KM2)
    network = build_scalable_street_network(scale, style_id, _SEED)
    blocks = build_scalable_block_authority(network)
    compiled = compile_scalable_topology(network, block_authority=blocks)
    authority = build_scalable_static_authority(
        scale,
        style_id,
        _SEED,
        network,
        blocks,
        compiled,
    )

    task4_payload = task4_output_payload(compiled)
    task5_payload = task5_output_payload(authority)
    task4_count, task4_sha256 = output_payload_receipt("task4", task4_payload)
    task5_count, task5_sha256 = output_payload_receipt("task5", task5_payload)
    return {
        "target_population": _TARGET_POPULATION,
        "urbanized_area_km2_hex": _URBANIZED_AREA_KM2.hex(),
        "style_id": style_id,
        "seed": _SEED,
        "task4": (
            task4_count,
            task4_sha256,
            compiled.fingerprint,
            array_sidecars(compiled.road_csr),
            mapping_rows_sha256(compiled.road_csr),
            metadata_items_sha256(compiled.metadata_items),
        ),
        "task5": (
            task5_count,
            task5_sha256,
            authority.fingerprint,
            array_sidecars(authority.road_csr),
            mapping_rows_sha256(authority.road_csr),
        ),
    }


def _manifest_bytes(manifest: dict[str, object]) -> bytes:
    return (
        json.dumps(
            manifest,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def _validate_array_sidecar_shape(value: object, *, label: str) -> None:
    if type(value) is not list or len(value) != len(_ARRAY_CONTRACTS):
        raise _OracleFailure(f"manifest {label} array rows are invalid", exit_code=3)
    for row, (expected_name, _dtype, _count_name) in zip(
        value,
        _ARRAY_CONTRACTS,
        strict=True,
    ):
        if (
            type(row) is not list
            or len(row) != 3
            or row[0] != expected_name
            or type(row[1]) is not int
            or row[1] < 0
            or type(row[2]) is not str
            or _SHA256_TEXT.fullmatch(row[2]) is None
        ):
            raise _OracleFailure(
                f"manifest {label} array row is invalid: {expected_name}",
                exit_code=3,
            )


def _validate_case_shape(value: object, *, expected_style: str) -> None:
    if type(value) is not dict or set(value) != {
        "target_population",
        "urbanized_area_km2_hex",
        "style_id",
        "seed",
        "task4",
        "task5",
    }:
        raise _OracleFailure("manifest case shape is invalid", exit_code=3)
    if (
        type(value["target_population"]) is not int
        or value["target_population"] != _TARGET_POPULATION
        or type(value["urbanized_area_km2_hex"]) is not str
        or value["urbanized_area_km2_hex"] != _URBANIZED_AREA_KM2.hex()
        or type(value["style_id"]) is not str
        or value["style_id"] != expected_style
        or type(value["seed"]) is not int
        or value["seed"] != _SEED
    ):
        raise _OracleFailure(
            f"manifest case header is invalid: {expected_style}",
            exit_code=3,
        )
    task4 = value["task4"]
    task5 = value["task5"]
    if type(task4) is not list or len(task4) != 6:
        raise _OracleFailure("manifest Task 4 receipt shape is invalid", exit_code=3)
    if type(task5) is not list or len(task5) != 5:
        raise _OracleFailure("manifest Task 5 receipt shape is invalid", exit_code=3)
    for label, row in (("Task 4", task4), ("Task 5", task5)):
        if (
            type(row[0]) is not int
            or row[0] < 0
            or type(row[1]) is not str
            or _SHA256_TEXT.fullmatch(row[1]) is None
            or type(row[2]) is not str
            or _SHA256_TEXT.fullmatch(row[2]) is None
            or type(row[-1]) is not str
            or _SHA256_TEXT.fullmatch(row[-1]) is None
        ):
            raise _OracleFailure(
                f"manifest {label} digest fields are invalid",
                exit_code=3,
            )
    _validate_array_sidecar_shape(task4[3], label="Task 4")
    _validate_array_sidecar_shape(task5[3], label="Task 5")
    if (
        type(task4[4]) is not str
        or _SHA256_TEXT.fullmatch(task4[4]) is None
        or type(task4[5]) is not str
        or _SHA256_TEXT.fullmatch(task4[5]) is None
        or type(task5[4]) is not str
        or _SHA256_TEXT.fullmatch(task5[4]) is None
    ):
        raise _OracleFailure("manifest sidecar digest is invalid", exit_code=3)


def _validate_manifest_shape(value: dict[str, object]) -> None:
    exact_keys = {
        "schema_version",
        "created_utc",
        "environment",
        "producer_argv",
        "mutable_production_pre_state",
        "immutable_production_dependency_sha256",
        "immutable_provenance_sha256",
        "serializer_schema",
        "cases",
    }
    if set(value) != exact_keys:
        raise _OracleFailure("manifest top-level shape is invalid", exit_code=3)
    if (
        value["schema_version"] != _MANIFEST_SCHEMA
        or value["serializer_schema"] != _SERIALIZER_SCHEMA
        or value["producer_argv"] != list(_PRODUCER_ARGV)
        or type(value["created_utc"]) is not str
        or _CREATED_UTC.fullmatch(value["created_utc"]) is None
    ):
        raise _OracleFailure("manifest immutable header is invalid", exit_code=3)
    environment = value["environment"]
    if (
        type(environment) is not list
        or len(environment) != 6
        or any(type(item) is not str or not item for item in environment)
        or environment[-1] != "."
    ):
        raise _OracleFailure("manifest environment shape is invalid", exit_code=3)
    mutable_rows = _as_tuple_rows(
        value["mutable_production_pre_state"],
        width=3,
        label="mutable production pre-state",
    )
    if mutable_rows != _reviewed_mutable_pre_state():
        raise _OracleFailure(
            "manifest mutable pre-state is not the reviewed pre-state",
            exit_code=3,
        )
    provenance_rows = _as_tuple_rows(
        value["immutable_provenance_sha256"],
        width=2,
        label="immutable provenance",
    )
    if tuple(row[0] for row in provenance_rows) != tuple(
        sorted(_IMMUTABLE_PROVENANCE_PATHS)
    ) or any(_SHA256_TEXT.fullmatch(row[1]) is None for row in provenance_rows):
        raise _OracleFailure("manifest provenance shape is invalid", exit_code=3)
    census_rows = _as_tuple_rows(
        value["immutable_production_dependency_sha256"],
        width=3,
        label="immutable production census",
    )
    census_paths = tuple(row[0] for row in census_rows)
    if (
        not census_rows
        or census_paths != tuple(sorted(set(census_paths)))
        or any(
            not path.startswith("src/metroflow/")
            or not path.endswith(".py")
            or path in _MUTABLE_PRODUCTION_PATHS
            or state != "file"
            or _SHA256_TEXT.fullmatch(digest) is None
            for path, state, digest in census_rows
        )
    ):
        raise _OracleFailure("manifest immutable census shape is invalid", exit_code=3)
    cases = value["cases"]
    if type(cases) is not list or len(cases) != len(_STYLES):
        raise _OracleFailure("manifest case set is invalid", exit_code=3)
    for case, expected_style in zip(cases, _STYLES, strict=True):
        _validate_case_shape(case, expected_style=expected_style)


def _manifest_identity(path: Path, *, exit_code: int) -> tuple[int, int, int, int, str]:
    _raw, identity = _read_regular_file(
        path,
        exit_code=exit_code,
        label="manifest",
    )
    return identity


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _read_manifest(path: Path, *, exit_code: int = 3) -> dict[str, object]:
    identity_before = _manifest_identity(path, exit_code=exit_code)
    try:
        raw, read_identity = _read_regular_file(
            path,
            exit_code=exit_code,
            label="manifest",
        )
        value = json.loads(raw, parse_constant=_reject_json_constant)
        canonical = _manifest_bytes(value)
    except (OSError, UnicodeDecodeError, ValueError, TypeError) as exc:
        raise _OracleFailure("manifest is missing or invalid", exit_code=exit_code) from exc
    identity_after = _manifest_identity(path, exit_code=exit_code)
    if identity_before != read_identity or read_identity != identity_after:
        raise _OracleFailure("manifest changed while being read", exit_code=exit_code)
    if type(value) is not dict or raw != canonical:
        raise _OracleFailure("manifest is not canonical JSON", exit_code=exit_code)
    try:
        _validate_manifest_shape(value)
    except _OracleFailure as exc:
        if exit_code == exc.exit_code:
            raise
        raise _OracleFailure(str(exc), exit_code=exit_code) from exc
    return value


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags)
        status = os.fstat(descriptor)
        if not stat.S_ISDIR(status.st_mode):
            raise OSError("publication parent is not a directory")
        os.fsync(descriptor)
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _write_create_once(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary_path, path)
        except FileExistsError as exc:
            raise _OracleFailure("manifest output already exists", exit_code=2) from exc
        try:
            _fsync_directory(path.parent)
        except OSError as exc:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            try:
                _fsync_directory(path.parent)
            except OSError:
                pass
            raise _OracleFailure(
                "manifest publish could not be made durable by directory fsync",
                exit_code=2,
            ) from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def _as_tuple_rows(value: object, *, width: int, label: str) -> tuple[tuple[str, ...], ...]:
    if type(value) is not list:
        raise _OracleFailure(f"manifest {label} must be a list", exit_code=3)
    rows: list[tuple[str, ...]] = []
    for row in value:
        if type(row) is not list or len(row) != width or any(type(item) is not str for item in row):
            raise _OracleFailure(f"manifest {label} row is invalid", exit_code=3)
        rows.append(tuple(row))
    return tuple(rows)


def _comparison_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _emit_comparison(label: str, expected: object, current: object) -> bool:
    matches = type(expected) is type(current) and expected == current
    print(
        f"comparison.{label}|status={'PASS' if matches else 'FAIL'}"
        f"|expected={_comparison_json(expected)}"
        f"|current={_comparison_json(current)}"
    )
    return matches


def _emit_keyed_row_comparisons(
    label: str,
    expected_rows: tuple[tuple[str, ...], ...],
    current_rows: tuple[tuple[str, ...], ...],
) -> bool:
    expected_by_key = {row[0]: row for row in expected_rows}
    current_by_key = {row[0]: row for row in current_rows}
    matches = True
    for key in sorted(set(expected_by_key) | set(current_by_key)):
        matches = (
            _emit_comparison(
                f"{label}.{key}",
                expected_by_key.get(key),
                current_by_key.get(key),
            )
            and matches
        )
    return matches


def _emit_comparison_tree(label: str, expected: object, current: object) -> bool:
    if type(expected) is dict and type(current) is dict:
        matches = True
        for key in sorted(set(expected) | set(current)):
            matches = (
                _emit_comparison_tree(
                    f"{label}.{key}",
                    expected.get(key),
                    current.get(key),
                )
                and matches
            )
        return matches
    if type(expected) is list and type(current) is list:
        matches = _emit_comparison(
            f"{label}.length",
            len(expected),
            len(current),
        )
        for index in range(max(len(expected), len(current))):
            expected_value = expected[index] if index < len(expected) else None
            current_value = current[index] if index < len(current) else None
            matches = (
                _emit_comparison_tree(
                    f"{label}.{index}",
                    expected_value,
                    current_value,
                )
                and matches
            )
        return matches
    return _emit_comparison(label, expected, current)


def _create_manifest(output: Path) -> int:
    if output.exists() or output.is_symlink():
        raise _OracleFailure("manifest output already exists", exit_code=2)
    environment_before = _environment(exit_code=2)
    mutable_before = _mutable_production_state(create=True)
    census_before = _immutable_production_census(exit_code=2)
    provenance_before = _immutable_provenance(exit_code=2)
    cases = tuple(_build_case(style_id) for style_id in _STYLES)
    environment_after = _environment(exit_code=2)
    mutable_after = _mutable_production_state(create=True)
    census_after = _immutable_production_census(exit_code=2)
    provenance_after = _immutable_provenance(exit_code=2)
    if environment_before != environment_after:
        raise _OracleFailure("environment changed during case construction", exit_code=2)
    if mutable_before != mutable_after:
        raise _OracleFailure("mutable production changed during case construction", exit_code=2)
    if census_before != census_after:
        raise _OracleFailure("immutable production changed during case construction", exit_code=2)
    if provenance_before != provenance_after:
        raise _OracleFailure("immutable provenance changed during case construction", exit_code=2)
    manifest: dict[str, object] = {
        "schema_version": _MANIFEST_SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "environment": environment_after,
        "producer_argv": _PRODUCER_ARGV,
        "mutable_production_pre_state": mutable_after,
        "immutable_production_dependency_sha256": census_after,
        "immutable_provenance_sha256": provenance_after,
        "serializer_schema": _SERIALIZER_SCHEMA,
        "cases": cases,
    }
    payload = _manifest_bytes(manifest)
    _write_create_once(output, payload)
    if output.read_bytes() != payload or _read_manifest(
        output,
        exit_code=2,
    ) != json.loads(payload):
        raise _OracleFailure("manifest self-read failed", exit_code=2)
    print(f"created {output.relative_to(_REPOSITORY_ROOT).as_posix()}")
    return 0


def _compare_mutable_states(
    old_rows: tuple[tuple[str, ...], ...],
    new_rows: tuple[tuple[str, str, str], ...],
) -> None:
    expected_paths = tuple(_MUTABLE_PRODUCTION_PATHS)
    if tuple(row[0] for row in old_rows) != expected_paths:
        raise _OracleFailure("manifest mutable path set is invalid", exit_code=4)
    for row in old_rows:
        path, state, digest = row
        if state not in {"file", "absent"} or (state == "absent") != (digest == ""):
            raise _OracleFailure(
                f"manifest mutable pre-state row is invalid: {path}",
                exit_code=4,
            )
    for old_row, new_row in zip(old_rows, new_rows, strict=True):
        _emit_comparison(
            f"mutable_production.{old_row[0]}",
            old_row,
            new_row,
        )


def _verify_manifest(manifest_path: Path) -> int:
    manifest_identity_before = _manifest_identity(manifest_path, exit_code=3)
    manifest = _read_manifest(manifest_path)
    environment_before = _environment(exit_code=3)
    provenance_before = _immutable_provenance(exit_code=3)
    if not _emit_comparison(
        "environment",
        manifest["environment"],
        list(environment_before),
    ):
        raise _OracleFailure("manifest environment mismatch", exit_code=3)
    manifest_provenance = _as_tuple_rows(
        manifest["immutable_provenance_sha256"],
        width=2,
        label="immutable provenance",
    )
    if not _emit_keyed_row_comparisons(
        "immutable_provenance",
        manifest_provenance,
        provenance_before,
    ):
        raise _OracleFailure("immutable provenance mismatch", exit_code=3)

    census_before = _immutable_production_census(exit_code=4)
    manifest_census = _as_tuple_rows(
        manifest["immutable_production_dependency_sha256"],
        width=3,
        label="immutable production census",
    )
    if not _emit_keyed_row_comparisons(
        "immutable_production",
        manifest_census,
        census_before,
    ):
        raise _OracleFailure("immutable production dependency mismatch", exit_code=4)
    old_mutable = _as_tuple_rows(
        manifest["mutable_production_pre_state"],
        width=3,
        label="mutable production pre-state",
    )
    mutable_before = _mutable_production_state(create=False)
    _compare_mutable_states(old_mutable, mutable_before)

    cases = tuple(_build_case(style_id) for style_id in _STYLES)
    environment_after = _environment(exit_code=3)
    provenance_after = _immutable_provenance(exit_code=3)
    census_after = _immutable_production_census(exit_code=4)
    mutable_after = _mutable_production_state(create=False)
    environment_stable = _emit_comparison(
        "environment_stability",
        list(environment_before),
        list(environment_after),
    )
    provenance_stable = _emit_keyed_row_comparisons(
        "immutable_provenance_stability",
        provenance_before,
        provenance_after,
    )
    census_stable = _emit_keyed_row_comparisons(
        "immutable_production_stability",
        census_before,
        census_after,
    )
    mutable_stable = _emit_keyed_row_comparisons(
        "mutable_production_stability",
        mutable_before,
        mutable_after,
    )
    if not environment_stable or not provenance_stable:
        raise _OracleFailure("immutable environment/provenance changed during verify", exit_code=3)
    if not census_stable or not mutable_stable:
        raise _OracleFailure("production state changed during verify", exit_code=4)
    current_cases = json.loads(_manifest_bytes({"cases": cases}))["cases"]
    expected_by_style = {
        case.get("style_id"): case for case in manifest["cases"] if type(case) is dict
    }
    current_by_style = {case["style_id"]: case for case in current_cases}
    cases_match = True
    for style_id in _STYLES:
        cases_match = (
            _emit_comparison_tree(
                f"case.{style_id}",
                expected_by_style.get(style_id),
                current_by_style.get(style_id),
            )
            and cases_match
        )
    if not cases_match:
        raise _OracleFailure("one or more output oracle cases differ", exit_code=5)
    if manifest_identity_before != _manifest_identity(manifest_path, exit_code=3):
        raise _OracleFailure("manifest changed during verification", exit_code=3)
    print("verification=PASS")
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        description="Create once or verify the frozen Task 4/5 byte oracle.",
        allow_abbrev=False,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--output", metavar="PATH")
    group.add_argument("--verify", metavar="PATH")
    if any(
        argument.startswith("--output=") or argument.startswith("--verify=")
        for argument in arguments
    ):
        parser.error("option=value syntax is not admitted")
    if arguments.count("--output") > 1 or arguments.count("--verify") > 1:
        parser.error("repeated arguments are not admitted")
    namespace = parser.parse_args(arguments)
    selected = namespace.output if namespace.output is not None else namespace.verify
    if selected != _MANIFEST_RELATIVE_PATH:
        parser.error(f"PATH must be exactly {_MANIFEST_RELATIVE_PATH}")
    return namespace


def main(argv: Sequence[str] | None = None) -> int:
    namespace = _parse_args(argv)
    try:
        if namespace.output is not None:
            return _create_manifest(_REPOSITORY_ROOT / namespace.output)
        return _verify_manifest(_REPOSITORY_ROOT / namespace.verify)
    except _OracleFailure as exc:
        print(f"oracle_error={exc}", file=sys.stderr)
        return exc.exit_code
    except Exception as exc:
        mode_exit = 2 if namespace.output is not None else 5
        print(f"oracle_error={type(exc).__name__}: {exc}", file=sys.stderr)
        return mode_exit


if __name__ == "__main__":
    raise SystemExit(main())
