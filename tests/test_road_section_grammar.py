from __future__ import annotations

import math

import pytest


def _lane(direction="forward", width_m=3.5):
    from metroflow.map.lane_grammar import RoadSectionUnit, RoadUnitKind

    return RoadSectionUnit(RoadUnitKind.LANE, width_m, direction)


def test_carriageway_profile_compiles_explicit_meter_units() -> None:
    from metroflow.map.lane_grammar import (
        CarriagewayProfile,
        RoadDesignStandard,
        RoadUnitKind,
    )

    standard = RoadDesignStandard(lane_width_m=3.5, median_width_m=1.2)
    section = CarriagewayProfile(
        lane_count_forward=2,
        lane_count_backward=1,
        median=True,
    ).to_section_end(standard)

    assert section.lane_count_forward == 2
    assert section.lane_count_backward == 1
    assert section.total_width_m == pytest.approx((3 * 3.5) + 1.2 + (2 * 2.0))
    assert [unit.kind for unit in section.units].count(RoadUnitKind.SIDEWALK) == 2
    assert [unit.kind for unit in section.units].count(RoadUnitKind.MEDIAN) == 1


def test_road_section_units_fail_closed_on_direction_and_width() -> None:
    from metroflow.map.lane_grammar import RoadSectionUnit, RoadUnitKind

    with pytest.raises(ValueError, match="travel direction"):
        RoadSectionUnit(RoadUnitKind.LANE, 3.5, "none")
    with pytest.raises(ValueError, match="must not have a travel direction"):
        RoadSectionUnit(RoadUnitKind.MEDIAN, 1.0, "forward")
    with pytest.raises(ValueError, match="width_m"):
        RoadSectionUnit(RoadUnitKind.SHOULDER, 0.0)
    with pytest.raises(ValueError, match="finite"):
        RoadSectionUnit(RoadUnitKind.SHOULDER, math.inf)


def test_base_and_shift_profiles_enforce_distinct_invariants() -> None:
    from metroflow.map.lane_grammar import (
        RoadSectionEnd,
        RoadSectionProfile,
        SegmentInterfaceType,
    )

    section = RoadSectionEnd((_lane("backward"), _lane("forward")))
    base = RoadSectionProfile(
        profile_id="base-2",
        start=section,
        end=section,
        interface_type=SegmentInterfaceType.BASE,
    )
    shift = RoadSectionProfile(
        profile_id="shift-2",
        start=section,
        end=section,
        interface_type=SegmentInterfaceType.SHIFT,
        end_center_offset_m=3.5,
    )

    assert base.fingerprint != shift.fingerprint
    with pytest.raises(ValueError, match="BASE"):
        RoadSectionProfile(
            profile_id="bad-base",
            start=section,
            end=section,
            interface_type="base",
            end_center_offset_m=1.0,
        )
    with pytest.raises(ValueError, match="SHIFT"):
        RoadSectionProfile(
            profile_id="bad-shift",
            start=section,
            end=section,
            interface_type="shift",
            end_center_offset_m=7.1,
        )


def test_transition_and_ramp_profiles_validate_lane_delta_and_channel() -> None:
    from metroflow.map.lane_grammar import (
        RoadSectionEnd,
        RoadSectionProfile,
        RoadSectionUnit,
        RoadUnitKind,
    )

    one_lane = RoadSectionEnd((_lane(),))
    two_lane = RoadSectionEnd((_lane(), _lane()))
    ramp_end = RoadSectionEnd(
        (
            _lane(),
            RoadSectionUnit(RoadUnitKind.CHANNEL, 1.0),
            _lane(),
        )
    )

    transition = RoadSectionProfile("transition", one_lane, two_lane, "transition")
    ramp = RoadSectionProfile("ramp", one_lane, ramp_end, "ramp")

    assert transition.end.lane_count_forward == 2
    assert ramp.interface_type.value == "ramp"
    with pytest.raises(ValueError, match="exactly one lane"):
        RoadSectionProfile("bad-transition", one_lane, one_lane, "transition")
    with pytest.raises(ValueError, match="lane and CHANNEL"):
        RoadSectionProfile("bad-ramp", one_lane, two_lane, "ramp")

    direction_swap = RoadSectionEnd(
        (_lane("backward"), _lane(), _lane(), _lane())
    )
    two_way = RoadSectionEnd((_lane("backward"), _lane()))
    with pytest.raises(ValueError, match="one travel direction"):
        RoadSectionProfile("bad-direction-swap", two_way, direction_swap, "transition")

    changed_roadside = RoadSectionEnd(
        (
            RoadSectionUnit(RoadUnitKind.SHOULDER, 1.5),
            _lane(),
            _lane(),
        )
    )
    with pytest.raises(ValueError, match="ordered lane insertion"):
        RoadSectionProfile("bad-roadside", one_lane, changed_roadside, "transition")

    channel_on_narrow_end = RoadSectionEnd(
        (RoadSectionUnit(RoadUnitKind.CHANNEL, 1.0), _lane())
    )
    with pytest.raises(ValueError, match="lane and CHANNEL"):
        RoadSectionProfile("bad-channel-side", channel_on_narrow_end, two_lane, "ramp")


