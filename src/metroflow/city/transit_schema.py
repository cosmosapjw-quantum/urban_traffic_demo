from __future__ import annotations

from typing import Any, Mapping


def _as_list(value: object, *, field_name: str, errors: list[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        errors.append(f"{field_name} must be a list")
        return []
    out: list[dict[str, Any]] = []
    for idx, entry in enumerate(value):
        if not isinstance(entry, dict):
            errors.append(f"{field_name}[{idx}] must be an object")
            continue
        out.append(entry)
    return out


def _require_unique_ids(
    entries: list[dict[str, Any]],
    *,
    id_field: str,
    label: str,
    errors: list[str],
) -> set[str]:
    ids: set[str] = set()
    for idx, entry in enumerate(entries):
        value = entry.get(id_field)
        if not isinstance(value, str) or not value:
            errors.append(f"{label}[{idx}].{id_field} must be a non-empty string")
            continue
        if value in ids:
            errors.append(f"duplicate {label} id: {value}")
            continue
        ids.add(value)
    return ids


def validate_transit_schema(schema: Mapping[str, object]) -> dict[str, object]:
    """Validate transit-ready schema integrity contract."""

    errors: list[str] = []
    lines = _as_list(schema.get("lines"), field_name="lines", errors=errors)
    stations = _as_list(schema.get("stations"), field_name="stations", errors=errors)
    transfers = _as_list(schema.get("transfers"), field_name="transfers", errors=errors)
    headways = _as_list(schema.get("headways"), field_name="headways", errors=errors)

    line_ids = _require_unique_ids(lines, id_field="line_id", label="lines", errors=errors)
    station_ids = _require_unique_ids(stations, id_field="station_id", label="stations", errors=errors)
    _require_unique_ids(transfers, id_field="transfer_id", label="transfers", errors=errors)
    _require_unique_ids(headways, id_field="headway_profile_id", label="headways", errors=errors)

    for idx, line in enumerate(lines):
        station_sequence = line.get("station_sequence")
        if not isinstance(station_sequence, list) or len(station_sequence) < 2:
            errors.append(f"lines[{idx}].station_sequence must have >= 2 stations")
            continue
        for station_id in station_sequence:
            if not isinstance(station_id, str) or station_id not in station_ids:
                errors.append(f"lines[{idx}] references unknown station_id: {station_id}")

    for idx, station in enumerate(stations):
        served_lines = station.get("served_lines")
        if not isinstance(served_lines, list) or not served_lines:
            errors.append(f"stations[{idx}].served_lines must be a non-empty list")
            continue
        for line_id in served_lines:
            if not isinstance(line_id, str) or line_id not in line_ids:
                errors.append(f"stations[{idx}] references unknown line_id: {line_id}")

    for idx, transfer in enumerate(transfers):
        from_station = transfer.get("from_station_id")
        to_station = transfer.get("to_station_id")
        if not isinstance(from_station, str) or from_station not in station_ids:
            errors.append(f"transfers[{idx}].from_station_id is invalid")
        if not isinstance(to_station, str) or to_station not in station_ids:
            errors.append(f"transfers[{idx}].to_station_id is invalid")
        if isinstance(from_station, str) and isinstance(to_station, str) and from_station == to_station:
            errors.append(f"transfers[{idx}] must connect distinct stations")

    for idx, profile in enumerate(headways):
        line_id = profile.get("line_id")
        if not isinstance(line_id, str) or line_id not in line_ids:
            errors.append(f"headways[{idx}].line_id is invalid")
        mapping = profile.get("time_band_to_headway_seconds")
        if not isinstance(mapping, dict) or not mapping:
            errors.append(f"headways[{idx}].time_band_to_headway_seconds must be a non-empty mapping")
            continue
        for band, seconds in mapping.items():
            if not isinstance(band, str) or not band:
                errors.append(f"headways[{idx}] has invalid time band key")
            if not isinstance(seconds, (int, float)) or seconds <= 0:
                errors.append(f"headways[{idx}] has non-positive headway value for {band}")

    return {
        "valid": not errors,
        "errors": errors,
    }
