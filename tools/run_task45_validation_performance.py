#!/usr/bin/env python3
"""Run the frozen Task 4/5 isolated current-content RSS protocol."""

from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
import gc
import hashlib
import json
import math
import multiprocessing
import os
from pathlib import Path
import platform
import resource
import secrets
import select
import socket
import stat
import statistics
import sys
import time
import traceback
from typing import Any, Sequence


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_REPORT_RELATIVE_PATH = (
    ".superpowers/sdd/scalable_synthetic_v2_implementation_plan/"
    "task-4-5-validation-performance-report.md"
)
_EXACT_ARGUMENTS = (
    "--mode",
    "isolated-rss",
    "--target-population",
    "1000000",
    "--urbanized-area-km2",
    "250",
    "--style-id",
    "grid_core",
    "--seed",
    "17",
    "--replicates",
    "2",
    "--output",
    _REPORT_RELATIVE_PATH,
)
_EXACT_COMMAND = (
    ".venv/bin/python",
    "tools/run_task45_validation_performance.py",
    *_EXACT_ARGUMENTS,
)
_SAMPLE_INTERVAL_NS = 2_000_000
_MAX_SAMPLE_INTERVAL_NS = 5_000_000
_STABILITY_SAMPLE_COUNT = 200
_STABILITY_SPAN_KIB = 1024
_STABILITY_TIMEOUT_NS = 10_000_000_000
_READY_TIMEOUT_SECONDS = 1800.0
_WORKLOAD_TIMEOUT_NS = 900_000_000_000
_RSS_LIMIT_KIB = 32_768
_NETWORK_SEAL_SCHEMA = "scalable_network_current_content_v1"
_BLOCKS_SEAL_SCHEMA = "scalable_blocks_current_content_v1"
_COMPILED_SEAL_SCHEMA = "scalable_compiled_current_content_v1"
_COMPILED_AGGREGATE_SEAL_SCHEMA = "scalable_compiled_aggregate_current_v1"
_STATIC_SEAL_SCHEMA = "scalable_static_current_content_v1"
_TASK5_INVOCATION_SEAL_SCHEMA = "scalable_task5_invocation_current_v1"
_TASK5_NETWORK_PROJECTION_SCHEMA = "scalable_task5_network_projection_v1"
_TASK5_BLOCKS_PROJECTION_SCHEMA = "scalable_task5_blocks_projection_v1"
_TASK5_COMPILED_PROJECTION_SCHEMA = "scalable_task5_compiled_projection_v1"
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


@dataclass(frozen=True, slots=True)
class _ReplicateResult:
    replicate: int
    child_pid: int
    status: str
    error: str | None
    baseline_kib: float | None
    peak_kib: int | None
    delta_kib: float | None
    maximum_sample_gap_ns: int | None
    inclusive_ru_maxrss_kib: int | None
    fingerprints: object | None
    receipt_values: object | None
    environment: object | None
    child_exit_code: int | None
    raw_samples: tuple[tuple[int, str, int], ...]


