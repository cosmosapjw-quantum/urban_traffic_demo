"""Scenario preset metadata used by map-foundation gate execution."""

from __future__ import annotations

from typing import Any, Final

MAP_FOUNDATION_GATE_PRESETS: Final[dict[str, dict[str, Any]]] = {
    "map_foundation_weekday_morning": {
        "scenario_id": "synthetic_100k",
        "seed": 42,
        "day_type": "weekday",
        "time_band": "morning",
        "ui_stream_enabled": False,
        "learning_enabled": False,
        "gate_profile": "sc020_sc042_map_foundation",
    },
    "map_foundation_weekend_evening": {
        "scenario_id": "synthetic_100k",
        "seed": 137,
        "day_type": "weekend",
        "time_band": "evening",
        "ui_stream_enabled": False,
        "learning_enabled": False,
        "gate_profile": "sc020_sc042_map_foundation",
    },
}

RADICAL_BACKBONE_GATE_PRESET: Final[dict[str, Any]] = {
    "scenario_id": "synthetic_100k",
    "seed": 42,
    "day_type": "weekday",
    "time_band": "morning",
    "ui_stream_enabled": False,
    "learning_enabled": False,
    "gate_profile": "phase3d_radical_backbone_gate",
    "required_metrics": (
        "active_bbox_aspect_ratio",
        "axis_aligned_link_share",
        "district_anisotropy_score",
        "one_tick_runtime_seconds_median",
        "fr002a_non_regression_pass",
        "fr005b_non_regression_pass",
        "fr006a_non_regression_pass",
        "fr006b_non_regression_pass",
    ),
}

REALISM_VALIDATION_SEEDS: Final[dict[str, int]] = {
    "map_foundation_weekday": int(MAP_FOUNDATION_GATE_PRESETS["map_foundation_weekday_morning"]["seed"]),
    "map_foundation_weekend": int(MAP_FOUNDATION_GATE_PRESETS["map_foundation_weekend_evening"]["seed"]),
    "radical_backbone_gate": int(RADICAL_BACKBONE_GATE_PRESET["seed"]),
}
