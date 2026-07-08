"""UI control packet <-> simulation control adapter helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from metroflow.sim.control import SimulationControl
from metroflow.ui.packets import UIPacketEnvelope, UIPacketType, build_ui_control_ack_packet as _build_ack_packet

__all__ = [
    "UIControlCommandParseResult",
    "parse_ui_control_command",
    "build_ui_control_ack_packet",
]


@dataclass(slots=True)
class UIControlCommandParseResult:
    """Normalized result of parsing a `ui.control_command` packet."""

    command_id: str
    action: str | None
    control: SimulationControl
    accepted: bool
    reason: str | None = None

    def ack_payload(self, *, applied_tick: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "command_id": self.command_id,
            "accepted": bool(self.accepted),
        }
        if self.reason:
            payload["reason"] = str(self.reason)
        if applied_tick is not None:
            payload["applied_tick"] = int(applied_tick)
        return payload


def parse_ui_control_command(
    packet: Mapping[str, Any] | UIPacketEnvelope,
) -> UIControlCommandParseResult:
    """Parse a `ui.control_command` envelope into `SimulationControl`.

    This adapter currently supports the baseline T038 actions:
    - `set_day_type`
    - `set_time_band`
    - `request_snapshot`
    """

    try:
        envelope = packet if isinstance(packet, UIPacketEnvelope) else UIPacketEnvelope.from_mapping(packet)
    except Exception as exc:
        return UIControlCommandParseResult(
            command_id="",
            action=None,
            control=SimulationControl.noop(),
            accepted=False,
            reason=f"invalid_control_packet: {exc}",
        )

    payload = envelope.payload if isinstance(envelope.payload, Mapping) else {}
    raw_command_id = payload.get("command_id", "")
    command_id = raw_command_id.strip() if isinstance(raw_command_id, str) else ""
    action = payload.get("action")
    raw_args = payload.get("arguments", {})

    if envelope.type is not UIPacketType.CONTROL_COMMAND:
        return UIControlCommandParseResult(
            command_id=command_id,
            action=str(action) if action is not None else None,
            control=SimulationControl.noop(),
            accepted=False,
            reason=f"unexpected_packet_type: {envelope.type.value}",
        )
    if not command_id:
        return UIControlCommandParseResult(
            command_id="",
            action=str(action) if action is not None else None,
            control=SimulationControl.noop(),
            accepted=False,
            reason="missing command_id",
        )
    if not isinstance(action, str) or not action:
        return UIControlCommandParseResult(
            command_id=command_id,
            action=None,
            control=SimulationControl.noop(),
            accepted=False,
            reason="missing action",
        )
    if not isinstance(raw_args, Mapping):
        return UIControlCommandParseResult(
            command_id=command_id,
            action=action,
            control=SimulationControl.noop(),
            accepted=False,
            reason="arguments must be an object",
        )
    args = dict(raw_args)

    try:
        control = _control_from_action(action, args)
    except ValueError as exc:
        return UIControlCommandParseResult(
            command_id=command_id,
            action=action,
            control=SimulationControl.noop(),
            accepted=False,
            reason=str(exc),
        )

    return UIControlCommandParseResult(
        command_id=command_id,
        action=action,
        control=control,
        accepted=True,
    )


def build_ui_control_ack_packet(
    *,
    run_id: str,
    tick: int,
    day_type: str,
    time_band: str,
    command_id: str,
    accepted: bool,
    reason: str | None = None,
    applied_tick: int | None = None,
) -> UIPacketEnvelope:
    """Backward-compatible wrapper delegating to `ui.packets` builder (T053)."""

    return _build_ack_packet(
        run_id=run_id,
        tick=tick,
        day_type=day_type,
        time_band=time_band,
        command_id=command_id,
        accepted=accepted,
        reason=reason,
        applied_tick=applied_tick,
    )


def _control_from_action(action: str, args: Mapping[str, Any]) -> SimulationControl:
    if action == "set_day_type":
        if "day_type" not in args:
            raise ValueError("set_day_type requires arguments.day_type")
        return SimulationControl(set_day_type=args["day_type"])
    if action == "set_time_band":
        if "time_band" not in args:
            raise ValueError("set_time_band requires arguments.time_band")
        return SimulationControl(set_time_band=args["time_band"])
    if action == "request_snapshot":
        force = bool(args.get("force", True))
        return SimulationControl(ui_force_snapshot=force)
    raise ValueError(f"unsupported action: {action}")
