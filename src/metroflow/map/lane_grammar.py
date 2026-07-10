"""Project-owned static road-section grammar with explicit meter units."""

from __future__ import annotations

import hashlib
import json
import math
import operator
from dataclasses import dataclass, field
from enum import Enum
from numbers import Real

__all__ = [
    "SegmentInterfaceType",
    "RoadUnitKind",
    "TravelDirection",
    "RoadDesignStandard",
    "RoadSectionUnit",
    "RoadSectionEnd",
    "RoadSectionProfile",
    "CarriagewayProfile",
]


class SegmentInterfaceType(str, Enum):
    BASE = "base"
    SHIFT = "shift"
    TRANSITION = "transition"
    RAMP = "ramp"


class RoadUnitKind(str, Enum):
    LANE = "lane"
    MEDIAN = "median"
    SHOULDER = "shoulder"
    CURB = "curb"
    SIDEWALK = "sidewalk"
    BIKE_LANE = "bike_lane"
    BARRIER = "barrier"
    CHANNEL = "channel"
    PARKING = "parking"
    EMPTY = "empty"


class TravelDirection(str, Enum):
    FORWARD = "forward"
    BACKWARD = "backward"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class RoadDesignStandard:
    """Authored road dimensions in meters for static section compilation."""

    lane_width_m: float = 3.5
    median_width_m: float = 1.2
    shoulder_width_m: float = 1.5
    curb_width_m: float = 0.25
    sidewalk_width_m: float = 2.0
    bike_lane_width_m: float = 1.8
    barrier_width_m: float = 0.5
    channel_width_m: float = 1.0
    parking_width_m: float = 2.5
    max_lateral_shift_m: float = 3.5

    def __post_init__(self) -> None:
        for name in (
            "lane_width_m",
            "median_width_m",
            "shoulder_width_m",
            "curb_width_m",
            "sidewalk_width_m",
            "bike_lane_width_m",
            "barrier_width_m",
            "channel_width_m",
            "parking_width_m",
            "max_lateral_shift_m",
        ):
            value = _canonical_float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and > 0")
            object.__setattr__(self, name, value)

    def width_for(self, kind: RoadUnitKind | str) -> float:
        resolved = RoadUnitKind(kind)
        field_name = {
            RoadUnitKind.LANE: "lane_width_m",
            RoadUnitKind.MEDIAN: "median_width_m",
            RoadUnitKind.SHOULDER: "shoulder_width_m",
            RoadUnitKind.CURB: "curb_width_m",
            RoadUnitKind.SIDEWALK: "sidewalk_width_m",
            RoadUnitKind.BIKE_LANE: "bike_lane_width_m",
            RoadUnitKind.BARRIER: "barrier_width_m",
            RoadUnitKind.CHANNEL: "channel_width_m",
            RoadUnitKind.PARKING: "parking_width_m",
            RoadUnitKind.EMPTY: "lane_width_m",
        }[resolved]
        return float(getattr(self, field_name))

    def _canonical_payload(self) -> dict[str, float]:
        return {
            name: float(getattr(self, name))
            for name in (
                "lane_width_m",
                "median_width_m",
                "shoulder_width_m",
                "curb_width_m",
                "sidewalk_width_m",
                "bike_lane_width_m",
                "barrier_width_m",
                "channel_width_m",
                "parking_width_m",
                "max_lateral_shift_m",
            )
        }


@dataclass(frozen=True, slots=True)
class RoadSectionUnit:
    """One ordered cross-section unit with width measured in meters."""

    kind: RoadUnitKind | str
    width_m: float
    direction: TravelDirection | str = TravelDirection.NONE

    def __post_init__(self) -> None:
        kind = RoadUnitKind(self.kind)
        direction = TravelDirection(self.direction)
        width_m = _canonical_float(self.width_m)
        if not math.isfinite(width_m):
            raise ValueError("width_m must be finite")
        if width_m <= 0.0:
            raise ValueError("width_m must be > 0")
        if kind is RoadUnitKind.LANE and direction is TravelDirection.NONE:
            raise ValueError("lane units require a travel direction")
        if kind is not RoadUnitKind.LANE and direction is not TravelDirection.NONE:
            raise ValueError(f"{kind.value} units must not have a travel direction")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "width_m", width_m)
        object.__setattr__(self, "direction", direction)

    def _canonical_payload(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "width_m": self.width_m,
            "direction": self.direction.value,
        }


