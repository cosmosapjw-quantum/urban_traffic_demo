"""Behavioral tests for the deterministic correlated development field."""

from __future__ import annotations

import math

import pytest

from metroflow.city.development_field import (
    DevelopmentFieldConfig,
    DeterministicDevelopmentField,
)


def _correlation(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    assert len(left) == len(right) and len(left) > 1
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right, strict=True)
    )
    left_norm = math.sqrt(sum((value - left_mean) ** 2 for value in left))
    right_norm = math.sqrt(sum((value - right_mean) ** 2 for value in right))
    return numerator / (left_norm * right_norm)


def test_value_and_gradient_replay_bit_identically_for_fixed_seed_and_metres() -> None:
    """Break caught: field queries depend on process-local or traversal state."""
    config = DevelopmentFieldConfig(correlation_length_m=400.0, amplitude=0.28)
    first = DeterministicDevelopmentField(seed=701, config=config)
    second = DeterministicDevelopmentField(seed=701, config=config)

    point = (1_250.0, -875.0)
    assert first.value_at(*point) == second.value_at(*point)
    assert first.gradient_at(*point) == second.gradient_at(*point)
    assert first.fingerprint == second.fingerprint


def test_short_separation_has_stronger_spatial_autocorrelation_than_long_separation() -> None:
    """Break caught: implementation degenerates to independent coordinate hash noise."""
    field = DeterministicDevelopmentField(
        seed=503,
        config=DevelopmentFieldConfig(correlation_length_m=500.0, amplitude=0.30),
    )
    x_values = tuple(float(index * 175) for index in range(32))
    base = tuple(field.value_at(x_m, 0.0) for x_m in x_values)
    nearby = tuple(field.value_at(x_m, 125.0) for x_m in x_values)
    distant = tuple(field.value_at(x_m, 2_000.0) for x_m in x_values)

    assert _correlation(base, nearby) > _correlation(base, distant)


def test_query_order_does_not_change_any_replayed_field_value() -> None:
    """Break caught: a cache or mutable octave state leaks evaluation order."""
    field = DeterministicDevelopmentField(seed=907)
    points = tuple((float(index * 125), float(index * -75)) for index in range(16))
    forward = {point: field.value_at(*point) for point in points}
    reverse = {point: field.value_at(*point) for point in reversed(points)}

    assert reverse == forward


def test_invalid_field_units_and_amplitude_fail_closed() -> None:
    """Break caught: non-metre or non-finite field parameters silently enter replay."""
    with pytest.raises(ValueError, match="correlation_length_m"):
        DevelopmentFieldConfig(correlation_length_m=0.0, amplitude=0.2)
    with pytest.raises(ValueError, match="amplitude"):
        DevelopmentFieldConfig(correlation_length_m=250.0, amplitude=1.1)
