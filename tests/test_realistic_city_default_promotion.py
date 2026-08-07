from __future__ import annotations

import json
from pathlib import Path

from metroflow.benchmarks.realistic_city_scale import (
    load_realistic_city_scale_report,
)
from metroflow.city.plausibility_audit import (
    load_realistic_city_plausibility_audit,
)
from metroflow.sim.config import CityGenerationConfig

_ROOT = Path(__file__).resolve().parents[1]
_PR62 = _ROOT / "artifacts/runtime_spine_review/realistic-city-pr62-plausibility.json"
_PR63 = _ROOT / "artifacts/runtime_spine_review/realistic-city-pr63-scale.json"
_DECISION = (
    _ROOT
    / "artifacts/runtime_spine_review/realistic-city-pr64-default-promotion-decision.json"
)


def test_realistic_city_default_promotion_is_blocked_by_canonical_evidence() -> None:
    plausibility = load_realistic_city_plausibility_audit(_PR62)
    scale = load_realistic_city_scale_report(_PR63)
    decision = json.loads(_DECISION.read_text(encoding="utf-8"))
    default_config = CityGenerationConfig()

    assert plausibility.overall_pass is False
    assert scale.performance_gate_pass is False
    assert scale.default_promotion_eligible is False
    assert default_config.topology_mode == "standard"
    assert default_config.zone_poi_coupling_mode == "legacy"

    assert decision["status"] == "BLOCKED"
    assert decision["default_changed"] is False
    assert decision["current_default"] == "standard"
    assert decision["requested_default"] == "realistic_synthetic_v1"
    assert decision["source_evidence"]["pr62"]["fingerprint"] == plausibility.fingerprint
    assert decision["source_evidence"]["pr63"]["fingerprint"] == scale.fingerprint
    assert decision["source_evidence"]["pr62"]["pass"] is False
    assert decision["source_evidence"]["pr63"]["pass"] is False
    assert set(decision["blockers"]) == {
        "pr62_morphology_plausibility_failed",
        "pr63_generation_wall_failed",
        "pr63_realized_population_failed",
        "pr63_paired_throughput_failed",
    }
