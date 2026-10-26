"""Finite normalized departure measures; exact interval integration in SI units."""

from dataclasses import dataclass
import math

DAY_S = 86400.0


@dataclass(frozen=True, slots=True)
class DepartureWindow:
    start_s: float
    end_s: float
    probability: float = 1.0

    def __post_init__(self):
        if (
            not all(math.isfinite(x) for x in (self.start_s, self.end_s, self.probability))
            or not 0 <= self.start_s < self.end_s <= DAY_S
            or self.probability <= 0
        ):
            raise ValueError("finite positive departure window inside one day required")


@dataclass(frozen=True, slots=True)
class DepartureProfile:
    windows: tuple[DepartureWindow, ...]

    def __post_init__(self):
        object.__setattr__(self, "windows", tuple(self.windows))
        if not self.windows or abs(math.fsum(w.probability for w in self.windows) - 1.0) > 1e-12:
            raise ValueError("departure window probabilities must sum to one")
        ordered = sorted(self.windows, key=lambda w: w.start_s)
        if any(a.end_s > b.start_s for a, b in zip(ordered, ordered[1:])):
            raise ValueError("overlapping departure windows")

    def fraction(self, start_s, end_s):
        if not all(math.isfinite(t) for t in (start_s, end_s)) or end_s < start_s:
            raise ValueError("finite ordered interval required")
        return math.fsum(
            w.probability
            * max(0.0, min(end_s, w.end_s) - max(start_s, w.start_s))
            / (w.end_s - w.start_s)
            for w in self.windows
        )

    def first_moment_s(self, start_s=0.0, end_s=DAY_S):
        """Integral t dP(t), not the conditional mean of a partial interval."""
        self.fraction(start_s, end_s)
        terms = []
        for w in self.windows:
            lo, hi = max(start_s, w.start_s), min(end_s, w.end_s)
            if hi > lo:
                terms.append(w.probability * (hi - lo) * (hi + lo) / (2 * (w.end_s - w.start_s)))
        return math.fsum(terms)


def daily_profiles(day, purpose):
    """Declared synthetic calendar, not learned travel behaviour."""
    if day not in ("weekday", "weekend") or purpose not in (
        "work",
        "school",
        "service",
        "delivery",
    ):
        raise ValueError("supported day and purpose required")
    hours = (
        ((7.0, 9.0, 17.0, 19.0) if purpose == "work" else (10.0, 11.0, 13.0, 14.0))
        if day == "weekday"
        else ((9.0, 10.0, 14.0, 15.0) if purpose == "work" else (10.0, 12.0, 16.0, 18.0))
    )
    if purpose == "school":
        hours = (8.0, 9.0, 15.0, 16.0) if day == "weekday" else (10.0, 11.0, 14.0, 15.0)
    if purpose == "delivery":
        return DepartureProfile(
            (DepartureWindow(9 * 3600, 10 * 3600, 0.6), DepartureWindow(15 * 3600, 16 * 3600, 0.4))
        ), None
    a, b, c, d = hours
    return DepartureProfile((DepartureWindow(a * 3600, b * 3600),)), DepartureProfile(
        (DepartureWindow(c * 3600, d * 3600),)
    )
