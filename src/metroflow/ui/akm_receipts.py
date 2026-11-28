"""Read-only presentation adapter for explicitly research-scoped Rust receipts.

No transport, routing, eligibility, or storage computation lives here. The
native receipt status and provenance are kept, including a blocked run.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class AKMReceiptView:
    schema: str
    status: str
    model: str
    time_s: float
    scope: str
    sha256: str
    payload: dict[str, Any]


def _reject_nonfinite(token: str) -> None:
    raise ValueError(f"nonfinite JSON constant: {token}")


def _time(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("invalid observation time")
    if not math.isfinite(value) or value < 0:
        raise ValueError("invalid observation time")
    return float(value)


def read_akm_receipt(path: str | Path, *, expected_sha256: str | None = None) -> AKMReceiptView:
    """Decode committed Rust JSON without reconstructing any physical state."""
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError("AKM receipt digest mismatch")
    data = json.loads(raw, parse_constant=_reject_nonfinite)
    if not isinstance(data, dict):
        raise ValueError("invalid receipt schema")
    schema = data.get("schema")
    if schema == "metroflow_akm_native_owners_v1":
        status = data["status"]
        if status not in {"EXECUTED_FOR_REVIEW", "BLOCKED"}:
            raise ValueError("unsupported native research status")
        time = _time(data["time_s"])
        if "pilot" in data:
            times = [_time(x["time_s"]) for x in data["pilot"]["samples"]]
            if not times or times[-1] != time or any(a >= b for a, b in zip(times, times[1:])):
                raise ValueError("invalid pilot sample sequence")
        return AKMReceiptView(
            schema, status, data["model_identity"], time,
            data["scope"], digest, data,
        )
    if schema == "akm_d07_causal_lab_v1":
        status = data["status"]
        if status not in {"EXECUTED_FOR_REVIEW", "BLOCKED"}:
            raise ValueError("unsupported D07 research status")
        time = _time(data["time_s"])
        if _time(data["last_sample"]["time_s"]) != time:
            raise ValueError("inconsistent D07 observation time")
        times = [_time(r["time_s"]) for r in data["samples"]]
        if any(a >= b for a, b in zip(times, times[1:])) or any(t > time for t in times):
            raise ValueError("invalid D07 observation time sequence")
        return AKMReceiptView(
            schema, status, data["model_identity"], time,
            data["scope"], digest, data,
        )
    if schema == "akm_d08_luti_v1":
        status = data["status"]
        if status not in {"EXECUTED_FOR_REVIEW", "BLOCKED"}:
            raise ValueError("unsupported D08 research status")
        time = _time(data["time_s"])
        rows = data["epochs"]
        if len(rows) != data["completed_epochs"] or [r["index"] for r in rows] != list(range(len(rows))):
            raise ValueError("invalid D08 epoch sequence")
        if any(_time(r["access"]["stamp_s"]) > time for r in rows):
            raise ValueError("future D08 observation")
        return AKMReceiptView(schema, status, data["model_identity"], time,
                              data["scope"], digest, data)
    if schema == "akm_b_active_city_observed_v1":
        rows = data["result"]["snapshots"]
        times = [_time(r["time_s"]) for r in rows]
        if not times or times != data["observation_times_s"] or any(
            a >= b for a, b in zip(times, times[1:])
        ):
            raise ValueError("invalid native observation schedule")
        payload = dict(data)
        payload["snapshots"] = rows
        return AKMReceiptView(
            schema, "OBSERVED_RESEARCH", "akm-b-active-archive",
            times[-1], data["scope"], digest, payload,
        )
    raise ValueError("unsupported AKM receipt schema")
