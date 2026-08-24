"""Deterministic metre-scale correlated development intensity field.

This is a project-owned synthetic field, not calibrated terrain or observed
development data.  A seeded integer lattice is interpolated with a quintic
kernel, giving fixed spatial correlation length and analytic gradients.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math

FIELD_SCHEMA_VERSION = "development_field_v1"


@dataclass(frozen=True, slots=True)
class DevelopmentFieldConfig:
    """Frozen field parameters in metres and dimensionless intensity units."""

    correlation_length_m: float = 400.0
    amplitude: float = 0.28

    def __post_init__(self) -> None:
        correlation_length_m = float(self.correlation_length_m)
        amplitude = float(self.amplitude)
        if not math.isfinite(correlation_length_m) or correlation_length_m <= 0.0:
            raise ValueError("correlation_length_m must be finite and positive")
        if not math.isfinite(amplitude) or not 0.0 < amplitude <= 0.5:
            raise ValueError("amplitude must be finite and in (0, 0.5]")
        object.__setattr__(self, "correlation_length_m", correlation_length_m)
        object.__setattr__(self, "amplitude", amplitude)


DEFAULT_DEVELOPMENT_FIELD_CONFIG = DevelopmentFieldConfig()


@dataclass(frozen=True, slots=True)
class DeterministicDevelopmentField:
    """Replay-stable correlated scalar field with values and metre gradients."""

    seed: int
    config: DevelopmentFieldConfig = DEFAULT_DEVELOPMENT_FIELD_CONFIG
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise TypeError("seed must be an integer")
        if type(self.config) is not DevelopmentFieldConfig:
            raise TypeError("config must be an exact DevelopmentFieldConfig")
        payload = {
            "schema_version": FIELD_SCHEMA_VERSION,
            "seed": self.seed,
            "correlation_length_m": self.config.correlation_length_m,
            "amplitude": self.config.amplitude,
        }
        object.__setattr__(
            self,
            "fingerprint",
            hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        )

    def _lattice_value(self, x_index: int, y_index: int) -> float:
        payload = f"{FIELD_SCHEMA_VERSION}:{self.seed}:{x_index}:{y_index}".encode()
        raw = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
        return raw / 9_223_372_036_854_775_807.5 - 1.0

    def value_at(self, x_m: float, y_m: float) -> float:
        value, _gradient_x, _gradient_y = self._value_and_gradient(x_m, y_m)
        return value

    def gradient_at(self, x_m: float, y_m: float) -> tuple[float, float]:
        _value, gradient_x, gradient_y = self._value_and_gradient(x_m, y_m)
        return (gradient_x, gradient_y)

    def intensity_at(self, x_m: float, y_m: float) -> float:
        return 0.4 + self.config.amplitude * self.value_at(x_m, y_m)

    def _value_and_gradient(self, x_m: float, y_m: float) -> tuple[float, float, float]:
        x_m = float(x_m)
        y_m = float(y_m)
        if not math.isfinite(x_m) or not math.isfinite(y_m):
            raise ValueError("field coordinates must be finite metres")
        length = self.config.correlation_length_m
        x_index = math.floor(x_m / length)
        y_index = math.floor(y_m / length)
        x_fraction = x_m / length - x_index
        y_fraction = y_m / length - y_index
        x_weight = _quintic(x_fraction)
        y_weight = _quintic(y_fraction)
        x_derivative = _quintic_derivative(x_fraction) / length
        y_derivative = _quintic_derivative(y_fraction) / length
        lower_left = self._lattice_value(x_index, y_index)
        lower_right = self._lattice_value(x_index + 1, y_index)
        upper_left = self._lattice_value(x_index, y_index + 1)
        upper_right = self._lattice_value(x_index + 1, y_index + 1)
        lower = lower_left + x_weight * (lower_right - lower_left)
        upper = upper_left + x_weight * (upper_right - upper_left)
        value = lower + y_weight * (upper - lower)
        gradient_x = x_derivative * (
            (lower_right - lower_left)
            + y_weight * ((upper_right - upper_left) - (lower_right - lower_left))
        )
        gradient_y = y_derivative * (upper - lower)
        return (round(value, 15), round(gradient_x, 18), round(gradient_y, 18))


def _quintic(value: float) -> float:
    return value * value * value * (value * (value * 6.0 - 15.0) + 10.0)


def _quintic_derivative(value: float) -> float:
    return 30.0 * value * value * (value - 1.0) * (value - 1.0)
