"""Compile static road-section profiles from aggregate generated links."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from numbers import Integral, Real
from types import MappingProxyType
from typing import Mapping, Protocol, Sequence

from metroflow.map.lane_grammar import (
    CarriagewayProfile,
    RoadDesignStandard,
    RoadSectionProfile,
    SegmentInterfaceType,
    TravelDirection,
)
from metroflow.map.road_geometry import RoadGeometryCatalog

__all__ = [
    "LinkSectionAssignment",
    "RoadSectionCatalog",
    "compile_road_sections",
]


class _LinkLike(Protocol):
    link_id: int
    road_class: object
    lanes: int
    capacity_veh_per_tick: float


@dataclass(frozen=True, slots=True)
class LinkSectionAssignment:
    """Static aggregate section values for one directed link."""

    link_id: int
    profile_id: str
    direction: TravelDirection | str
    lane_count: int
    capacity_veh_per_tick: float
    total_width_m: float

    def __post_init__(self) -> None:
        link_id = _strict_nonnegative_int(self.link_id, "link_id")
        profile_id = str(self.profile_id).strip()
        direction = TravelDirection(self.direction)
        lane_count = _strict_nonnegative_int(self.lane_count, "lane_count")
        capacity = _strict_real(self.capacity_veh_per_tick, "capacity_veh_per_tick")
        width = _strict_real(self.total_width_m, "total_width_m")
        if not profile_id:
            raise ValueError("profile_id must be non-empty")
        if direction is TravelDirection.NONE:
            raise ValueError("link section direction must be forward or backward")
        if lane_count < 1:
            raise ValueError("lane_count must be >= 1")
        if not math.isfinite(capacity) or capacity < 0.0:
            raise ValueError("capacity_veh_per_tick must be finite and >= 0")
        if not math.isfinite(width) or width <= 0.0:
            raise ValueError("total_width_m must be finite and > 0")
        object.__setattr__(self, "link_id", link_id)
        object.__setattr__(self, "profile_id", profile_id)
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "lane_count", lane_count)
        object.__setattr__(self, "capacity_veh_per_tick", capacity)
        object.__setattr__(self, "total_width_m", width)

    def _canonical_payload(self) -> dict[str, object]:
        return {
            "link_id": self.link_id,
            "profile_id": self.profile_id,
            "direction": self.direction.value,
            "lane_count": self.lane_count,
            "capacity_veh_per_tick": self.capacity_veh_per_tick,
            "total_width_m": self.total_width_m,
        }


@dataclass(frozen=True, slots=True)
class RoadSectionCatalog:
    """Unique static profiles and complete directed-link assignments."""

    profiles: tuple[RoadSectionProfile, ...]
    assignments: tuple[LinkSectionAssignment, ...]
    _profile_by_id: Mapping[str, RoadSectionProfile] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _assignment_by_link_id: Mapping[int, LinkSectionAssignment] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        profiles = tuple(sorted(self.profiles, key=lambda item: item.profile_id))
        assignments = tuple(sorted(self.assignments, key=lambda item: item.link_id))
        if any(not isinstance(item, RoadSectionProfile) for item in profiles):
            raise TypeError("profiles must contain RoadSectionProfile instances")
        if any(not isinstance(item, LinkSectionAssignment) for item in assignments):
            raise TypeError("assignments must contain LinkSectionAssignment instances")
        profile_by_id = {profile.profile_id: profile for profile in profiles}
        assignment_by_link_id = {
            assignment.link_id: assignment for assignment in assignments
        }
        if len(profile_by_id) != len(profiles):
            raise ValueError("duplicate road section profile_id values")
        if len(assignment_by_link_id) != len(assignments):
            raise ValueError("duplicate road section link_id assignments")
        missing = sorted(
            {
                assignment.profile_id
                for assignment in assignments
                if assignment.profile_id not in profile_by_id
            }
        )
        if missing:
            raise ValueError(f"section assignments reference missing profiles: {missing}")
        object.__setattr__(self, "profiles", profiles)
        object.__setattr__(self, "assignments", assignments)
        object.__setattr__(self, "_profile_by_id", MappingProxyType(profile_by_id))
        object.__setattr__(
            self,
            "_assignment_by_link_id",
            MappingProxyType(assignment_by_link_id),
        )

    @property
    def fingerprint(self) -> str:
        return _sha256_json(
            {
                "profiles": [
                    {
                        "profile_id": profile.profile_id,
                        "structural_fingerprint": profile.fingerprint,
                    }
                    for profile in self.profiles
                ],
                "assignments": [
                    assignment._canonical_payload() for assignment in self.assignments
                ],
            }
        )

    def profile(self, profile_id: str) -> RoadSectionProfile:
        try:
            return self._profile_by_id[str(profile_id)]
        except KeyError as exc:
            raise KeyError(f"unknown road section profile_id {profile_id!r}") from exc

    def assignment_for_link(self, link_id: int) -> LinkSectionAssignment:
        try:
            return self._assignment_by_link_id[int(link_id)]
        except KeyError as exc:
            raise KeyError(f"no road section assignment for link_id {int(link_id)}") from exc


def compile_road_sections(
    *,
    links: Sequence[_LinkLike],
    road_geometry: RoadGeometryCatalog,
    design_standard: RoadDesignStandard | None = None,
) -> RoadSectionCatalog:
    """Compile profiles while preserving authoritative aggregate link values."""

    design = design_standard if design_standard is not None else RoadDesignStandard()
    if not isinstance(design, RoadDesignStandard):
        raise TypeError("design_standard must be a RoadDesignStandard")
    link_by_id = {
        _strict_nonnegative_int(link.link_id, "link_id"): link for link in links
    }
    if len(link_by_id) != len(links):
        raise ValueError("links must have unique link_id values")
    geometry_link_ids = {assignment.link_id for assignment in road_geometry.assignments}
    link_ids = set(link_by_id)
    extra_geometry_links = sorted(geometry_link_ids - link_ids)
    if extra_geometry_links:
        raise ValueError(
            "road geometry contains assignments for unknown link_id values: "
            f"{extra_geometry_links}"
        )

    links_by_geometry: dict[int, list[_LinkLike]] = {}
    for link in sorted(
        links,
        key=lambda item: _strict_nonnegative_int(item.link_id, "link_id"),
    ):
        link_id = _strict_nonnegative_int(link.link_id, "link_id")
        assignment = road_geometry.assignment_for_link(link_id)
        links_by_geometry.setdefault(assignment.geometry_id, []).append(link)

    profiles: dict[str, RoadSectionProfile] = {}
    assignments: list[LinkSectionAssignment] = []
    for geometry_id in sorted(links_by_geometry):
        physical_links = links_by_geometry[geometry_id]
        forward_link = _link_for_geometry_direction(
            physical_links,
            road_geometry,
            reversed_direction=False,
        )
        backward_link = _link_for_geometry_direction(
            physical_links,
            road_geometry,
            reversed_direction=True,
        )
        forward_lanes = (
            0
            if forward_link is None
            else _strict_nonnegative_int(forward_link.lanes, "lanes")
        )
        backward_lanes = (
            0
            if backward_link is None
            else _strict_nonnegative_int(backward_link.lanes, "lanes")
        )
        representative = forward_link if forward_link is not None else backward_link
        if representative is None:
            raise ValueError(f"geometry_id {geometry_id} has no directed links")
        road_class = str(
            getattr(representative.road_class, "value", representative.road_class)
        )
        roadside = _roadside_profile_for_class(road_class)
        median = bool(
            forward_lanes
            and backward_lanes
            and road_class in {"arterial", "expressway", "bridge"}
        )
        profile_id = (
            f"base:{road_class}:f{forward_lanes}:b{backward_lanes}:"
            f"m{int(median)}:{roadside}"
        )
        section = CarriagewayProfile(
            lane_count_forward=forward_lanes,
            lane_count_backward=backward_lanes,
            median=median,
            roadside_profile=roadside,
        ).to_section_end(design)
        profile = RoadSectionProfile(
            profile_id=profile_id,
            start=section,
            end=section,
            interface_type=SegmentInterfaceType.BASE,
            design_standard=design,
        )
        existing = profiles.get(profile_id)
        if existing is not None and existing.fingerprint != profile.fingerprint:
            raise ValueError(f"profile_id {profile_id!r} has inconsistent structure")
        profiles[profile_id] = profile

        for link in physical_links:
            link_id = _strict_nonnegative_int(link.link_id, "link_id")
            geometry_assignment = road_geometry.assignment_for_link(link_id)
            direction = (
                TravelDirection.BACKWARD
                if geometry_assignment.reversed
                else TravelDirection.FORWARD
            )
            compiled_lane_count = (
                section.lane_count_backward
                if direction is TravelDirection.BACKWARD
                else section.lane_count_forward
            )
            if compiled_lane_count != _strict_nonnegative_int(link.lanes, "lanes"):
                raise ValueError(
                    f"link {link_id} lane count differs from compiled section"
                )
            assignments.append(
                LinkSectionAssignment(
                    link_id=link_id,
                    profile_id=profile_id,
                    direction=direction,
                    lane_count=compiled_lane_count,
                    capacity_veh_per_tick=float(link.capacity_veh_per_tick),
                    total_width_m=section.total_width_m,
                )
            )

    return RoadSectionCatalog(
        profiles=tuple(profiles.values()),
        assignments=tuple(assignments),
    )


def _link_for_geometry_direction(
    links: Sequence[_LinkLike],
    road_geometry: RoadGeometryCatalog,
    *,
    reversed_direction: bool,
) -> _LinkLike | None:
    matches = [
        link
        for link in links
        if road_geometry.assignment_for_link(
            _strict_nonnegative_int(link.link_id, "link_id")
        ).reversed
        is reversed_direction
    ]
    if len(matches) > 1:
        raise ValueError("physical centerline has duplicate directed links")
    return matches[0] if matches else None


def _roadside_profile_for_class(road_class: str) -> str:
    if road_class in {"expressway", "bridge"}:
        return "limited_access"
    if road_class == "ramp":
        return "rural"
    return "urban"


def _strict_nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{field_name} must be an integer")
    converted = int(value)
    if converted < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return converted


def _strict_real(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field_name} must be a real number")
    return float(value)


def _sha256_json(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()
