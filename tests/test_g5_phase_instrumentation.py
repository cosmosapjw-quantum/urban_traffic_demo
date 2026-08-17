"""Diagnostic tests and non-intrusive phase instrumentation harness for G5 scalable map pipeline."""

from __future__ import annotations

import time
import os
import resource
from dataclasses import dataclass
import pytest

from metroflow.city.scale import CityScaleSpec
from metroflow.city.scalable_topology import build_scalable_street_network
from metroflow.city.scalable_blocks import build_scalable_block_authority
from metroflow.city.scalable_topology_adapter import compile_scalable_topology
from metroflow.city.scalable_authority import (
    build_scalable_static_authority,
    require_valid_scalable_static_authority,
    ScalableStaticAuthority,
)


@dataclass(frozen=True, slots=True)
class G5PhaseMeasurement:
    phase_id: str
    start_monotonic_ns: int
    end_monotonic_ns: int
    duration_ms: float
    start_vmrss_kib: int
    end_vmrss_kib: int
    delta_vmrss_kib: int


def _get_current_vmrss_kib() -> int:
    """Query current process VmRSS from /proc/self/statm or fallback to ru_maxrss."""
    try:
        with open("/proc/self/statm", "r") as f:
            fields = f.read().strip().split()
            page_size_kb = os.sysconf("SC_PAGE_SIZE") // 1024
            return int(fields[1]) * page_size_kb
    except Exception:
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def measure_g5_generation_phases(
    spec: CityScaleSpec,
    style_id: str,
    seed: int,
) -> tuple[dict[str, G5PhaseMeasurement], ScalableStaticAuthority]:
    """Execute all scalable generation stages and record non-intrusive phase timings/memory."""
    measurements: dict[str, G5PhaseMeasurement] = {}

    # Phase 1: Task 3 Street Network Topology
    t0 = time.monotonic_ns()
    rss0 = _get_current_vmrss_kib()
    network = build_scalable_street_network(spec, style_id, seed)
    t1 = time.monotonic_ns()
    rss1 = _get_current_vmrss_kib()
    measurements["task3_topology"] = G5PhaseMeasurement(
        phase_id="task3_topology",
        start_monotonic_ns=t0,
        end_monotonic_ns=t1,
        duration_ms=(t1 - t0) / 1_000_000.0,
        start_vmrss_kib=rss0,
        end_vmrss_kib=rss1,
        delta_vmrss_kib=max(0, rss1 - rss0),
    )

    # Phase 2: Task 3B Block Authority & DCEL Formation
    t0 = time.monotonic_ns()
    rss0 = _get_current_vmrss_kib()
    blocks = build_scalable_block_authority(network)
    t1 = time.monotonic_ns()
    rss1 = _get_current_vmrss_kib()
    measurements["task3b_blocks"] = G5PhaseMeasurement(
        phase_id="task3b_blocks",
        start_monotonic_ns=t0,
        end_monotonic_ns=t1,
        duration_ms=(t1 - t0) / 1_000_000.0,
        start_vmrss_kib=rss0,
        end_vmrss_kib=rss1,
        delta_vmrss_kib=max(0, rss1 - rss0),
    )

    # Phase 3: Task 4 Topology Compilation
    t0 = time.monotonic_ns()
    rss0 = _get_current_vmrss_kib()
    compiled = compile_scalable_topology(network, block_authority=blocks)
    t1 = time.monotonic_ns()
    rss1 = _get_current_vmrss_kib()
    measurements["task4_compile"] = G5PhaseMeasurement(
        phase_id="task4_compile",
        start_monotonic_ns=t0,
        end_monotonic_ns=t1,
        duration_ms=(t1 - t0) / 1_000_000.0,
        start_vmrss_kib=rss0,
        end_vmrss_kib=rss1,
        delta_vmrss_kib=max(0, rss1 - rss0),
    )

    # Phase 4: Task 5 Static Road Authority
    t0 = time.monotonic_ns()
    rss0 = _get_current_vmrss_kib()
    authority = build_scalable_static_authority(
        scale_spec=spec,
        style_id=style_id,
        seed=seed,
        network=network,
        blocks=blocks,
        compiled=compiled,
    )
    t1 = time.monotonic_ns()
    rss1 = _get_current_vmrss_kib()
    measurements["task5_authority"] = G5PhaseMeasurement(
        phase_id="task5_authority",
        start_monotonic_ns=t0,
        end_monotonic_ns=t1,
        duration_ms=(t1 - t0) / 1_000_000.0,
        start_vmrss_kib=rss0,
        end_vmrss_kib=rss1,
        delta_vmrss_kib=max(0, rss1 - rss0),
    )

    # Phase 5: Cross-Stage Validation Verification
    t0 = time.monotonic_ns()
    rss0 = _get_current_vmrss_kib()
    require_valid_scalable_static_authority(
        authority,
        scale_spec=spec,
        style_id=style_id,
        seed=seed,
        network=network,
        blocks=blocks,
        compiled=compiled,
    )
    t1 = time.monotonic_ns()
    rss1 = _get_current_vmrss_kib()
    measurements["task5_validation"] = G5PhaseMeasurement(
        phase_id="task5_validation",
        start_monotonic_ns=t0,
        end_monotonic_ns=t1,
        duration_ms=(t1 - t0) / 1_000_000.0,
        start_vmrss_kib=rss0,
        end_vmrss_kib=rss1,
        delta_vmrss_kib=max(0, rss1 - rss0),
    )

    return measurements, authority