class _LineChannel:
    """Nonce-bound newline JSON over one private socket."""

    def __init__(self, control_socket: socket.socket, nonce: str) -> None:
        self._socket = control_socket
        self._nonce = nonce
        self._buffer = bytearray()

    def send(self, event: str, **payload: object) -> None:
        message = {"event": event, "nonce": self._nonce, **payload}
        encoded = (
            json.dumps(
                message,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        self._socket.sendall(encoded)

    def _pop_message(self) -> dict[str, object] | None:
        newline = self._buffer.find(b"\n")
        if newline < 0:
            return None
        raw = bytes(self._buffer[:newline])
        del self._buffer[: newline + 1]
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("control channel sent invalid JSON") from exc
        if (
            type(value) is not dict
            or type(value.get("event")) is not str
            or value.get("nonce") != self._nonce
        ):
            raise RuntimeError("control channel event or nonce mismatch")
        return value

    def receive(self, timeout_seconds: float) -> dict[str, object]:
        deadline = time.monotonic() + timeout_seconds
        while True:
            message = self._pop_message()
            if message is not None:
                return message
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("control channel receive timed out")
            readable, _, _ = select.select((self._socket,), (), (), remaining)
            if not readable:
                raise TimeoutError("control channel receive timed out")
            chunk = self._socket.recv(65_536)
            if not chunk:
                raise RuntimeError("control channel closed before a complete event")
            self._buffer.extend(chunk)

    def poll(self) -> dict[str, object] | None:
        message = self._pop_message()
        if message is not None:
            return message
        readable, _, _ = select.select((self._socket,), (), (), 0.0)
        if not readable:
            return None
        chunk = self._socket.recv(65_536)
        if not chunk:
            raise RuntimeError("control channel closed unexpectedly")
        self._buffer.extend(chunk)
        return self._pop_message()


def _plain_receipt_value(value: object) -> object:
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is tuple:
        return tuple(_plain_receipt_value(item) for item in value)
    if is_dataclass(value) and not isinstance(value, type):
        return (
            type(value).__module__,
            type(value).__qualname__,
            tuple(
                (field.name, _plain_receipt_value(getattr(value, field.name)))
                for field in fields(value)
            ),
        )
    raise TypeError(f"unsupported receipt report value: {type(value).__name__}")


def _require_exact_launcher(*, executable: str, script_path: str, cwd: str) -> None:
    expected_venv = str(_REPOSITORY_ROOT / ".venv")
    expected_executable = str(_REPOSITORY_ROOT / ".venv/bin/python")
    expected_script = str(_REPOSITORY_ROOT / "tools/run_task45_validation_performance.py")
    expected_cwd = str(_REPOSITORY_ROOT)
    if (
        type(executable) is not str
        or type(script_path) is not str
        or type(cwd) is not str
        or sys.prefix != expected_venv
        or sys.base_prefix == sys.prefix
        or executable != expected_executable
        or script_path != expected_script
        or cwd != expected_cwd
    ):
        raise RuntimeError("controller launcher does not match the frozen command")


def _child_environment(
    numpy_version: str,
    numpy_origin: str,
) -> tuple[str, str, str, str, str, str, str, str, str]:
    if (
        type(numpy_version) is not str
        or not numpy_version
        or type(numpy_origin) is not str
        or not numpy_origin
    ):
        raise TypeError("NumPy version and origin must be nonempty built-in strings")
    return (
        platform.python_implementation(),
        platform.python_version(),
        numpy_version,
        platform.platform(),
        sys.byteorder,
        sys.executable,
        sys.prefix,
        str(Path(numpy_origin).absolute()),
        str(Path.cwd()),
    )


def _terminate_and_reap(process: object) -> int | None:
    if process.is_alive():
        process.terminate()
        process.join(10.0)
    if process.is_alive():
        process.kill()
        process.join(10.0)
    if process.is_alive():
        raise RuntimeError("measurement child remained alive after SIGKILL")
    return process.exitcode


def _lookup_static_receipt_for_measurement(authority: Any) -> Any:
    from metroflow.city import scalable_authority as authority_module
    from metroflow.city.scalable_validation_receipts import (
        _BLOCKS_SEAL_SCHEMA,
        _COMPILED_AGGREGATE_SEAL_SCHEMA,
        _NETWORK_SEAL_SCHEMA,
        _STATIC_CONTENT_SEAL_SCHEMAS,
        _TASK5_INVOCATION_SEAL_SCHEMA,
        _lookup_validation_receipt,
    )

    return _lookup_validation_receipt(
        "static",
        authority.schema_version,
        authority.fingerprint,
        expected_policy_versions=authority_module.static_receipt_policy_versions(),
        expected_source_seal_schemas=(
            ("blocks.current", _BLOCKS_SEAL_SCHEMA),
            ("compiled.aggregate", _COMPILED_AGGREGATE_SEAL_SCHEMA),
            ("invocation.current", _TASK5_INVOCATION_SEAL_SCHEMA),
            ("network.current", _NETWORK_SEAL_SCHEMA),
        ),
        expected_content_seal_schemas=_STATIC_CONTENT_SEAL_SCHEMAS,
    )


def _measurement_child(
    control_socket: socket.socket,
    nonce: str,
    target_population: int,
    urbanized_area_km2: int,
    style_id: str,
    seed: int,
) -> None:
    channel = _LineChannel(control_socket, nonce)
    clear_receipts = None
    try:
        import numpy as np
        from metroflow.city import scalable_validation_receipts as receipt_module
        from metroflow.city.scale import CityScaleSpec
        from metroflow.city.scalable_authority import (
            _capture_stable_static_validation_receipt,
            _capture_verified_task5_source_snapshot_from_receipt,
            build_scalable_static_authority,
        )
        from metroflow.city.scalable_blocks import build_scalable_block_authority
        from metroflow.city.scalable_topology import build_scalable_street_network
        from metroflow.city.scalable_topology_adapter import (
            _TURN_POLICY,
            _require_scalable_source_cross_binding,
            compile_scalable_topology,
        )
        from metroflow.city.scalable_validation_receipts import (
            _ValidationReceipt,
            _VerifiedTask5SourceSnapshot,
            _clear_validation_receipts_for_test,
            _lookup_validation_receipt,
            _register_validation_receipt,
        )

        clear_receipts = _clear_validation_receipts_for_test
        expected_receipt_literals = {
            "_NETWORK_SEAL_SCHEMA": _NETWORK_SEAL_SCHEMA,
            "_BLOCKS_SEAL_SCHEMA": _BLOCKS_SEAL_SCHEMA,
            "_COMPILED_SEAL_SCHEMA": _COMPILED_SEAL_SCHEMA,
            "_COMPILED_AGGREGATE_SEAL_SCHEMA": _COMPILED_AGGREGATE_SEAL_SCHEMA,
            "_STATIC_SEAL_SCHEMA": _STATIC_SEAL_SCHEMA,
            "_TASK5_INVOCATION_SEAL_SCHEMA": _TASK5_INVOCATION_SEAL_SCHEMA,
            "_TASK5_NETWORK_PROJECTION_SCHEMA": _TASK5_NETWORK_PROJECTION_SCHEMA,
            "_TASK5_BLOCKS_PROJECTION_SCHEMA": _TASK5_BLOCKS_PROJECTION_SCHEMA,
            "_TASK5_COMPILED_PROJECTION_SCHEMA": _TASK5_COMPILED_PROJECTION_SCHEMA,
            "_NETWORK_RECEIPT_POLICY_VERSION": _NETWORK_RECEIPT_POLICY_VERSION,
            "_BLOCKS_RECEIPT_POLICY_VERSION": _BLOCKS_RECEIPT_POLICY_VERSION,
            "_COMPILED_RECEIPT_POLICY_VERSION": _COMPILED_RECEIPT_POLICY_VERSION,
            "_STATIC_RECEIPT_POLICY_VERSION": _STATIC_RECEIPT_POLICY_VERSION,
            "_TASK5_SNAPSHOT_POLICY_VERSION": _TASK5_SNAPSHOT_POLICY_VERSION,
        }
        for name, expected in expected_receipt_literals.items():
            if getattr(receipt_module, name) != expected:
                raise RuntimeError(f"receipt literal mismatch: {name}")
        if not callable(_require_scalable_source_cross_binding):
            raise TypeError("source cross-binding seam is not callable")

        scale_spec = CityScaleSpec(target_population, float(urbanized_area_km2))
        network = build_scalable_street_network(scale_spec, style_id, seed)
        blocks = build_scalable_block_authority(network)
        compiled = compile_scalable_topology(
            network,
            block_authority=blocks,
        )
        authority = build_scalable_static_authority(
            scale_spec,
            style_id,
            seed,
            network,
            blocks,
            compiled,
        )

        network_receipt = _lookup_validation_receipt(
            "network",
            network.schema_version,
            network.fingerprint,
            expected_policy_versions=(("receipt_policy", _NETWORK_RECEIPT_POLICY_VERSION),),
            expected_source_seal_schemas=(),
            expected_content_seal_schemas=(("network.current", _NETWORK_SEAL_SCHEMA),),
        )
        blocks_receipt = _lookup_validation_receipt(
            "blocks",
            blocks.schema_version,
            blocks.fingerprint,
            expected_policy_versions=(
                ("embedding_policy", blocks.embedding_policy),
                ("receipt_policy", _BLOCKS_RECEIPT_POLICY_VERSION),
                ("subdivision_schema", blocks.subdivision_schema),
                ("tile_policy", blocks.tile_policy),
            ),
            expected_source_seal_schemas=(),
            expected_content_seal_schemas=(("blocks.current", _BLOCKS_SEAL_SCHEMA),),
        )
        compiled_receipt = _lookup_validation_receipt(
            "compiled",
            compiled.schema_version,
            compiled.fingerprint,
            expected_policy_versions=(
                (
                    "numeric_profile_policy",
                    compiled.numeric_profile_policy_version,
                ),
                ("receipt_policy", _COMPILED_RECEIPT_POLICY_VERSION),
                ("turn_policy", _TURN_POLICY),
            ),
            expected_source_seal_schemas=(
                ("blocks.current", _BLOCKS_SEAL_SCHEMA),
                ("network.current", _NETWORK_SEAL_SCHEMA),
            ),
            expected_content_seal_schemas=_COMPILED_CONTENT_SEAL_SCHEMAS,
        )
        static_receipt = _lookup_static_receipt_for_measurement(authority)
        setup_receipts = (
            network_receipt,
            blocks_receipt,
            compiled_receipt,
            static_receipt,
        )
        if any(type(receipt) is not _ValidationReceipt for receipt in setup_receipts):
            raise RuntimeError("setup lookup did not return four exact receipts")
        saved_receipts = copy.deepcopy(setup_receipts)
        if any(type(receipt) is not _ValidationReceipt for receipt in saved_receipts):
            raise RuntimeError("copied setup receipt has an unexpected type")
        if saved_receipts != setup_receipts:
            raise RuntimeError("copied setup receipt changed value")
        fingerprints = (
            ("network", network.fingerprint),
            ("blocks", blocks.fingerprint),
            ("compiled", compiled.fingerprint),
            ("static", authority.fingerprint),
        )
        receipt_values = tuple(_plain_receipt_value(value) for value in saved_receipts)
        environment = _child_environment(np.__version__, np.__file__)
        network_receipt = None
        blocks_receipt = None
        compiled_receipt = None
        static_receipt = None
        setup_receipts = None
        _clear_validation_receipts_for_test()
        channel.send(
            "READY",
            fingerprints=fingerprints,
            receipt_values=receipt_values,
            environment=environment,
        )
        receipt_values = None
        fingerprints = None
        environment = None
        for _ in range(3):
            gc.collect()
        channel.send("BASELINE_READY")
        start_message = channel.receive(_READY_TIMEOUT_SECONDS)
        if start_message["event"] != "START":
            raise RuntimeError("child expected exactly one START event")

        saved_network, saved_blocks, saved_compiled, saved_static = saved_receipts
        (
            source_snapshot,
            current_network_receipt,
            current_blocks_receipt,
            current_compiled_receipt,
        ) = _capture_verified_task5_source_snapshot_from_receipt(
            scale_spec,
            style_id,
            seed,
            network,
            blocks,
            compiled,
            registered_compiled_receipt=saved_compiled,
        )
        if type(source_snapshot) is not _VerifiedTask5SourceSnapshot:
            raise TypeError("source capture did not return the exact snapshot type")
        current_receipts = (
            current_network_receipt,
            current_blocks_receipt,
            current_compiled_receipt,
        )
        if any(type(receipt) is not _ValidationReceipt for receipt in current_receipts):
            raise TypeError("source capture did not return exact receipt types")
        if current_receipts != (saved_network, saved_blocks, saved_compiled):
            raise RuntimeError("source capture receipt differs from setup receipt")
        for receipt in current_receipts:
            _register_validation_receipt(receipt)
        current_static_receipt = _capture_stable_static_validation_receipt(
            authority,
            source_snapshot=source_snapshot,
            compiled=compiled,
        )
        if type(current_static_receipt) is not _ValidationReceipt:
            raise TypeError("static capture did not return an exact receipt")
        if current_static_receipt != saved_static:
            raise RuntimeError("static capture receipt differs from setup receipt")
        _register_validation_receipt(current_static_receipt)
        _clear_validation_receipts_for_test()

        source_snapshot = None
        current_receipts = None
        current_network_receipt = None
        current_blocks_receipt = None
        current_compiled_receipt = None
        current_static_receipt = None
        receipt = None
        network_receipt = None
        blocks_receipt = None
        compiled_receipt = None
        static_receipt = None
        setup_receipts = None
        saved_receipts = None
        saved_network = None
        saved_blocks = None
        saved_compiled = None
        saved_static = None
        receipt_values = None
        fingerprints = None
        environment = None
        expected_receipt_literals = None
        for _ in range(3):
            gc.collect()
        channel.send(
            "END",
            inclusive_ru_maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        )
        acknowledgement = channel.receive(30.0)
        if acknowledgement["event"] != "ACK":
            raise RuntimeError("child expected exactly one ACK event")
    except BaseException as exc:
        if clear_receipts is not None:
            try:
                clear_receipts()
            except Exception:
                pass
        try:
            channel.send(
                "ERROR",
                error=f"{type(exc).__name__}: {exc}",
                traceback="".join(traceback.format_exception(exc))[-16_384:],
            )
        except Exception:
            pass
        raise
    finally:
        control_socket.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Measure the frozen no-output Task 4/5 validation workload in two fresh children."
        ),
        allow_abbrev=False,
    )
    parser.add_argument("--mode", choices=("isolated-rss",), required=True)
    parser.add_argument("--target-population", type=int, required=True)
    parser.add_argument("--urbanized-area-km2", type=int, required=True)
    parser.add_argument("--style-id", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--replicates", type=int, required=True)
    parser.add_argument("--output", required=True)
    return parser


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    if arguments in (("-h",), ("--help",)):
        return parser.parse_args(arguments)
    if arguments != _EXACT_ARGUMENTS:
        parser.error("arguments must exactly match the frozen isolated-rss command")
    return parser.parse_args(arguments)


def _read_vmrss_kib(child_pid: int) -> int:
    status_path = Path("/proc") / str(child_pid) / "status"
    try:
        with status_path.open("r", encoding="ascii") as handle:
            matches = [line for line in handle if line.startswith("VmRSS:")]
    except OSError as exc:
        raise RuntimeError("unable to read child VmRSS") from exc
    if len(matches) != 1:
        raise RuntimeError("child status does not contain exactly one VmRSS row")
    fields_value = matches[0].split()
    if len(fields_value) != 3 or fields_value[0] != "VmRSS:" or fields_value[2] != "kB":
        raise RuntimeError("child VmRSS row is malformed")
    try:
        value = int(fields_value[1])
    except ValueError as exc:
        raise RuntimeError("child VmRSS value is not an integer") from exc
    if value <= 0:
        raise RuntimeError("child VmRSS value must be positive")
    return value


def _require_event(message: dict[str, object], expected_event: str) -> None:
    if message["event"] == "ERROR":
        raise RuntimeError(f"measurement child error: {message.get('error', 'unspecified error')}")
    if message["event"] != expected_event:
        raise RuntimeError(
            f"unexpected control event: expected {expected_event}, received {message['event']}"
        )


def _run_replicate(
    replicate: int,
    *,
    target_population: int,
    urbanized_area_km2: int,
    style_id: str,
    seed: int,
) -> _ReplicateResult:
    nonce = secrets.token_hex(32)
    parent_socket, child_socket = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    context = multiprocessing.get_context("spawn")
    process = context.Process(
        target=_measurement_child,
        args=(
            child_socket,
            nonce,
            target_population,
            urbanized_area_km2,
            style_id,
            seed,
        ),
        name=f"task45-isolated-rss-{replicate}",
    )
    raw_samples: list[tuple[int, str, int]] = []
    child_pid = 0
    fingerprints: object | None = None
    receipt_values: object | None = None
    environment: object | None = None
    child_exit_code: int | None = None
    try:
        process.start()
        child_pid = process.pid or 0
        child_socket.close()
        if child_pid <= 0:
            raise RuntimeError("measurement child did not expose a PID")
        channel = _LineChannel(parent_socket, nonce)
        ready = channel.receive(_READY_TIMEOUT_SECONDS)
        _require_event(ready, "READY")
        fingerprints = ready.get("fingerprints")
        receipt_values = ready.get("receipt_values")
        environment = ready.get("environment")
        if type(fingerprints) is not list or len(fingerprints) != 4:
            raise RuntimeError("READY public fingerprints are malformed")
        if type(receipt_values) is not list or len(receipt_values) != 4:
            raise RuntimeError("READY receipt values are malformed")
        if (
            type(environment) is not list
            or len(environment) != 9
            or any(type(item) is not str or not item for item in environment)
            or environment[0] != platform.python_implementation()
            or environment[1] != platform.python_version()
            or environment[3] != platform.platform()
            or environment[4] != sys.byteorder
            or environment[5] != sys.executable
            or environment[6] != sys.prefix
            or not Path(environment[7]).is_relative_to(_REPOSITORY_ROOT / ".venv")
            or environment[8] != str(Path.cwd())
        ):
            raise RuntimeError("READY child environment is malformed")
        baseline_ready = channel.receive(_READY_TIMEOUT_SECONDS)
        _require_event(baseline_ready, "BASELINE_READY")

        stability_deadline = time.monotonic_ns() + _STABILITY_TIMEOUT_NS
        stability_window: list[int] = []
        next_sample_ns = time.monotonic_ns()
        while True:
            delay_ns = next_sample_ns - time.monotonic_ns()
            if delay_ns > 0:
                time.sleep(delay_ns / 1_000_000_000)
            timestamp_ns = time.monotonic_ns()
            vmrss_kib = _read_vmrss_kib(child_pid)
            if raw_samples:
                gap_ns = timestamp_ns - raw_samples[-1][0]
                if gap_ns > _MAX_SAMPLE_INTERVAL_NS:
                    raise RuntimeError(f"VmRSS sampling gap exceeded 5 ms: {gap_ns} ns")
            raw_samples.append((timestamp_ns, "stabilize", vmrss_kib))
            stability_window.append(vmrss_kib)
            if len(stability_window) > _STABILITY_SAMPLE_COUNT:
                del stability_window[0]
            message = channel.poll()
            if message is not None:
                _require_event(message, "NO_EVENT_EXPECTED")
            if (
                len(stability_window) == _STABILITY_SAMPLE_COUNT
                and max(stability_window) - min(stability_window) <= _STABILITY_SPAN_KIB
            ):
                break
            if timestamp_ns >= stability_deadline:
                raise RuntimeError("VmRSS did not stabilize within 10 seconds")
            next_sample_ns = timestamp_ns + _SAMPLE_INTERVAL_NS

        baseline_kib = float(statistics.median(stability_window))
        start_marker_ns = time.monotonic_ns()
        channel.send("START")
        end_message: dict[str, object] | None = None
        workload_deadline = start_marker_ns + _WORKLOAD_TIMEOUT_NS
        next_sample_ns = start_marker_ns
        while end_message is None:
            delay_ns = next_sample_ns - time.monotonic_ns()
            if delay_ns > 0:
                time.sleep(delay_ns / 1_000_000_000)
            timestamp_ns = time.monotonic_ns()
            vmrss_kib = _read_vmrss_kib(child_pid)
            gap_ns = timestamp_ns - raw_samples[-1][0]
            if gap_ns > _MAX_SAMPLE_INTERVAL_NS:
                raise RuntimeError(f"VmRSS sampling gap exceeded 5 ms: {gap_ns} ns")
            raw_samples.append((timestamp_ns, "measured", vmrss_kib))
            message = channel.poll()
            if message is not None:
                _require_event(message, "END")
                end_message = message
                break
            if timestamp_ns >= workload_deadline:
                raise RuntimeError("isolated workload exceeded 900 seconds")
            next_sample_ns = timestamp_ns + _SAMPLE_INTERVAL_NS

        post_timestamp_ns = time.monotonic_ns()
        post_vmrss_kib = _read_vmrss_kib(child_pid)
        post_gap_ns = post_timestamp_ns - raw_samples[-1][0]
        if post_gap_ns > _MAX_SAMPLE_INTERVAL_NS:
            raise RuntimeError(f"post-END sampling gap exceeded 5 ms: {post_gap_ns} ns")
        raw_samples.append((post_timestamp_ns, "post_end", post_vmrss_kib))
        channel.send("ACK")
        process.join(30.0)
        if process.is_alive():
            raise RuntimeError("measurement child did not exit after ACK")
        child_exit_code = process.exitcode
        if process.exitcode != 0:
            raise RuntimeError(f"measurement child exit code was {process.exitcode}")
        inclusive_ru_maxrss_kib = end_message.get("inclusive_ru_maxrss_kib")
        if type(inclusive_ru_maxrss_kib) is not int or inclusive_ru_maxrss_kib <= 0:
            raise RuntimeError("END ru_maxrss value is malformed")
        measured_values = [
            vmrss_kib
            for timestamp_ns, phase, vmrss_kib in raw_samples
            if timestamp_ns >= start_marker_ns and phase in {"measured", "post_end"}
        ]
        if not measured_values:
            raise RuntimeError("measured VmRSS series is empty")
        peak_kib = max(measured_values)
        delta_kib = max(0.0, peak_kib - baseline_kib)
        gaps = [current[0] - previous[0] for previous, current in zip(raw_samples, raw_samples[1:])]
        maximum_gap_ns = max(gaps, default=0)
        return _ReplicateResult(
            replicate=replicate,
            child_pid=child_pid,
            status="MEASURED",
            error=None,
            baseline_kib=baseline_kib,
            peak_kib=peak_kib,
            delta_kib=delta_kib,
            maximum_sample_gap_ns=maximum_gap_ns,
            inclusive_ru_maxrss_kib=inclusive_ru_maxrss_kib,
            fingerprints=fingerprints,
            receipt_values=receipt_values,
            environment=environment,
            child_exit_code=child_exit_code,
            raw_samples=tuple(raw_samples),
        )
    except BaseException as exc:
        child_exit_code = _terminate_and_reap(process)
        if not isinstance(exc, Exception):
            raise
        gaps = [current[0] - previous[0] for previous, current in zip(raw_samples, raw_samples[1:])]
        return _ReplicateResult(
            replicate=replicate,
            child_pid=child_pid,
            status="PROTOCOL_FAIL",
            error=f"{type(exc).__name__}: {exc}",
            baseline_kib=None,
            peak_kib=None,
            delta_kib=None,
            maximum_sample_gap_ns=max(gaps, default=None),
            inclusive_ru_maxrss_kib=None,
            fingerprints=fingerprints,
            receipt_values=receipt_values,
            environment=environment,
            child_exit_code=child_exit_code,
            raw_samples=tuple(raw_samples),
        )
    finally:
        parent_socket.close()
        child_socket.close()


def _receipt_values_sha256(value: object | None) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _append_report(
    report_path: Path,
    *,
    results: Sequence[_ReplicateResult],
    disposition: str,
    tolerance_kib: int | None,
) -> None:
    if report_path.is_symlink():
        raise RuntimeError("performance report path must not be a symlink")
    if report_path.exists() and not stat.S_ISREG(report_path.lstat().st_mode):
        raise RuntimeError("performance report path must be a regular file")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "",
        "## Isolated current-content RSS measurement",
        "",
        f"- recorded_utc: `{datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}`",
        f"- controller_sha256: `{hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}`",
        f"- command: `{' '.join(_EXACT_COMMAND)}`",
        f"- disposition: **{disposition}**",
        f"- raw_delta_limit_kib: `{_RSS_LIMIT_KIB}`",
        f"- repeatability_tolerance_kib: `{tolerance_kib}`",
        "- boundary: isolated baseline-subtracted validation/capture workload; not inclusive G5 RSS",
        "",
    ]
    for result in results:
        lines.extend(
            (
                f"### Replicate {result.replicate}",
                "",
                f"- child_pid: `{result.child_pid}`",
                f"- status: `{result.status}`",
                f"- error: `{result.error}`",
                f"- baseline_kib: `{result.baseline_kib}`",
                f"- peak_kib: `{result.peak_kib}`",
                f"- delta_kib: `{result.delta_kib}`",
                f"- maximum_sample_gap_ns: `{result.maximum_sample_gap_ns}`",
                f"- inclusive_child_ru_maxrss_kib_diagnostic: `{result.inclusive_ru_maxrss_kib}`",
                f"- public_fingerprints: `{json.dumps(result.fingerprints, separators=(',', ':'))}`",
                f"- copied_receipt_values_sha256: `{_receipt_values_sha256(result.receipt_values)}`",
                f"- child_environment: `{json.dumps(result.environment, separators=(',', ':'))}`",
                f"- final_child_exit_code: `{result.child_exit_code}`",
                "",
                "```text",
                "monotonic_ns,phase,vmrss_kib",
            )
        )
        lines.extend(
            f"{timestamp_ns},{phase},{vmrss_kib}"
            for timestamp_ns, phase, vmrss_kib in result.raw_samples
        )
        lines.extend(("```", ""))
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    with report_path.open("ab") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _run_isolated_rss(namespace: argparse.Namespace) -> int:
    _require_exact_launcher(
        executable=str(Path(sys.executable).absolute()),
        script_path=str(Path(sys.argv[0]).absolute()),
        cwd=str(Path.cwd()),
    )
    imported = tuple(
        name
        for name in sys.modules
        if name == "numpy"
        or name.startswith("numpy.")
        or name == "metroflow"
        or name.startswith("metroflow.")
    )
    if imported:
        raise RuntimeError(
            "controller imported NumPy or MetroFlow before child creation: " + ", ".join(imported)
        )
    results: list[_ReplicateResult] = []
    for replicate in range(1, namespace.replicates + 1):
        result = _run_replicate(
            replicate,
            target_population=namespace.target_population,
            urbanized_area_km2=namespace.urbanized_area_km2,
            style_id=namespace.style_id,
            seed=namespace.seed,
        )
        results.append(result)
        if result.status != "MEASURED":
            _append_report(
                _REPOSITORY_ROOT / namespace.output,
                results=results,
                disposition="CHILD_OR_PROTOCOL_FAIL_EXIT_3",
                tolerance_kib=None,
            )
            return 3

    first, second = results
    if (
        first.fingerprints != second.fingerprints
        or first.receipt_values != second.receipt_values
        or first.environment != second.environment
    ):
        _append_report(
            _REPOSITORY_ROOT / namespace.output,
            results=results,
            disposition="REPLICATE_SETUP_MISMATCH_EXIT_3",
            tolerance_kib=None,
        )
        return 3
    if first.delta_kib is None or second.delta_kib is None:
        raise RuntimeError("measured replicate is missing its RSS delta")
    largest_delta = max(first.delta_kib, second.delta_kib)
    tolerance_kib = max(4096, math.ceil(0.10 * largest_delta))
    limit_pass = all(
        result.delta_kib is not None and result.delta_kib <= _RSS_LIMIT_KIB for result in results
    )
    repeatability_pass = abs(first.delta_kib - second.delta_kib) <= tolerance_kib
    if not limit_pass or not repeatability_pass:
        _append_report(
            _REPOSITORY_ROOT / namespace.output,
            results=results,
            disposition="RSS_LIMIT_OR_REPEATABILITY_FAIL_EXIT_4",
            tolerance_kib=tolerance_kib,
        )
        return 4
    _append_report(
        _REPOSITORY_ROOT / namespace.output,
        results=results,
        disposition="ISOLATED_RSS_PASS_EXIT_0",
        tolerance_kib=tolerance_kib,
    )
    print(
        "isolated_rss=PASS "
        f"delta_kib=({first.delta_kib},{second.delta_kib}) "
        f"tolerance_kib={tolerance_kib}"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    namespace = _parse_args(argv)
    try:
        return _run_isolated_rss(namespace)
    except Exception as exc:
        print(f"controller_error={type(exc).__name__}: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
