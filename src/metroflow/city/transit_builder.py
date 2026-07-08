from __future__ import annotations

from typing import Any

from .transit_schema import validate_transit_schema


def build_transit_ready_artifacts(*, seed: int) -> dict[str, object]:
    """Build deterministic transit-ready static artifacts for schema validation."""

    line_id = f"L{(int(seed) % 5) + 1}"
    station_prefix = f"S{(int(seed) % 3) + 1}"
    station_ids = [f"{station_prefix}A", f"{station_prefix}B", f"{station_prefix}C"]

    artifacts: dict[str, object] = {
        "lines": [
            {
                "line_id": line_id,
                "mode": "metro",
                "station_sequence": station_ids,
                "service_window": {"start": "05:30", "end": "24:00"},
            }
        ],
        "stations": [
            {"station_id": station_ids[0], "name": f"{station_ids[0]} Hub", "x": 0.0, "y": 0.0, "served_lines": [line_id]},
            {"station_id": station_ids[1], "name": f"{station_ids[1]} Core", "x": 1.0, "y": 0.4, "served_lines": [line_id]},
            {"station_id": station_ids[2], "name": f"{station_ids[2]} North", "x": 2.0, "y": 0.8, "served_lines": [line_id]},
        ],
        "transfers": [
            {
                "transfer_id": f"T{line_id}",
                "from_station_id": station_ids[0],
                "to_station_id": station_ids[1],
                "walk_time_seconds": 180,
                "penalty_seconds": 60,
            }
        ],
        "headways": [
            {
                "headway_profile_id": f"H{line_id}",
                "line_id": line_id,
                "time_band_to_headway_seconds": {"peak": 300, "offpeak": 480},
            }
        ],
    }
    validation = validate_transit_schema(artifacts)
    if not bool(validation["valid"]):
        raise ValueError(f"generated transit schema is invalid: {validation['errors']}")
    return artifacts


def apply_transit_builder_stage(state: dict[str, Any]) -> dict[str, Any]:
    """Attach transit-ready artifacts only when transit-ready mode is requested."""

    mode = str(state.get("mode", "road_only"))
    if mode != "transit_ready":
        return dict(state)

    next_state = dict(state)
    seed = int(next_state.get("seed", 0))
    artifacts = build_transit_ready_artifacts(seed=seed)
    next_state["transit_ready_artifacts"] = artifacts
    next_state["transit_schema_validation"] = validate_transit_schema(artifacts)
    return next_state
