from __future__ import annotations

from enum import Enum
from fractions import Fraction
import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from metroflow.city import scalable_authority as static_module
from metroflow.city import scalable_topology_adapter as adapter
from metroflow.city.graph import (
    BridgeCrossing,
    Node,
    NodeKind,
    RoadClass,
    RoadLink,
)
from metroflow.city.scale import CityScaleSpec
from metroflow.city.scalable_blocks import (
    V2BlockAccessIndex,
    build_scalable_block_authority,
)
from metroflow.city.scalable_topology import (
    FacilityKind,
    RoadHierarchy,
    build_scalable_street_network,
)


_SERIALIZER_SCHEMA = "scalable_task45_output_payload_v1"
_REVIEWED_ENUM_TYPES = (RoadClass, NodeKind, FacilityKind, RoadHierarchy)
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


def _reference_normalize(value: object) -> object:
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is float:
        if not np.isfinite(value):
            raise ValueError("reference float must be finite")
        return ("float_hex", value.hex())
    if type(value) is Fraction:
        return ("fraction", value.numerator, value.denominator)
    if type(value) in _REVIEWED_ENUM_TYPES:
        enum_value = value.value
        if type(enum_value) is not str:
            raise TypeError("reviewed enum values must be exact strings")
        return enum_value
    if type(value) is tuple:
        return tuple(_reference_normalize(item) for item in value)
    raise TypeError(f"unsupported reference value: {type(value).__name__}")


