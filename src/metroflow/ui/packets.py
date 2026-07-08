"""UI packet envelope and schema version helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from metroflow.sim.config import DayType, TimeBand

__all__ = [
    "UI_PACKET_SCHEMA_VERSION",
    "UISimTimeRef",
    "UIPacketType",
    "UIPacketEnvelope",
    "current_ui_packet_schema_version",
    "is_supported_ui_packet_schema_version",
    "assert_supported_ui_packet_schema_version",
    "build_ui_packet_envelope",
    "build_ui_event_overlay_packet",
    "build_ui_control_ack_packet",
    "normalize_ui_event_overlay_item",
    "validate_ui_packet_envelope",
]

UI_PACKET_SCHEMA_VERSION = 1


class StrEnum(str, Enum):
    """Local string enum base."""


class UIPacketType(StrEnum):
    TOPOLOGY_SNAPSHOT = "ui.topology_snapshot"
    CONGESTION_FRAME = "ui.congestion_frame"
    EVENT_OVERLAY = "ui.event_overlay"
    METRICS_SUMMARY = "ui.metrics_summary"
    CONTROL_COMMAND = "ui.control_command"
    CONTROL_ACK = "ui.control_ack"


@dataclass(slots=True)
class UISimTimeRef:
    """Current simulation day/time reference included in packet envelopes."""

    day_type: DayType
    time_band: TimeBand

    def __post_init__(self) -> None:
        self.day_type = DayType(self.day_type)
        self.time_band = TimeBand(self.time_band)

    def as_dict(self) -> dict[str, str]:
        return {
            "day_type": self.day_type.value,
            "time_band": self.time_band.value,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "UISimTimeRef":
        return cls(
            day_type=data["day_type"],
            time_band=data["time_band"],
        )


@dataclass(slots=True)
class UIPacketEnvelope:
    """Common UI packet envelope for simulation/UI stream messages."""

    type: UIPacketType | str
    run_id: str
    tick: int
    sim_time: UISimTimeRef | Mapping[str, Any]
    payload: Mapping[str, Any] | dict[str, Any] = field(default_factory=dict)
    schema_version: int = UI_PACKET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.type, UIPacketType):
            self.type = UIPacketType(self.type)
        self.run_id = str(self.run_id)
        self.tick = int(self.tick)
        self.schema_version = int(self.schema_version)
        if not isinstance(self.sim_time, UISimTimeRef):
            self.sim_time = UISimTimeRef.from_mapping(dict(self.sim_time))
        if not isinstance(self.payload, dict):
            self.payload = dict(self.payload)

        if self.tick < 0:
            raise ValueError("tick must be >= 0")
        if not self.run_id:
            raise ValueError("run_id must not be empty")
        assert_supported_ui_packet_schema_version(self.schema_version)

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "tick": self.tick,
            "sim_time": self.sim_time.as_dict(),
            "payload": dict(self.payload),
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "UIPacketEnvelope":
        return cls(
            type=data["type"],
            schema_version=data.get("schema_version", UI_PACKET_SCHEMA_VERSION),
            run_id=data["run_id"],
            tick=data["tick"],
            sim_time=data["sim_time"],
            payload=data.get("payload", {}),
        )


def current_ui_packet_schema_version() -> int:
    """Return the currently supported UI packet schema version."""

    return UI_PACKET_SCHEMA_VERSION


def is_supported_ui_packet_schema_version(schema_version: int) -> bool:
    """Whether an incoming/outgoing packet schema version is supported."""

    return int(schema_version) == UI_PACKET_SCHEMA_VERSION


def assert_supported_ui_packet_schema_version(schema_version: int) -> None:
    """Raise if `schema_version` is not supported by the current code."""

    if not is_supported_ui_packet_schema_version(schema_version):
        raise ValueError(
            "Unsupported UI packet schema_version "
            f"{int(schema_version)} (supported: {UI_PACKET_SCHEMA_VERSION})"
        )


def build_ui_packet_envelope(
    *,
    packet_type: UIPacketType | str,
    run_id: str,
    tick: int,
    day_type: DayType | str,
    time_band: TimeBand | str,
    payload: Mapping[str, Any] | None = None,
    schema_version: int = UI_PACKET_SCHEMA_VERSION,
) -> UIPacketEnvelope:
    """Build a UI packet envelope with normalized common fields."""

    return UIPacketEnvelope(
        type=packet_type,
        schema_version=schema_version,
        run_id=run_id,
        tick=tick,
        sim_time=UISimTimeRef(day_type=day_type, time_band=time_band),
        payload={} if payload is None else dict(payload),
    )


def build_ui_event_overlay_packet(
    *,
    run_id: str,
    tick: int,
    day_type: DayType | str,
    time_band: TimeBand | str,
    events: tuple[Any, ...] | list[Any],
    schema_version: int = UI_PACKET_SCHEMA_VERSION,
) -> UIPacketEnvelope:
    """Build a `ui.event_overlay` packet with normalized event payload items."""

    normalized = tuple(normalize_ui_event_overlay_item(e) for e in tuple(events))
    return build_ui_packet_envelope(
        packet_type=UIPacketType.EVENT_OVERLAY,
        run_id=run_id,
        tick=tick,
        day_type=day_type,
        time_band=time_band,
        payload={"events": normalized},
        schema_version=schema_version,
    )


def build_ui_control_ack_packet(
    *,
    run_id: str,
    tick: int,
    day_type: DayType | str,
    time_band: TimeBand | str,
    command_id: str,
    accepted: bool,
    reason: str | None = None,
    applied_tick: int | None = None,
    schema_version: int = UI_PACKET_SCHEMA_VERSION,
) -> UIPacketEnvelope:
    """Build a `ui.control_ack` envelope payload matching the packet contract."""

    payload: dict[str, Any] = {
        "command_id": str(command_id),
        "accepted": bool(accepted),
    }
    if reason:
        payload["reason"] = str(reason)
    if applied_tick is not None and not accepted:
        raise ValueError("applied_tick is only valid for accepted control acks")
    if applied_tick is not None:
        payload["applied_tick"] = int(applied_tick)

    return build_ui_packet_envelope(
        packet_type=UIPacketType.CONTROL_ACK,
        run_id=run_id,
        tick=tick,
        day_type=day_type,
        time_band=time_band,
        payload=payload,
        schema_version=schema_version,
    )


def normalize_ui_event_overlay_item(event: Any) -> dict[str, Any]:
    """Normalize one event overlay item into contract-friendly dict fields."""

    def _field(obj: Any, name: str, default: Any = None) -> Any:
        if isinstance(obj, Mapping):
            return obj.get(name, default)
        return getattr(obj, name, default)

    status = _field(event, "status", "")
    severity = _field(event, "severity", "")
    event_type = _field(event, "event_type", "")
    target_scope = _field(event, "target_scope", {})
    if not isinstance(target_scope, Mapping):
        target_scope = {}
    try:
        event_id = int(_field(event, "event_id", -1))
    except Exception:
        event_id = -1
    severity_out = _normalize_event_severity_value(severity)
    return {
        "event_id": event_id,
        "event_type": str(getattr(event_type, "value", event_type)),
        "status": str(getattr(status, "value", status)),
        "severity": severity_out,
        "target_scope": dict(target_scope),
    }


def _normalize_event_severity_value(raw: Any) -> str:
    """Return a stable string severity for UI packet compatibility/fail-soft behavior."""

    value = getattr(raw, "value", raw)
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        try:
            f = float(value)
        except Exception:
            return "unknown"
        return "unknown" if f != f or f in (float("inf"), float("-inf")) else str(f)
    if value is None:
        return "unknown"
    try:
        text = str(value)
    except Exception:
        return "unknown"
    return text if text else "unknown"


def validate_ui_packet_envelope(packet: Mapping[str, Any] | UIPacketEnvelope) -> tuple[str, ...]:
    """Return envelope validation issues (empty tuple means valid)."""

    issues: list[str] = []
    try:
        envelope = (
            packet
            if isinstance(packet, UIPacketEnvelope)
            else UIPacketEnvelope.from_mapping(packet)
        )
    except Exception as exc:  # foundational helper; return issue instead of raising
        return (f"invalid_envelope: {exc}",)

    if not envelope.run_id:
        issues.append("run_id must not be empty")
    if envelope.tick < 0:
        issues.append("tick must be >= 0")
    if not is_supported_ui_packet_schema_version(envelope.schema_version):
        issues.append(
            "unsupported schema_version "
            f"{envelope.schema_version} (supported: {UI_PACKET_SCHEMA_VERSION})"
        )
    if not isinstance(envelope.payload, dict):
        issues.append("payload must be an object/dict")
    return tuple(issues)