def test_interface_edits_preserve_order_width_and_existing_channels() -> None:
    from metroflow.map.lane_grammar import (
        RoadSectionEnd,
        RoadSectionProfile,
        RoadSectionUnit,
        RoadUnitKind,
    )

    sidewalk = RoadSectionUnit(RoadUnitKind.SIDEWALK, 2.0)
    start = RoadSectionEnd((sidewalk, _lane()))
    moved_sidewalk = RoadSectionEnd((_lane(), _lane(), sidewalk))
    with pytest.raises(ValueError, match="ordered lane insertion"):
        RoadSectionProfile("moved-sidewalk", start, moved_sidewalk, "transition")

    two_way = RoadSectionEnd((_lane("backward"), _lane()))
    changed_backward_width = RoadSectionEnd(
        (_lane("backward", 3.2), _lane(), _lane())
    )
    with pytest.raises(ValueError, match="ordered lane insertion"):
        RoadSectionProfile(
            "changed-unchanged-direction",
            two_way,
            changed_backward_width,
            "transition",
        )

    channel = RoadSectionUnit(RoadUnitKind.CHANNEL, 1.0)
    ramp_start = RoadSectionEnd((_lane(), channel))
    changed_channel = RoadSectionEnd(
        (_lane(), RoadSectionUnit(RoadUnitKind.CHANNEL, 0.8), _lane())
    )
    with pytest.raises(ValueError, match="lane and CHANNEL"):
        RoadSectionProfile("changed-channel", ramp_start, changed_channel, "ramp")


def test_section_profile_fingerprint_is_deterministic_and_normalizes_zero() -> None:
    from metroflow.map.lane_grammar import RoadSectionEnd, RoadSectionProfile

    section = RoadSectionEnd((_lane(),))
    first = RoadSectionProfile(
        "one-way",
        section,
        section,
        "base",
        start_center_offset_m=-0.0,
    )
    second = RoadSectionProfile(
        "one-way",
        section,
        section,
        "base",
        start_center_offset_m=0.0,
    )

    assert first.fingerprint == second.fingerprint
    assert len(first.fingerprint) == 64
    renamed = RoadSectionProfile("renamed", section, section, "base")
    assert renamed.fingerprint == first.fingerprint
    assert renamed.identity_fingerprint != first.identity_fingerprint


def test_road_section_end_requires_at_least_one_lane() -> None:
    from metroflow.map.lane_grammar import RoadSectionEnd, RoadSectionUnit, RoadUnitKind

    with pytest.raises(ValueError, match="at least one lane"):
        RoadSectionEnd((RoadSectionUnit(RoadUnitKind.SIDEWALK, 2.0),))


@pytest.mark.parametrize("lane_count", (1.9, "2", math.inf, True))
def test_carriageway_profile_rejects_coercive_lane_counts(lane_count) -> None:
    from metroflow.map.lane_grammar import CarriagewayProfile

    with pytest.raises(ValueError, match="nonnegative integer"):
        CarriagewayProfile(lane_count, 0)


def test_carriageway_profile_rejects_non_boolean_median() -> None:
    from metroflow.map.lane_grammar import CarriagewayProfile

    with pytest.raises(ValueError, match="median must be a bool"):
        CarriagewayProfile(1, 0, median="false")


def test_invalid_numeric_widths_raise_value_error() -> None:
    from metroflow.map.lane_grammar import RoadDesignStandard, RoadSectionUnit, RoadUnitKind

    with pytest.raises(ValueError, match="real number"):
        RoadSectionUnit(RoadUnitKind.SHOULDER, None)
    with pytest.raises(ValueError, match="real number"):
        RoadDesignStandard(lane_width_m=None)


@pytest.mark.parametrize(
    "invalid",
    ("1.5", True, 10**10000),
    ids=("numeric-string", "boolean", "overflowing-integer"),
)
def test_widths_and_offsets_reject_coercive_numeric_values(invalid) -> None:
    from metroflow.map.lane_grammar import (
        RoadDesignStandard,
        RoadSectionEnd,
        RoadSectionProfile,
        RoadSectionUnit,
        RoadUnitKind,
    )

    with pytest.raises(ValueError, match="real number"):
        RoadSectionUnit(RoadUnitKind.SHOULDER, invalid)
    with pytest.raises(ValueError, match="real number"):
        RoadDesignStandard(lane_width_m=invalid)
    section = RoadSectionEnd((_lane(),))
    with pytest.raises(ValueError, match="real number"):
        RoadSectionProfile(
            "invalid-offset",
            section,
            section,
            "base",
            start_center_offset_m=invalid,
        )