def _reference_bytes(value: object) -> bytes:
    return json.dumps(
        _reference_normalize(value),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _reference_array_sidecars(csr: object) -> tuple[tuple[str, int, str], ...]:
    counts = {
        "nodes": len(csr.nodes),
        "node_indptr": len(csr.nodes) + 1,
        "links": len(csr.links),
        "turns": len(csr.turns),
    }
    rows: list[tuple[str, int, str]] = []
    for name, expected_dtype, count_name in _ARRAY_CONTRACTS:
        value = getattr(csr, name)
        assert type(value) is np.ndarray
        assert value.dtype == expected_dtype
        assert value.shape == (counts[count_name],)
        assert value.flags.c_contiguous
        materialized = value.tobytes(order="C")
        rows.append((name, value.nbytes, hashlib.sha256(materialized).hexdigest()))
    return tuple(rows)


def _reference_mapping_digest(csr: object) -> str:
    payload = (
        tuple(sorted(csr.node_id_to_index.items())),
        tuple(sorted(csr.link_id_to_index.items())),
        tuple(sorted(csr.turn_pair_to_index.items())),
        csr.topology_cache_key,
    )
    return hashlib.sha256(_reference_bytes(payload)).hexdigest()


def _handbuilt_rows() -> tuple[object, object, object]:
    profile = adapter.ScalableNumericProfile(
        profile_id="vector:profile",
        lanes_per_direction=2,
        free_flow_speed_mps=13.25,
        capacity_veh_per_second=1.75,
        operational_road_class=RoadClass.ARTERIAL,
        section_roadside_profile="urban",
        median_when_bidirectional=True,
    )
    road = adapter.ScalableRoadCrosswalk(
        physical_road_id=7,
        road_semantic_id="a" * 64,
        hierarchy=RoadHierarchy.ARTERIAL,
        facility=FacilityKind.SURFACE,
        profile_id="vector:profile",
        layer=0,
        layer_transition=None,
        access_directions=("forward", "reverse"),
        provenance="vector",
        geometry_id=11,
        centerline_source_ref="vector:7",
        forward_link_id=14,
        reverse_link_id=15,
        structure_group=None,
        structure_group_id=None,
        failure_group="vector:failure",
        bridge_group_id=None,
    )
    group = adapter.ScalableGroupCrosswalk(
        semantic_group="vector:failure",
        dense_group_id=3,
        member_physical_road_ids=(7,),
    )
    return profile, road, group


def test_handbuilt_payload_vectors_cover_enum_float_and_fraction_grammar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile, road, group = _handbuilt_rows()
    node = Node(
        node_id=2,
        kind=NodeKind.INTERSECTION,
        x=1.25,
        y=-0.0,
        zone_id=None,
        signal_group_id=5,
    )
    link = RoadLink(
        link_id=14,
        src_node_id=2,
        dst_node_id=3,
        road_class=RoadClass.ARTERIAL,
        length_m=Fraction(401, 2),
        free_flow_speed_mps=13.25,
        capacity_veh_per_tick=Fraction(7, 4),
        lanes=2,
        physical_road_id=7,
    )
    bridge = BridgeCrossing(
        bridge_group_id=4,
        link_ids=(14,),
        barrier_id=8,
        crossing_name="vector crossing",
        bottleneck_rank_hint=None,
    )
    task4_fixture = SimpleNamespace(
        schema_version="compiled-vector-v1",
        numeric_profile_policy_version="numeric-vector-v1",
        source_network_fingerprint="1" * 64,
        source_block_authority_fingerprint="2" * 64,
        terrain_fingerprint="3" * 64,
        scale_fingerprint="4" * 64,
        style_fingerprint="5" * 64,
        numeric_profiles=(profile,),
        road_crosswalk=(road,),
        structure_group_crosswalk=(group,),
        failure_group_crosswalk=(group,),
        topology=SimpleNamespace(
            nodes=(node,),
            links=(link,),
            bridge_crossings=(bridge,),
            road_geometry=SimpleNamespace(assignments=(object(), object())),
            node_interfaces=SimpleNamespace(interfaces=(object(),)),
        ),
        road_geometry_fingerprint="6" * 64,
        road_section_fingerprint="7" * 64,
        node_interface_fingerprint="8" * 64,
        turn_authority_fingerprint="9" * 64,
        source_node_count=1,
        source_physical_road_count=1,
        source_block_count=1,
        compiled_node_count=1,
        compiled_link_count=1,
        compiled_turn_count=0,
        permitted_turn_count=0,
        forbidden_u_turn_count=0,
        bridge_crossing_count=1,
        metadata_items=(("exact_ratio", Fraction(3, 7)), ("signed_zero", -0.0)),
    )
    expected_task4_payload = adapter._compiled_fingerprint_payload(task4_fixture)

    access = V2BlockAccessIndex(
        block_to_road_ids=((0, (7,)),),
        block_to_node_ids=((0, (2,)),),
        road_to_block_ids=((7, (0,)),),
        node_to_block_ids=((2, (0,)),),
        primary_access_by_block=((0, 2),),
        incidence_visit_count=4,
    )
    fingerprints = SimpleNamespace(
        schema_version="fingerprints-vector-v1",
        config="a" * 64,
        geometry="b" * 64,
        topology="c" * 64,
        link_attributes="d" * 64,
        turn_authority="e" * 64,
        blocks_access="f" * 64,
        land_use_zoning="0" * 64,
        routing_static="1" * 64,
        accessibility_static="2" * 64,
        replay_static="3" * 64,
        composite="4" * 64,
    )
    task5_fixture = SimpleNamespace(
        schema_version="static-vector-v1",
        scale_spec=SimpleNamespace(
            target_population=100_000,
            urbanized_area_km2=25.0,
        ),
        style_id="grid_core",
        seed=17,
        extent_mm=(-1, -2, 3, 4),
        width_m=4.25,
        height_m=6.5,
        centers_mm=((Fraction(1, 3), 2),),
        source_network_schema_version="network-vector-v1",
        source_blocks_schema_version="blocks-vector-v1",
        source_compiled_schema_version="compiled-vector-v1",
        numeric_profile_policy_version="numeric-vector-v1",
        source_network_fingerprint="1" * 64,
        source_blocks_fingerprint="2" * 64,
        source_compiled_fingerprint="3" * 64,
        source_terrain_fingerprint="4" * 64,
        source_scale_fingerprint="5" * 64,
        source_style_fingerprint="6" * 64,
        source_geometry_fingerprint="7" * 64,
        source_section_fingerprint="8" * 64,
        source_node_interface_fingerprint="9" * 64,
        source_turn_authority_fingerprint="a" * 64,
        numeric_profiles=(profile,),
        road_crosswalk=(road,),
        structure_group_crosswalk=(group,),
        failure_group_crosswalk=(group,),
        block_access_index=access,
        block_land_use=(SimpleNamespace(fingerprint="b" * 64),),
        capacity_certificate=SimpleNamespace(fingerprint="c" * 64),
        taz_catalog=SimpleNamespace(fingerprint="d" * 64),
        poi_catalog=SimpleNamespace(fingerprint="e" * 64),
        fingerprints=fingerprints,
        road_csr=SimpleNamespace(content_fingerprint="f" * 64),
        routing_dependency_key=SimpleNamespace(fingerprint="0" * 64),
    )
    expected_task5_payload = static_module._static_authority_payload(task5_fixture)

    def _reject_private_payload_delegation(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("oracle producer delegated to a private payload helper")

    monkeypatch.setattr(
        adapter,
        "_compiled_fingerprint_payload",
        _reject_private_payload_delegation,
    )
    monkeypatch.setattr(
        static_module,
        "_static_authority_payload",
        _reject_private_payload_delegation,
    )
    sys.modules.pop("tools.build_task45_preoptimization_oracle", None)
    oracle = importlib.import_module("tools.build_task45_preoptimization_oracle")

    assert oracle.task4_output_payload(task4_fixture) == expected_task4_payload
    assert oracle.task5_output_payload(task5_fixture) == expected_task5_payload

    grammar_vector = (
        RoadClass.ARTERIAL,
        1.25,
        Fraction(-3, 7),
        ("plain", True, None),
    )
    assert oracle.materialized_canonical_bytes(grammar_vector) == (
        b'["arterial",["float_hex","0x1.4000000000000p+0"],["fraction",-3,7],["plain",true,null]]'
    )
    unrelated_string_enum = Enum("UnrelatedStringEnum", {"VALUE": "value"}).VALUE
    unrelated_integer_enum = Enum("UnrelatedIntegerEnum", {"VALUE": 1}).VALUE
    for unsupported_enum in (unrelated_string_enum, unrelated_integer_enum):
        with pytest.raises(TypeError, match="unsupported canonical value"):
            oracle.materialized_canonical_bytes(unsupported_enum)
        with pytest.raises(TypeError, match="unsupported reference value"):
            _reference_bytes(unsupported_enum)
    for task_name, payload in (
        ("task4", oracle.task4_output_payload(task4_fixture)),
        ("task5", oracle.task5_output_payload(task5_fixture)),
    ):
        expected = _reference_bytes((_SERIALIZER_SCHEMA, task_name, payload))
        assert oracle.output_payload_bytes(task_name, payload) == expected
        assert oracle.output_payload_receipt(task_name, payload) == (
            len(expected),
            hashlib.sha256(expected).hexdigest(),
        )


def test_real_100k_payload_and_sidecar_vectors_match_independent_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scale = CityScaleSpec(100_000, 25.0)
    network = build_scalable_street_network(scale, "grid_core", 17)
    blocks = build_scalable_block_authority(network)
    compiled = adapter.compile_scalable_topology(network, block_authority=blocks)
    static = static_module.build_scalable_static_authority(
        scale,
        "grid_core",
        17,
        network,
        blocks,
        compiled,
    )

    expected_task4_payload = adapter._compiled_fingerprint_payload(compiled)
    expected_task5_payload = static_module._static_authority_payload(static)

    def _reject_private_payload_delegation(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("oracle producer delegated to a private payload helper")

    monkeypatch.setattr(
        adapter,
        "_compiled_fingerprint_payload",
        _reject_private_payload_delegation,
    )
    monkeypatch.setattr(
        static_module,
        "_static_authority_payload",
        _reject_private_payload_delegation,
    )
    sys.modules.pop("tools.build_task45_preoptimization_oracle", None)
    oracle = importlib.import_module("tools.build_task45_preoptimization_oracle")

    task4_payload = oracle.task4_output_payload(compiled)
    task5_payload = oracle.task5_output_payload(static)
    assert task4_payload == expected_task4_payload
    assert task5_payload == expected_task5_payload

    for task_name, payload in (("task4", task4_payload), ("task5", task5_payload)):
        expected = _reference_bytes((_SERIALIZER_SCHEMA, task_name, payload))
        assert oracle.output_payload_bytes(task_name, payload) == expected
        assert oracle.output_payload_receipt(task_name, payload) == (
            len(expected),
            hashlib.sha256(expected).hexdigest(),
        )

    assert oracle.array_sidecars(compiled.road_csr) == _reference_array_sidecars(compiled.road_csr)
    assert oracle.array_sidecars(static.road_csr) == _reference_array_sidecars(static.road_csr)
    assert oracle.mapping_rows_sha256(compiled.road_csr) == _reference_mapping_digest(
        compiled.road_csr
    )
    assert oracle.mapping_rows_sha256(static.road_csr) == _reference_mapping_digest(static.road_csr)
    assert (
        oracle.metadata_items_sha256(compiled.metadata_items)
        == hashlib.sha256(_reference_bytes(compiled.metadata_items)).hexdigest()
    )


def test_oracle_census_rejects_symlinked_package_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    oracle = importlib.import_module("tools.build_task45_preoptimization_oracle")
    source_root = tmp_path / "src" / "metroflow"
    source_root.mkdir(parents=True)
    (source_root / "visible.py").write_text("VALUE = 1\n", encoding="utf-8")
    external = tmp_path / "external_package"
    external.mkdir()
    (external / "hidden.py").write_text("VALUE = 2\n", encoding="utf-8")
    (source_root / "linked_package").symlink_to(
        external,
        target_is_directory=True,
    )
    monkeypatch.setattr(oracle, "_REPOSITORY_ROOT", tmp_path)

    with pytest.raises(
        oracle._OracleFailure,
        match="directory.*symlink|symlink.*directory",
    ) as captured:
        oracle._immutable_production_census(exit_code=4)
    assert captured.value.exit_code == 4


def test_oracle_rejects_unauthorized_nonself_provenance_before_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    oracle = importlib.import_module("tools.build_task45_preoptimization_oracle")
    original_digest = oracle._regular_file_digest
    reviewed_path = next(
        path
        for path in oracle._IMMUTABLE_PROVENANCE_PATHS
        if path.endswith("brief-rebind-independent-review.md")
    )

    def _drifted_digest(relative_path: str, *, exit_code: int) -> str:
        if relative_path == reviewed_path:
            return "0" * 64
        return original_digest(relative_path, exit_code=exit_code)

    monkeypatch.setattr(oracle, "_regular_file_digest", _drifted_digest)
    with pytest.raises(
        oracle._OracleFailure,
        match="authorized.*provenance|provenance.*authorized",
    ) as captured:
        oracle._immutable_provenance(exit_code=2)
    assert captured.value.exit_code == 2


def test_oracle_manifest_parser_rejects_inexact_case_headers() -> None:
    oracle = importlib.import_module("tools.build_task45_preoptimization_oracle")
    sidecars = [[name, 0, "0" * 64] for name, *_ in oracle._ARRAY_CONTRACTS]
    case = {
        "target_population": 100_000.0,
        "urbanized_area_km2_hex": (25.0).hex(),
        "style_id": "grid_core",
        "seed": 17.0,
        "task4": [0, "0" * 64, "1" * 64, sidecars, "2" * 64, "3" * 64],
        "task5": [0, "4" * 64, "5" * 64, sidecars, "6" * 64],
    }
    with pytest.raises(oracle._OracleFailure, match="case header"):
        oracle._validate_case_shape(case, expected_style="grid_core")


def test_oracle_manifest_parser_rejects_symlinks_and_nan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    oracle = importlib.import_module("tools.build_task45_preoptimization_oracle")
    target = tmp_path / "manifest-target.json"
    target.write_text("{}\n", encoding="utf-8")
    link = tmp_path / "manifest.json"
    link.symlink_to(target)
    monkeypatch.setattr(oracle, "_validate_manifest_shape", lambda _value: None)
    with pytest.raises(oracle._OracleFailure, match="regular non-symlink") as captured:
        oracle._read_manifest(link, exit_code=3)
    assert captured.value.exit_code == 3

    nan_manifest = tmp_path / "nan.json"
    nan_manifest.write_text('{"value":NaN}\n', encoding="utf-8")
    with pytest.raises(oracle._OracleFailure, match="invalid") as captured:
        oracle._read_manifest(nan_manifest, exit_code=3)
    assert captured.value.exit_code == 3


def test_oracle_verify_rejects_manifest_identity_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    oracle = importlib.import_module("tools.build_task45_preoptimization_oracle")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_bytes(b"before")
    environment = ("impl", "version", "numpy", "platform", "little", ".")
    provenance = (("review", "a" * 64),)
    census = (("src/metroflow/stable.py", "file", "b" * 64),)
    mutable = oracle._reviewed_mutable_pre_state()
    case = {"style_id": "only"}
    manifest = {
        "environment": list(environment),
        "immutable_provenance_sha256": [list(row) for row in provenance],
        "immutable_production_dependency_sha256": [list(row) for row in census],
        "mutable_production_pre_state": [list(row) for row in mutable],
        "cases": [case],
    }
    monkeypatch.setattr(oracle, "_STYLES", ("only",))
    monkeypatch.setattr(oracle, "_read_manifest", lambda *_args, **_kwargs: manifest)
    monkeypatch.setattr(oracle, "_environment", lambda **_kwargs: environment)
    monkeypatch.setattr(oracle, "_immutable_provenance", lambda **_kwargs: provenance)
    monkeypatch.setattr(
        oracle,
        "_immutable_production_census",
        lambda **_kwargs: census,
    )
    monkeypatch.setattr(
        oracle,
        "_mutable_production_state",
        lambda **_kwargs: mutable,
    )

    def _changing_case(_style_id: str) -> dict[str, object]:
        manifest_path.write_bytes(b"after")
        return case

    monkeypatch.setattr(oracle, "_build_case", _changing_case)
    with pytest.raises(oracle._OracleFailure, match="manifest.*changed") as captured:
        oracle._verify_manifest(manifest_path)
    assert captured.value.exit_code == 3
    output = capsys.readouterr().out
    assert "comparison.environment|status=PASS" in output
    assert "comparison.immutable_provenance.review|status=PASS" in output
    assert "comparison.immutable_production.src/metroflow/stable.py|status=PASS" in output
    assert "comparison.mutable_production." in output
    assert "comparison.case.only.style_id|status=PASS" in output


def test_oracle_manifest_read_is_descriptor_bound_against_path_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    oracle = importlib.import_module("tools.build_task45_preoptimization_oracle")
    manifest_path = tmp_path / "manifest.json"
    held_path = tmp_path / "manifest-held.json"
    donor_path = tmp_path / "manifest-donor.json"
    manifest_path.write_bytes(oracle._manifest_bytes({}))
    donor_path.write_bytes(oracle._manifest_bytes({"foreign": 1}))
    original_identity = oracle._manifest_identity
    identity_calls = 0

    def _swap_around_read(path: Path, *, exit_code: int) -> object:
        nonlocal identity_calls
        if identity_calls == 0:
            identity_calls += 1
            identity = original_identity(path, exit_code=exit_code)
            path.rename(held_path)
            path.symlink_to(donor_path)
            return identity
        if identity_calls == 1:
            identity_calls += 1
            path.unlink()
            held_path.rename(path)
        return original_identity(path, exit_code=exit_code)

    monkeypatch.setattr(oracle, "_manifest_identity", _swap_around_read)
    monkeypatch.setattr(oracle, "_validate_manifest_shape", lambda _value: None)
    with pytest.raises(
        oracle._OracleFailure,
        match="regular non-symlink|changed",
    ):
        oracle._read_manifest(manifest_path, exit_code=3)


def test_oracle_publication_fsyncs_directory_and_rolls_back_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    oracle = importlib.import_module("tools.build_task45_preoptimization_oracle")
    output = tmp_path / "manifest.json"
    original_open = os.open
    original_fsync = os.fsync
    directory_fds: set[int] = set()
    fsynced_fds: list[int] = []

    def _tracking_open(path: object, flags: int, *args: object) -> int:
        descriptor = original_open(path, flags, *args)
        if Path(path) == tmp_path:
            directory_fds.add(descriptor)
        return descriptor

    def _tracking_fsync(descriptor: int) -> None:
        fsynced_fds.append(descriptor)
        original_fsync(descriptor)

    monkeypatch.setattr(oracle.os, "open", _tracking_open)
    monkeypatch.setattr(oracle.os, "fsync", _tracking_fsync)
    oracle._write_create_once(output, b"payload")
    assert output.read_bytes() == b"payload"
    assert directory_fds & set(fsynced_fds)

    rollback_output = tmp_path / "rollback.json"
    original_directory_fsync = oracle._fsync_directory

    def _failing_directory_fsync(path: Path) -> None:
        if path == tmp_path:
            raise OSError("forced directory fsync failure")
        original_directory_fsync(path)

    monkeypatch.setattr(oracle, "_fsync_directory", _failing_directory_fsync)
    with pytest.raises(oracle._OracleFailure, match="publish|fsync|durable"):
        oracle._write_create_once(rollback_output, b"payload")
    assert not rollback_output.exists()


def test_controller_marks_measurement_before_sending_start() -> None:
    controller = importlib.import_module("tools.run_task45_validation_performance")
    source = inspect.getsource(controller._run_replicate)
    assert source.index("start_marker_ns =") < source.index('channel.send("START")')


def test_controller_releases_duplicate_receipts_and_binds_environment() -> None:
    controller = importlib.import_module("tools.run_task45_validation_performance")
    child_source = inspect.getsource(controller._measurement_child)
    first_clear = child_source.index("_clear_validation_receipts_for_test()")
    for name in (
        "network_receipt",
        "blocks_receipt",
        "compiled_receipt",
        "static_receipt",
        "setup_receipts",
    ):
        assert child_source.index(f"{name} = None") < first_clear

    baseline_ready = child_source.index('channel.send("BASELINE_READY")')
    for name in ("receipt_values", "fingerprints", "environment"):
        assert child_source.index(f"{name} = None") < baseline_ready
    assert baseline_ready < child_source.index(
        "start_message = channel.receive(_READY_TIMEOUT_SECONDS)"
    )

    assert "environment" in {field.name for field in controller.fields(controller._ReplicateResult)}
    run_source = inspect.getsource(controller._run_isolated_rss)
    assert "_require_exact_launcher" in run_source
    assert "first.environment != second.environment" in run_source


def test_controller_reaps_child_on_base_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = importlib.import_module("tools.run_task45_validation_performance")

    class _FakeSocket:
        def close(self) -> None:
            return None

    class _InterruptingChannel:
        def __init__(self, *_args: object) -> None:
            return None

        def receive(self, _timeout: float) -> object:
            raise KeyboardInterrupt

    class _FakeProcess:
        def __init__(self) -> None:
            self.pid = 12345
            self.exitcode: int | None = None
            self.alive = False
            self.terminate_called = False

        def start(self) -> None:
            self.alive = True

        def is_alive(self) -> bool:
            return self.alive

        def terminate(self) -> None:
            self.terminate_called = True
            self.alive = False
            self.exitcode = -15

        def kill(self) -> None:
            self.alive = False
            self.exitcode = -9

        def join(self, _timeout: float) -> None:
            return None

    process = _FakeProcess()
    context = SimpleNamespace(Process=lambda **_kwargs: process)
    monkeypatch.setattr(
        controller.socket,
        "socketpair",
        lambda *_args, **_kwargs: (_FakeSocket(), _FakeSocket()),
    )
    monkeypatch.setattr(controller.multiprocessing, "get_context", lambda _name: context)
    monkeypatch.setattr(controller, "_LineChannel", _InterruptingChannel)
    with pytest.raises(KeyboardInterrupt):
        controller._run_replicate(
            1,
            target_population=1_000_000,
            urbanized_area_km2=250,
            style_id="grid_core",
            seed=17,
        )
    assert process.terminate_called is True
    assert process.is_alive() is False


def test_controller_escalates_cleanup_and_checks_launcher() -> None:
    controller = importlib.import_module("tools.run_task45_validation_performance")

    class _IgnoringProcess:
        def __init__(self) -> None:
            self.alive = True
            self.exitcode: int | None = None
            self.terminate_called = False
            self.kill_called = False

        def is_alive(self) -> bool:
            return self.alive

        def terminate(self) -> None:
            self.terminate_called = True

        def kill(self) -> None:
            self.kill_called = True
            self.alive = False
            self.exitcode = -9

        def join(self, _timeout: float) -> None:
            return None

    process = _IgnoringProcess()
    controller._terminate_and_reap(process)
    assert process.terminate_called is True
    assert process.kill_called is True
    assert process.is_alive() is False

    expected_script = str(
        controller._REPOSITORY_ROOT / "tools/run_task45_validation_performance.py"
    )
    with pytest.raises(RuntimeError, match="launcher"):
        controller._require_exact_launcher(
            executable=str(Path("/usr/bin/python3").resolve()),
            script_path=expected_script,
            cwd=str(controller._REPOSITORY_ROOT),
        )