@dataclass(frozen=True, slots=True)
class RoadSectionEnd:
    """Ordered left-to-right units at one end of a road segment."""

    units: tuple[RoadSectionUnit, ...]

    def __post_init__(self) -> None:
        units = tuple(self.units)
        if not units:
            raise ValueError("section end units must not be empty")
        if any(not isinstance(unit, RoadSectionUnit) for unit in units):
            raise TypeError("section end units must be RoadSectionUnit instances")
        if not any(unit.kind is RoadUnitKind.LANE for unit in units):
            raise ValueError("section end must contain at least one lane")
        object.__setattr__(self, "units", units)

    @property
    def lane_count_forward(self) -> int:
        return sum(
            unit.kind is RoadUnitKind.LANE
            and unit.direction is TravelDirection.FORWARD
            for unit in self.units
        )

    @property
    def lane_count_backward(self) -> int:
        return sum(
            unit.kind is RoadUnitKind.LANE
            and unit.direction is TravelDirection.BACKWARD
            for unit in self.units
        )

    @property
    def lane_count_total(self) -> int:
        return self.lane_count_forward + self.lane_count_backward

    @property
    def total_width_m(self) -> float:
        return float(sum(unit.width_m for unit in self.units))

    @property
    def fingerprint(self) -> str:
        return _sha256_json(self._canonical_payload())

    def _canonical_payload(self) -> dict[str, object]:
        return {"units": [unit._canonical_payload() for unit in self.units]}


@dataclass(frozen=True, slots=True)
class RoadSectionProfile:
    """Static start/end cross-section with interface-specific validation."""

    profile_id: str
    start: RoadSectionEnd
    end: RoadSectionEnd
    interface_type: SegmentInterfaceType | str
    start_center_offset_m: float = 0.0
    end_center_offset_m: float = 0.0
    design_standard: RoadDesignStandard = field(default_factory=RoadDesignStandard)

    def __post_init__(self) -> None:
        profile_id = str(self.profile_id).strip()
        interface_type = SegmentInterfaceType(self.interface_type)
        start_offset = _canonical_float(self.start_center_offset_m)
        end_offset = _canonical_float(self.end_center_offset_m)
        if not profile_id:
            raise ValueError("profile_id must be non-empty")
        if not isinstance(self.start, RoadSectionEnd) or not isinstance(
            self.end, RoadSectionEnd
        ):
            raise TypeError("start and end must be RoadSectionEnd instances")
        if not isinstance(self.design_standard, RoadDesignStandard):
            raise TypeError("design_standard must be a RoadDesignStandard")
        if not math.isfinite(start_offset) or not math.isfinite(end_offset):
            raise ValueError("section center offsets must be finite")

        object.__setattr__(self, "profile_id", profile_id)
        object.__setattr__(self, "interface_type", interface_type)
        object.__setattr__(self, "start_center_offset_m", start_offset)
        object.__setattr__(self, "end_center_offset_m", end_offset)
        self._validate_interface()

    @property
    def fingerprint(self) -> str:
        """Structural fingerprint excluding the human-facing profile ID."""

        return _sha256_json(
            self._structural_payload()
        )

    @property
    def identity_fingerprint(self) -> str:
        """Fingerprint including the stable human-facing profile ID."""

        return _sha256_json(
            {
                "profile_id": self.profile_id,
                "structure": self._structural_payload(),
            }
        )

    def _structural_payload(self) -> dict[str, object]:
        return {
            "start": self.start._canonical_payload(),
            "end": self.end._canonical_payload(),
            "interface_type": self.interface_type.value,
            "start_center_offset_m": self.start_center_offset_m,
            "end_center_offset_m": self.end_center_offset_m,
        }

    def _validate_interface(self) -> None:
        offset_delta = abs(self.end_center_offset_m - self.start_center_offset_m)
        if self.interface_type is SegmentInterfaceType.BASE:
            if self.start != self.end or offset_delta != 0.0:
                raise ValueError("BASE profiles require identical sections and offsets")
            return
        if self.interface_type is SegmentInterfaceType.SHIFT:
            if self.start != self.end or offset_delta <= 0.0:
                raise ValueError("SHIFT profiles preserve sections and require a nonzero offset")
            if offset_delta > self.design_standard.max_lateral_shift_m:
                raise ValueError("SHIFT offset exceeds max_lateral_shift_m")
            return
        directional_deltas = (
            self.end.lane_count_forward - self.start.lane_count_forward,
            self.end.lane_count_backward - self.start.lane_count_backward,
        )
        if sorted(abs(delta) for delta in directional_deltas) != [0, 1]:
            raise ValueError(
                f"{self.interface_type.name} profiles must change exactly one lane "
                "in one travel direction"
            )
        changed_direction = (
            TravelDirection.FORWARD
            if directional_deltas[0] != 0
            else TravelDirection.BACKWARD
        )
        if self.interface_type is SegmentInterfaceType.TRANSITION:
            if offset_delta != 0.0:
                raise ValueError("TRANSITION profiles must preserve center offset")
            if not _is_single_lane_edit(
                self.start,
                self.end,
                direction=changed_direction,
                lane_width_m=self.design_standard.lane_width_m,
            ):
                raise ValueError(
                    "TRANSITION profiles permit only one ordered lane insertion or deletion"
                )
            return
        if offset_delta > self.design_standard.max_lateral_shift_m:
            raise ValueError("RAMP offset exceeds max_lateral_shift_m")
        if not _is_adjacent_lane_channel_edit(
            self.start,
            self.end,
            direction=changed_direction,
            lane_width_m=self.design_standard.lane_width_m,
            channel_width_m=self.design_standard.channel_width_m,
        ):
            raise ValueError(
                "RAMP profiles require one adjacent lane and CHANNEL edit on the wider end"
            )