ALL_STYLES = [
    "grid_core",
    "superblock_mixed",
    "organic",
    "ring_radial",
    "polycentric_tod",
    "river_constrained",
]


@pytest.mark.parametrize("style_id", ALL_STYLES)
def test_g5_phase_instrumentation_all_morphology_styles(style_id: str) -> None:
    """Verify non-intrusive phase instrumentation across all 6 archetypes at test scale."""
    spec = CityScaleSpec(
        target_population=100_000,
        urbanized_area_km2=25.0,
    )
    measurements, authority = measure_g5_generation_phases(spec, style_id=style_id, seed=42)

    assert set(measurements.keys()) == {
        "task3_topology",
        "task3b_blocks",
        "task4_compile",
        "task5_authority",
        "task5_validation",
    }

    for phase_id, m in measurements.items():
        assert m.phase_id == phase_id
        assert m.end_monotonic_ns >= m.start_monotonic_ns
        assert m.duration_ms >= 0.0
        assert m.start_vmrss_kib > 0
        assert m.end_vmrss_kib > 0

    assert isinstance(authority, ScalableStaticAuthority)
    assert authority.width_m > 0.0
    assert authority.height_m > 0.0
    assert len(authority.numeric_profiles) > 0
    assert len(authority.road_crosswalk) > 0


def test_g5_phase_instrumentation_deterministic_replicate() -> None:
    """Verify phase instrumentation produces identical authority and monotonic measurements."""
    spec = CityScaleSpec(
        target_population=100_000,
        urbanized_area_km2=25.0,
    )
    m1, auth1 = measure_g5_generation_phases(spec, style_id="grid_core", seed=17)
    m2, auth2 = measure_g5_generation_phases(spec, style_id="grid_core", seed=17)

    assert auth1.source_network_fingerprint == auth2.source_network_fingerprint
    assert auth1.source_blocks_fingerprint == auth2.source_blocks_fingerprint
    assert auth1.source_compiled_fingerprint == auth2.source_compiled_fingerprint
    assert auth1.width_m == auth2.width_m
    assert auth1.height_m == auth2.height_m

    for phase in m1:
        assert m1[phase].duration_ms >= 0.0
        assert m2[phase].duration_ms >= 0.0
