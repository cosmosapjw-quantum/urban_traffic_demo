"""Exact marked FIFO rank profiles and a conservative multi-input merge.

Research representation only: no Rust solver, f64-operation or checkpoint-wire
equivalence is claimed. Mass is veh, clocks s, birth/exit moments veh*s, readiness
targets m. Marks retain every route/class/observation distinction needed by a
consumer. Unknown boundary/readiness metadata fail closed when requested.

Profiles are immutable flat parents; views share their parent and retain all
internal heterogeneous knots. Merge intentionally materializes its true output
profile. It therefore exposes repeated-merge growth rather than hiding it in an
unbounded lazy DAG. Existing single-source prefix/inverse theory is reused.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from fractions import Fraction as F
from typing import Callable, Iterable, Iterator, Sequence

Number = int | F
Boundary = tuple[F, F]
ZERO = F(0)


def _q(value: Number) -> F:
    if isinstance(value, bool) or not isinstance(value, (int, F)):
        raise TypeError("exact Fraction or int required; floating input is not implicit")
    return F(value)


@dataclass(frozen=True, slots=True)
class MarkedMass:
    mark: str
    mass: F
    birth_moment: F

    def __post_init__(self) -> None:
        if not isinstance(self.mark, str) or not self.mark:
            raise ValueError("nonempty string mark required")
        mass, birth = _q(self.mass), _q(self.birth_moment)
        if mass < 0 or (mass == 0 and birth != 0):
            raise ValueError("negative mass or nonzero birth moment on zero mass")
        object.__setattr__(self, "mass", mass)
        object.__setattr__(self, "birth_moment", birth)


@dataclass(frozen=True, slots=True)
class RankSegment:
    parts: tuple[MarkedMass, ...]
    ready_target: F | None = None
    boundary: Boundary | None = None
    mass: F = field(init=False)

    def __post_init__(self) -> None:
        totals: dict[str, tuple[F, F]] = {}
        for part in self.parts:
            if not isinstance(part, MarkedMass):
                raise TypeError("RankSegment requires MarkedMass components")
            m, b = totals.get(part.mark, (ZERO, ZERO))
            totals[part.mark] = (m + part.mass, b + part.birth_moment)
        parts = tuple(MarkedMass(mark, m, b) for mark, (m, b) in sorted(totals.items()) if m)
        total = sum((p.mass for p in parts), ZERO)
        if total <= 0:
            raise ValueError("nonpositive rank segment")
        object.__setattr__(self, "parts", parts)
        object.__setattr__(self, "mass", total)
        if self.ready_target is not None:
            object.__setattr__(self, "ready_target", _q(self.ready_target))
        if self.boundary is not None:
            if len(self.boundary) != 2:
                raise ValueError("boundary needs two endpoints")
            a, b = map(_q, self.boundary)
            if b < a:
                raise ValueError("reversed boundary interval")
            object.__setattr__(self, "boundary", (a, b))


def _same_law(left: RankSegment, right: RankSegment) -> bool:
    """Exact adjacent affine-law identity, never heterogeneous averaging."""
    if left.ready_target != right.ready_target or len(left.parts) != len(right.parts):
        return False
    for a, b in zip(left.parts, right.parts):
        if a.mark != b.mark:
            return False
        if a.mass * right.mass != b.mass * left.mass:
            return False
        if a.birth_moment * right.mass != b.birth_moment * left.mass:
            return False
    if left.boundary is None or right.boundary is None:
        return left.boundary is None and right.boundary is None
    a, b = left.boundary
    c, d = right.boundary
    return b == c and (b - a) * right.mass == (d - c) * left.mass


def _coalesce_exact(segments: Iterable[RankSegment]) -> tuple[RankSegment, ...]:
    result: list[RankSegment] = []
    for segment in segments:
        if result and _same_law(result[-1], segment):
            previous = result.pop()
            parts = tuple(
                MarkedMass(a.mark, a.mass + b.mass, a.birth_moment + b.birth_moment)
                for a, b in zip(previous.parts, segment.parts)
            )
            boundary = None if previous.boundary is None else (
                previous.boundary[0], segment.boundary[1]  # type: ignore[index]
            )
            result.append(RankSegment(parts, previous.ready_target, boundary))
        else:
            result.append(segment)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class RankProfile:
    segments: tuple[RankSegment, ...]
    _ends: tuple[F, ...] = field(init=False, repr=False)
    mass: F = field(init=False)

    def __post_init__(self) -> None:
        segments = tuple(self.segments)
        ends: list[F] = []
        total = ZERO
        previous_target: F | None = None
        previous_boundary_end: F | None = None
        for segment in segments:
            if not isinstance(segment, RankSegment):
                raise TypeError("RankProfile requires RankSegment objects")
            if segment.ready_target is not None:
                if previous_target is not None and segment.ready_target < previous_target:
                    raise ValueError("ready targets must be nondecreasing")
                previous_target = segment.ready_target
            if segment.boundary is not None:
                if previous_boundary_end is not None and segment.boundary[0] < previous_boundary_end:
                    raise ValueError("boundary intervals must preserve FIFO order")
                previous_boundary_end = segment.boundary[1]
            total += segment.mass
            ends.append(total)
        object.__setattr__(self, "segments", segments)
        object.__setattr__(self, "_ends", tuple(ends))
        object.__setattr__(self, "mass", total)

    def view(self, start: Number = 0, end: Number | None = None) -> RankView:
        return RankView(self, _q(start), self.mass if end is None else _q(end))

    def ready_prefix(self, displacement: Number) -> F:
        """Ready mass in the declared monotone target profile; no motion solver."""
        value = _q(displacement)
        if any(s.ready_target is None for s in self.segments):
            raise ValueError("readiness metadata unknown")
        ready = ZERO
        for segment in self.segments:
            if segment.ready_target > value:  # type: ignore[operator]
                break
            ready += segment.mass
        return ready

    @property
    def essential_segments(self) -> int:
        """Minimal neighboring affine-law count in this stored flat profile."""
        if not self.segments:
            return 0
        return 1 + sum(
            not _same_law(a, b) for a, b in zip(self.segments, self.segments[1:])
        )


@dataclass(frozen=True, slots=True)
class ProfilePiece:
    segment: RankSegment
    segment_start: F
    start: F
    end: F

    @property
    def mass(self) -> F:
        return self.end - self.start

    @property
    def parts(self) -> tuple[MarkedMass, ...]:
        fraction = self.mass / self.segment.mass
        return tuple(
            MarkedMass(p.mark, p.mass * fraction, p.birth_moment * fraction)
            for p in self.segment.parts
        )

    @property
    def boundary(self) -> Boundary | None:
        interval = self.segment.boundary
        if interval is None:
            return None
        first, last = interval
        slope = (last - first) / self.segment.mass
        return (
            first + (self.start - self.segment_start) * slope,
            first + (self.end - self.segment_start) * slope,
        )

    @property
    def ready_target(self) -> F | None:
        return self.segment.ready_target


@dataclass(frozen=True, slots=True)
class RankView:
    profile: RankProfile
    start: F
    end: F

    def __post_init__(self) -> None:
        start, end = _q(self.start), _q(self.end)
        if not 0 <= start <= end <= self.profile.mass:
            raise ValueError("rank view outside parent")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    @property
    def mass(self) -> F:
        return self.end - self.start

    def subview(self, start: Number = 0, end: Number | None = None) -> RankView:
        first = _q(start)
        last = self.mass if end is None else _q(end)
        if not 0 <= first <= last <= self.mass:
            raise ValueError("relative view outside source")
        return RankView(self.profile, self.start + first, self.start + last)

    def iter_pieces(self) -> Iterator[ProfilePiece]:
        """Traverse actual semantic knots inside this view, without Part copies."""
        index = bisect_right(self.profile._ends, self.start)
        while index < len(self.profile.segments):
            left = ZERO if index == 0 else self.profile._ends[index - 1]
            right = self.profile._ends[index]
            if left >= self.end:
                break
            a, b = max(self.start, left), min(self.end, right)
            if a < b:
                yield ProfilePiece(self.profile.segments[index], left, a, b)
            index += 1

    def moments(self) -> dict[str, tuple[F, F]]:
        totals: dict[str, tuple[F, F]] = {}
        for piece in self.iter_pieces():
            fraction = piece.mass / piece.segment.mass
            for p in piece.segment.parts:
                m, b = totals.get(p.mark, (ZERO, ZERO))
                totals[p.mark] = (
                    m + p.mass * fraction, b + p.birth_moment * fraction
                )
        return totals


def concat_adjacent(views: Sequence[RankView]) -> RankView:
    if not views:
        raise ValueError("at least one view required")
    first = views[0]
    previous = first.end
    for view in views[1:]:
        if view.profile is not first.profile or view.start != previous:
            raise ValueError("only contiguous views of the same parent concatenate")
        previous = view.end
    return RankView(first.profile, first.start, previous)


@dataclass(frozen=True, slots=True)
class ServiceWindow:
    start: F
    end: F
    rate: F

    def __post_init__(self) -> None:
        first, last, rate = map(_q, (self.start, self.end, self.rate))
        if last <= first or rate < 0:
            raise ValueError("invalid service window or negative rate")
        object.__setattr__(self, "start", first)
        object.__setattr__(self, "end", last)
        object.__setattr__(self, "rate", rate)


@dataclass(frozen=True, slots=True)
class TimedView:
    view: RankView
    start: F
    end: F

    def __post_init__(self) -> None:
        first, last = _q(self.start), _q(self.end)
        if last <= first or self.view.mass <= 0:
            raise ValueError("TimedView needs positive time and served mass")
        object.__setattr__(self, "start", first)
        object.__setattr__(self, "end", last)

    @property
    def rate(self) -> F:
        return self.view.mass / (self.end - self.start)


def serve_windows(
    view: RankView,
    schedule: Iterable[ServiceWindow],
    *,
    require_complete: bool = False,
) -> tuple[TimedView, ...]:
    """Restrict prescribed FIFO service; it does not solve capacity/readiness."""
    result: list[TimedView] = []
    cursor = ZERO
    previous_end: F | None = None
    for window in schedule:
        if previous_end is not None and window.start < previous_end:
            raise ValueError("overlapping or reversed service schedule")
        previous_end = window.end
        amount = window.rate * (window.end - window.start)
        if cursor + amount > view.mass:
            raise ValueError("service exceeds available source mass")
        if amount:
            result.append(TimedView(
                view.subview(cursor, cursor + amount), window.start, window.end
            ))
        cursor += amount
    if require_complete and cursor != view.mass:
        raise ValueError("incomplete service")
    return tuple(result)


@dataclass(frozen=True, slots=True)
class MarkTransport:
    mark: str
    mass: F
    birth_moment: F
    exit_moment: F

    @property
    def residence(self) -> F:
        return self.exit_moment - self.birth_moment


@dataclass(frozen=True, slots=True)
class TransportMoments:
    marks: tuple[MarkTransport, ...]
    boundary_checked: bool
    readiness_checked: bool

    def as_dict(self) -> dict[str, MarkTransport]:
        return {item.mark: item for item in self.marks}


def transport_moments(
    slices: Iterable[TimedView],
    *,
    displacement: Callable[[F], Number] | None = None,
    check_boundary: bool = True,
) -> TransportMoments:
    """Integrate exit moments at all semantic knots.

    With displacement supplied, caller declares a nondecreasing motion clock;
    every served piece must already be ready at its first exit. Without that
    clock readiness is explicitly unchecked. Boundary causality is affine on
    each piece and checked at both endpoints. Missing requested metadata errors.
    """
    totals: dict[str, tuple[F, F, F]] = {}
    previous_end: F | None = None
    previous_view: RankView | None = None
    previous_displacement: F | None = None
    for timed in slices:
        if previous_end is not None and timed.start < previous_end:
            raise ValueError("transport slices overlap in time")
        if previous_view is not None and (
            timed.view.profile is not previous_view.profile
            or timed.view.start != previous_view.end
        ):
            raise ValueError("transport slices must be one contiguous FIFO stream")
        rate = timed.rate
        for piece in timed.view.iter_pieces():
            first = timed.start + (piece.start - timed.view.start) / rate
            last = timed.start + (piece.end - timed.view.start) / rate
            boundary = piece.boundary
            if check_boundary:
                if boundary is None:
                    raise ValueError("boundary metadata unknown")
                if first < boundary[0] or last < boundary[1]:
                    raise ValueError("service precedes declared boundary arrival")
            if displacement is not None:
                if piece.ready_target is None:
                    raise ValueError("readiness metadata unknown")
                a, b = _q(displacement(first)), _q(displacement(last))
                if b < a or (previous_displacement is not None and a < previous_displacement):
                    raise ValueError("displacement clock must be nondecreasing")
                if a < piece.ready_target:
                    raise ValueError("service precedes readiness")
                previous_displacement = b
            fraction = piece.mass / piece.segment.mass
            mean_exit = (first + last) / 2
            for p in piece.segment.parts:
                m, b, e = totals.get(p.mark, (ZERO, ZERO, ZERO))
                mass = p.mass * fraction
                totals[p.mark] = (
                    m + mass,
                    b + p.birth_moment * fraction,
                    e + mass * mean_exit,
                )
        previous_end, previous_view = timed.end, timed.view
    return TransportMoments(
        tuple(MarkTransport(mark, *values) for mark, values in sorted(totals.items())),
        check_boundary, displacement is not None,
    )


@dataclass(frozen=True, slots=True)
class _Flow:
    start: F
    end: F
    rates: tuple[tuple[str, F, F], ...]


def merge_streams(
    streams: Sequence[Sequence[TimedView]],
    *,
    target_at_end: Callable[[F], Number] | None = None,
) -> RankProfile:
    """Conservative exchangeable multi-input merge; flatten exact true knots.

    Each stream consumes a contiguous FIFO prefix/view under its own schedule.
    Birth moments are inherited, while boundary is the new arrival interval.
    An absent target callback leaves readiness explicitly unknown. A changing
    end-target callback is a declared admission discretization; refinement
    covariance requires preserving that same target law.
    """
    flows: list[_Flow] = []
    events: dict[F, tuple[list[int], list[int]]] = {}
    for stream in streams:
        previous: TimedView | None = None
        for timed in stream:
            if previous is not None and (
                timed.start < previous.end
                or timed.view.profile is not previous.view.profile
                or timed.view.start != previous.view.end
            ):
                raise ValueError("each merge input must be causal contiguous FIFO")
            rate = timed.rate
            for piece in timed.view.iter_pieces():
                first = timed.start + (piece.start - timed.view.start) / rate
                last = timed.start + (piece.end - timed.view.start) / rate
                rates = tuple(
                    (p.mark, rate * p.mass / piece.segment.mass,
                     rate * p.birth_moment / piece.segment.mass)
                    for p in piece.segment.parts
                )
                idx = len(flows)
                flows.append(_Flow(first, last, rates))
                events.setdefault(first, ([], []))[0].append(idx)
                events.setdefault(last, ([], []))[1].append(idx)
            previous = timed
    edges = sorted(events)
    active: set[int] = set()
    segments: list[RankSegment] = []
    for first, last in zip(edges, edges[1:]):
        starts, ends = events[first]
        active.difference_update(ends)
        active.update(starts)
        if not active:
            continue
        totals: dict[str, tuple[F, F]] = {}
        duration = last - first
        for idx in sorted(active):
            for mark, rate, birth_rate in flows[idx].rates:
                m, b = totals.get(mark, (ZERO, ZERO))
                totals[mark] = (m + rate * duration, b + birth_rate * duration)
        parts = tuple(MarkedMass(mark, m, b) for mark, (m, b) in sorted(totals.items()))
        target = None if target_at_end is None else _q(target_at_end(last))
        segments.append(RankSegment(parts, target, (first, last)))
    return RankProfile(_coalesce_exact(segments))


def representation_stats(views: Sequence[RankView]) -> dict[str, int]:
    """Actual unique retained owner identities, not expanded logical row counts."""
    profiles = {id(v.profile): v.profile for v in views}
    segments = {id(s): s for p in profiles.values() for s in p.segments}
    marks = {id(m): m for s in segments.values() for m in s.parts}
    return {
        "profile_owners": len(profiles),
        "segment_owners": len(segments),
        "mark_owners": len(marks),
        "view_count": len(views),
        "stored_profile_segments": sum(len(p.segments) for p in profiles.values()),
        "essential_profile_segments": sum(p.essential_segments for p in profiles.values()),
        "profile_dag_depth": 1 if profiles else 0,
        "view_profile_depth": 2 if views else 0,
    }