@dataclass(frozen=True, slots=True)
class CarriagewayProfile:
    """Compatibility facade for directional lane counts and roadside style."""

    lane_count_forward: int
    lane_count_backward: int
    median: bool = False
    roadside_profile: str = "urban"

    def __post_init__(self) -> None:
        forward = _strict_nonnegative_int(
            self.lane_count_forward,
            "lane_count_forward",
        )
        backward = _strict_nonnegative_int(
            self.lane_count_backward,
            "lane_count_backward",
        )
        roadside = str(self.roadside_profile)
        if forward + backward < 1:
            raise ValueError("at least one carriageway lane is required")
        if not isinstance(self.median, bool):
            raise ValueError("median must be a bool")
        if roadside not in {"urban", "rural", "limited_access", "none"}:
            raise ValueError(
                "roadside_profile must be one of: urban, rural, limited_access, none"
            )
        object.__setattr__(self, "lane_count_forward", forward)
        object.__setattr__(self, "lane_count_backward", backward)
        object.__setattr__(self, "median", bool(self.median))
        object.__setattr__(self, "roadside_profile", roadside)

    def to_section_end(
        self,
        standard: RoadDesignStandard | None = None,
    ) -> RoadSectionEnd:
        """Compile this facade to ordered static units using `standard`."""

        design = standard if standard is not None else RoadDesignStandard()
        if not isinstance(design, RoadDesignStandard):
            raise TypeError("standard must be a RoadDesignStandard")
        units: list[RoadSectionUnit] = []
        units.extend(_roadside_units(self.roadside_profile, design, left=True))
        units.extend(
            RoadSectionUnit(
                RoadUnitKind.LANE,
                design.lane_width_m,
                TravelDirection.BACKWARD,
            )
            for _ in range(self.lane_count_backward)
        )
        if self.median and self.lane_count_forward and self.lane_count_backward:
            units.append(RoadSectionUnit(RoadUnitKind.MEDIAN, design.median_width_m))
        units.extend(
            RoadSectionUnit(
                RoadUnitKind.LANE,
                design.lane_width_m,
                TravelDirection.FORWARD,
            )
            for _ in range(self.lane_count_forward)
        )
        units.extend(_roadside_units(self.roadside_profile, design, left=False))
        return RoadSectionEnd(tuple(units))


def _roadside_units(
    profile: str,
    design: RoadDesignStandard,
    *,
    left: bool,
) -> tuple[RoadSectionUnit, ...]:
    if profile == "none":
        return ()
    if profile == "urban":
        return (RoadSectionUnit(RoadUnitKind.SIDEWALK, design.sidewalk_width_m),)
    if profile == "rural":
        return (RoadSectionUnit(RoadUnitKind.SHOULDER, design.shoulder_width_m),)
    units = (
        RoadSectionUnit(RoadUnitKind.BARRIER, design.barrier_width_m),
        RoadSectionUnit(RoadUnitKind.SHOULDER, design.shoulder_width_m),
    )
    return units if left else tuple(reversed(units))


def _canonical_float(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("value must be a real number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("value must be a finite real number") from exc
    return 0.0 if number == 0.0 else number


def _strict_nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a nonnegative integer")
    try:
        number = operator.index(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field_name} must be a nonnegative integer") from exc
    if number < 0:
        raise ValueError(f"{field_name} must be a nonnegative integer")
    return int(number)


def _is_single_lane_edit(
    start: RoadSectionEnd,
    end: RoadSectionEnd,
    *,
    direction: TravelDirection,
    lane_width_m: float,
) -> bool:
    wider, narrower = (
        (end.units, start.units)
        if end.lane_count_total > start.lane_count_total
        else (start.units, end.units)
    )
    if len(wider) != len(narrower) + 1:
        return False
    for index, unit in enumerate(wider):
        if (
            unit.kind is RoadUnitKind.LANE
            and unit.direction is direction
            and unit.width_m == lane_width_m
            and wider[:index] + wider[index + 1 :] == narrower
        ):
            return True
    return False


def _is_adjacent_lane_channel_edit(
    section: RoadSectionEnd,
    end: RoadSectionEnd,
    *,
    direction: TravelDirection,
    lane_width_m: float,
    channel_width_m: float,
) -> bool:
    wider, narrower = (
        (end.units, section.units)
        if end.lane_count_total > section.lane_count_total
        else (section.units, end.units)
    )
    if len(wider) != len(narrower) + 2:
        return False
    for lane_index, lane in enumerate(wider):
        if not (
            lane.kind is RoadUnitKind.LANE
            and lane.direction is direction
            and lane.width_m == lane_width_m
        ):
            continue
        for channel_index in (lane_index - 1, lane_index + 1):
            if channel_index < 0 or channel_index >= len(wider):
                continue
            channel = wider[channel_index]
            if not (
                channel.kind is RoadUnitKind.CHANNEL
                and channel.width_m == channel_width_m
            ):
                continue
            removed = {lane_index, channel_index}
            if tuple(unit for index, unit in enumerate(wider) if index not in removed) == narrower:
                return True
    return False


def _sha256_json(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()
