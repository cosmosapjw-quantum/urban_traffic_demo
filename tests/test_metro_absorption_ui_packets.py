from __future__ import annotations

import sys
from dataclasses import dataclass

import pytest


def test_ui_packet_envelope_round_trips_without_donor_path() -> None:
    assert not any(path.endswith("/metro/src") for path in sys.path)

    from metroflow.ui.packets import (
        UIPacketType,
        build_ui_packet_envelope,
        validate_ui_packet_envelope,
    )

    envelope = build_ui_packet_envelope(
        packet_type=UIPacketType.CONGESTION_FRAME,
        run_id="run-1",
        tick=25,
        day_type="weekday",
        time_band="morning",
        payload={"sampled_link_count": 3},
    )

    as_dict = envelope.as_dict()

    assert as_dict == {
        "type": "ui.congestion_frame",
        "schema_version": 1,
        "run_id": "run-1",
        "tick": 25,
        "sim_time": {"day_type": "weekday", "time_band": "morning"},
        "payload": {"sampled_link_count": 3},
    }
    assert validate_ui_packet_envelope(as_dict) == ()


def test_ui_packet_schema_validation_is_fail_closed() -> None:
    from metroflow.ui.packets import (
        assert_supported_ui_packet_schema_version,
        validate_ui_packet_envelope,
    )

    with pytest.raises(ValueError, match="Unsupported UI packet schema_version"):
        assert_supported_ui_packet_schema_version(2)

    issues = validate_ui_packet_envelope(
        {
            "type": "ui.metrics_summary",
            "schema_version": 2,
            "run_id": "run-1",
            "tick": 0,
            "sim_time": {"day_type": "weekday", "time_band": "morning"},
            "payload": {},
        }
    )

    assert issues
    assert "unsupported" in issues[0].lower()


def test_event_overlay_packet_normalizes_mapping_and_object_events() -> None:
    from metroflow.ui.packets import build_ui_event_overlay_packet

    @dataclass
    class EventObject:
        event_id: int
        event_type: str
        status: str
        severity: float
        target_scope: dict[str, object]

    packet = build_ui_event_overlay_packet(
        run_id="run-1",
        tick=10,
        day_type="weekday",
        time_band="lunch",
        events=[
            {"event_id": "7", "event_type": "accident", "status": "active", "severity": True},
            EventObject(8, "closure", "scheduled", 0.5, {"link_ids": (1, 2)}),
        ],
    )

    assert packet.as_dict()["payload"]["events"] == (
        {
            "event_id": 7,
            "event_type": "accident",
            "status": "active",
            "severity": "true",
            "target_scope": {},
        },
        {
            "event_id": 8,
            "event_type": "closure",
            "status": "scheduled",
            "severity": "0.5",
            "target_scope": {"link_ids": (1, 2)},
        },
    )


def test_ui_snapshot_stream_buffer_throttles_and_coalesces_latest_snapshot() -> None:
    from metroflow.ui.stream_buffer import (
        UISnapshotStreamBuffer,
        compute_min_emit_interval_ticks,
    )

    assert compute_min_emit_interval_ticks(tick_seconds=1.0, hz_limit=0.5) == 2

    buffer = UISnapshotStreamBuffer(tick_seconds=1.0, hz_limit=0.5)

    first = buffer.offer({"frame": "a"}, tick=0)
    second = buffer.offer({"frame": "b"}, tick=1)
    third = buffer.offer({"frame": "c"}, tick=2)

    assert first is not None
    assert first.snapshot_source == {"frame": "a"}
    assert second is None
    assert third is not None
    assert third.snapshot_source == {"frame": "c"}
    assert third.dropped_since_last_emit == 1
    assert buffer.stats.as_dict() == {
        "offered": 3,
        "emitted": 2,
        "dropped_coalesced": 1,
        "forced_emits": 0,
    }
