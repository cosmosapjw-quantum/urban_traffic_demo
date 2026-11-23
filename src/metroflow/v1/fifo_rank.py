"""Conditional FIFO rank adapter for an existing homogeneous packet.

This is not a traffic engine. It preserves source label order and entry metadata;
the caller supplies the existing physical eligibility frontier and service law.
Fraction/int input uses exact arithmetic. Binary64 input is a collapsed-rank
representation, not the original repeated-multiplication IEEE operation order.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
import math
from typing import Iterator

Number = int | float | Fraction


class RankDomainError(ValueError):
    """Source or service violates the stated physical domain."""


class RankPrecisionError(ArithmeticError):
    """A positive service cannot be represented by the binary64 rank."""


def _number(value: Number, name: str) -> Number:
    if isinstance(value, bool) or not isinstance(value, (int, float, Fraction)):
        raise RankDomainError(f"{name} must be an int, Fraction or float")
    if isinstance(value, float) and not math.isfinite(value):
        raise RankDomainError(f"{name} must be finite")
    return value


@dataclass(frozen=True, slots=True)
class SourceRow:
    tag: int
    offset: int
    mass: Number
    birth: Number
    a: Number | None = None
    b: Number | None = None

    def __post_init__(self) -> None:
        for name, value in (("tag", self.tag), ("offset", self.offset)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RankDomainError(f"{name} must be a nonnegative integer")
        _number(self.mass, "mass")
        _number(self.birth, "birth")
        if self.mass < 0 or self.birth < 0:
            raise RankDomainError("mass and birth first moment must be nonnegative")
        if self.mass == 0 and self.birth != 0:
            raise RankDomainError("zero mass cannot carry a nonzero birth moment")
        if (self.a is None) != (self.b is None):
            raise RankDomainError("entry interval endpoints must be both present or absent")
        if self.a is not None:
            _number(self.a, "entry a")
            _number(self.b, "entry b")
            if self.a > self.b:
                raise RankDomainError("entry interval must satisfy a <= b")


@dataclass(frozen=True, slots=True)
class CompositionRoot:
    rows: tuple[SourceRow, ...]
    total_mass: Number = field(init=False)
    exact: bool = field(init=False)

    def __post_init__(self) -> None:
        rows = tuple(self.rows)
        if not rows or any(not isinstance(row, SourceRow) for row in rows):
            raise RankDomainError("a root requires nonempty SourceRow input")
        exact = all(not isinstance(v, float) for row in rows for v in (row.mass, row.birth))
        try:
            total = (sum((Fraction(row.mass) for row in rows), Fraction(0))
                     if exact else math.fsum(float(row.mass) for row in rows))
        except (OverflowError, ValueError) as exc:
            raise RankDomainError("source total is not representable") from exc
        if total <= 0 or (not exact and not math.isfinite(total)):
            raise RankDomainError("source total mass must be positive and finite")
        object.__setattr__(self, "rows", rows)
        object.__setattr__(self, "total_mass", total)
        object.__setattr__(self, "exact", exact)

    @classmethod
    def from_rows(cls, rows) -> "CompositionRoot":
        return cls(tuple(rows))

    def scalar(self, value: Number, name: str) -> Number:
        _number(value, name)
        if self.exact:
            # A float would silently change the promised exact domain.
            if isinstance(value, float):
                raise RankDomainError(f"{name}: use Fraction/int with an exact root")
            return Fraction(value)
        try:
            converted = float(value)
        except OverflowError as exc:
            raise RankDomainError(f"{name} is not representable") from exc
        if not math.isfinite(converted):
            raise RankDomainError(f"{name} must be finite")
        if value > 0 and converted == 0:
            raise RankPrecisionError(f"{name}: positive input underflow")
        return converted


@dataclass(frozen=True, slots=True)
class RankSpan:
    root: CompositionRoot
    lo: Number
    hi: Number

    def __post_init__(self) -> None:
        if not isinstance(self.root, CompositionRoot):
            raise RankDomainError("span root is not a CompositionRoot")
        lo = self.root.scalar(self.lo, "lo")
        hi = self.root.scalar(self.hi, "hi")
        if not 0 <= lo <= hi <= self.root.total_mass:
            raise RankDomainError("span must satisfy 0 <= lo <= hi <= root mass")
        object.__setattr__(self, "lo", lo)
        object.__setattr__(self, "hi", hi)

    @classmethod
    def full(cls, root: CompositionRoot) -> "RankSpan":
        return cls(root, 0, root.total_mass)

    @classmethod
    def from_rows(cls, rows) -> "RankSpan":
        return cls.full(CompositionRoot.from_rows(rows))

    @property
    def mass(self) -> Number:
        return self.hi - self.lo

    def iter_rows(self) -> Iterator[SourceRow]:
        """Expand only when a legacy consumer requests rows; split itself never does."""
        scale = self.mass / self.root.total_mass
        if self.mass > 0 and scale == 0:
            raise RankPrecisionError("positive span scale underflows")
        for row in self.root.rows:
            mass, birth = row.mass * scale, row.birth * scale
            if scale > 0 and ((row.mass > 0 and mass == 0) or (row.birth > 0 and birth == 0)):
                raise RankPrecisionError("positive source row moment underflows span scale")
            yield SourceRow(row.tag, row.offset, mass, birth,
                            row.a, row.b)

    def take_mass(self, amount: Number, eligible_rank: Number) -> "RankSplit":
        amount = self.root.scalar(amount, "service amount")
        eligible = self.root.scalar(eligible_rank, "eligible rank")
        if not self.lo <= eligible <= self.root.total_mass:
            raise RankDomainError("eligible frontier precedes consumed rank or exceeds source")
        available = min(self.hi, eligible) - self.lo
        if not 0 <= amount <= available:
            raise RankDomainError("service amount exceeds eligible FIFO mass")
        if amount == 0:
            cut = self.lo
        elif amount == self.mass:
            cut = self.hi
        else:
            cut = self.lo + amount
            if cut == self.lo:
                raise RankPrecisionError("positive service is smaller than the rank resolution")
            if cut >= self.hi:
                raise RankPrecisionError("positive unserved remainder is below rank resolution")
        if cut > eligible:
            raise RankPrecisionError("rounding would cross the physical eligibility frontier")
        realized = cut - self.lo
        return RankSplit(RankSpan(self.root, self.lo, cut),
                         RankSpan(self.root, cut, self.hi),
                         amount, realized, realized - amount)

    def take_fraction(self, fraction: Number, eligible_rank: Number) -> "RankSplit":
        fraction = self.root.scalar(fraction, "source service fraction")
        if not 0 <= fraction <= 1:
            raise RankDomainError("source service fraction must be in [0,1]")
        amount = fraction * self.mass
        if fraction > 0 and self.mass > 0 and amount == 0:
            raise RankPrecisionError("positive source fraction underflows service mass")
        if fraction < 1 and self.mass > 0 and amount == self.mass:
            raise RankPrecisionError("positive unserved source fraction is not representable")
        return self.take_mass(amount, eligible_rank)

    def moments_by_key(self) -> dict[tuple[int, int], tuple[Number, Number]]:
        values: dict[tuple[int, int], list[tuple[Number, Number]]] = {}
        for row in self.iter_rows():
            values.setdefault((row.tag, row.offset), []).append((row.mass, row.birth))
        add = (lambda xs: sum(xs, Fraction(0))) if self.root.exact else math.fsum
        return {key: (add(v[0] for v in rows), add(v[1] for v in rows))
                for key, rows in values.items()}


@dataclass(frozen=True, slots=True)
class RankSplit:
    served: RankSpan
    remainder: RankSpan
    requested_mass: Number
    realized_mass: Number
    roundoff_mass: Number


def prefix_error_bound(block_mass: Number, commodity_fraction: Number) -> Number:
    """Sharp h*p*(1-p) bound for fixed-block scalar commodity prefixes.

    This is not a coupled-network trajectory or derivative error estimate.
    """
    h = _number(block_mass, "block mass")
    p = _number(commodity_fraction, "commodity fraction")
    if h < 0 or not 0 <= p <= 1:
        raise RankDomainError("require h >= 0 and 0 <= p <= 1")
    return h * p * (1 - p)


def prefix_envelope(block_mass: Number, commodity_mass: Number, prefix_mass: Number):
    """Return (lower, upper, uniform_approximation, sharp_error_bound)."""
    h, m, x = (_number(block_mass, "block mass"),
               _number(commodity_mass, "commodity mass"),
               _number(prefix_mass, "prefix mass"))
    if not 0 <= m <= h or not 0 <= x <= h:
        raise RankDomainError("require 0 <= m,x <= h")
    if h == 0:
        return (0, 0, 0, 0)
    exact = not any(isinstance(v, float) for v in (h, m, x))
    p = Fraction(m) / Fraction(h) if exact else m / h
    return max(0, m - (h - x)), min(m, x), p * x, prefix_error_bound(h, p)
