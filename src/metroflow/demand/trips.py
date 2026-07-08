"""Trip request generation and activation helpers for baseline demand flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib

import numpy as np

from metroflow.city.zones import POI, POIType, ZoningPlacementResult
from metroflow.demand.population import Citizen, PopulationGenerationResult, ScheduleTemplate
from metroflow.sim.config import DayType, SimulationConfig, TimeBand

__all__ = [
    "TripRequestStatus",
    "TripRequest",
    "TripRequestGenerationResult",
    "generate_trip_requests",
    "build_trip_requests",
    "activate_trip_requests",
]


class StrEnum(str, Enum):
    """Local string enum base."""


class TripRequestStatus(StrEnum):
    QUEUED = "queued"
    ACTIVATED = "activated"
    CANCELED = "canceled"


@dataclass(slots=True)
class TripRequest:
    """Planned trip request emitted from citizen schedules before activation."""

    trip_request_id: int
    citizen_id: int
    origin_poi_id: int
    dest_poi_id: int
    planned_depart_tick: int
    day_type: DayType | str
    time_band: TimeBand | str
    status: TripRequestStatus | str = TripRequestStatus.QUEUED

    def __post_init__(self) -> None:
        self.trip_request_id = int(self.trip_request_id)
        self.citizen_id = int(self.citizen_id)
        self.origin_poi_id = int(self.origin_poi_id)
        self.dest_poi_id = int(self.dest_poi_id)
        self.planned_depart_tick = int(self.planned_depart_tick)
        self.day_type = DayType(self.day_type)
        self.time_band = TimeBand(self.time_band)
        self.status = TripRequestStatus(self.status)
        if self.origin_poi_id == self.dest_poi_id:
            raise ValueError("TripRequest origin_poi_id and dest_poi_id must differ")
        if self.planned_depart_tick < 0:
            raise ValueError("TripRequest planned_depart_tick must be >= 0")

    @classmethod
    def from_internal_values(
        cls,
        *,
        trip_request_id: int,
        citizen_id: int,
        origin_poi_id: int,
        dest_poi_id: int,
        planned_depart_tick: int,
        day_type: DayType,
        time_band: TimeBand,
        status: TripRequestStatus,
    ) -> "TripRequest":
        """Trusted fast-path constructor for internal demand generation loops."""

        if int(origin_poi_id) == int(dest_poi_id):
            raise ValueError("TripRequest origin_poi_id and dest_poi_id must differ")
        if int(planned_depart_tick) < 0:
            raise ValueError("TripRequest planned_depart_tick must be >= 0")
        out = object.__new__(cls)
        out.trip_request_id = int(trip_request_id)
        out.citizen_id = int(citizen_id)
        out.origin_poi_id = int(origin_poi_id)
        out.dest_poi_id = int(dest_poi_id)
        out.planned_depart_tick = int(planned_depart_tick)
        out.day_type = day_type
        out.time_band = time_band
        out.status = status
        return out


@dataclass(slots=True)
class TripRequestGenerationResult:
    """Output bundle for generated/activated trip request primitives."""

    trip_requests: tuple[TripRequest, ...]
    metadata: dict[str, int | float | str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.trip_requests = tuple(self.trip_requests)
        if not isinstance(self.metadata, dict):
            self.metadata = dict(self.metadata)


@dataclass(slots=True)
class _TripRequestLayoutPlan:
    """Planning stage output for trip generation.

    Split from `TripRequest` object materialization to make future JAX-porting
    and profiling of the planning stage easier.
    """

    rows: tuple[tuple[int, int, int, int], ...]
    metadata: dict[str, int | float | str]


def generate_trip_requests(
    population: PopulationGenerationResult,
    zoning: ZoningPlacementResult,
    config: SimulationConfig | None = None,
    *,
    seed: int = 0,
    day_type: DayType | str = DayType.WEEKDAY,
    time_band: TimeBand | str = TimeBand.MORNING,
    start_tick: int = 0,
    jitter_max_ticks: int = 900,
    start_trip_request_id: int = 1,
) -> TripRequestGenerationResult:
    """Generate queued trip requests for a given day/time context from citizens."""

    cfg = config if config is not None else SimulationConfig()
    day_type = DayType(day_type)
    time_band = TimeBand(time_band)
    start_tick = int(start_tick)
    jitter_max_ticks = int(jitter_max_ticks)
    if start_tick < 0:
        raise ValueError("start_tick must be >= 0")
    if jitter_max_ticks < 0:
        raise ValueError("jitter_max_ticks must be >= 0")
    if int(start_trip_request_id) < 1:
        raise ValueError("start_trip_request_id must be >= 1")
    if day_type not in cfg.day_type_set:
        raise ValueError(f"day_type {day_type.value} is not enabled in config.day_type_set")
    if time_band not in cfg.time_bands:
        raise ValueError(f"time_band {time_band.value} is not enabled in config.time_bands")

    citizens = tuple(population.citizens)
    schedules = tuple(population.schedule_templates)
    if not schedules:
        raise ValueError("population.schedule_templates must not be empty")
    if not citizens:
        return TripRequestGenerationResult(
            trip_requests=(),
            metadata={
                "seed": int(seed),
                "day_type": day_type.value,
                "time_band": time_band.value,
                "trip_request_count": 0,
                "requested_citizen_count": 0,
            },
        )

    schedule_by_id = {s.schedule_template_id: s for s in schedules}
    fallback_schedules = _fallback_schedules_by_day(schedules)
    if day_type not in fallback_schedules:
        raise ValueError(f"no schedule templates available for day_type={day_type.value}")

    poi_by_id = {poi.poi_id: poi for poi in zoning.pois}
    if not poi_by_id:
        raise ValueError("zoning.pois must not be empty")
    leisure_pois = tuple(poi for poi in zoning.pois if poi.poi_type == POIType.LEISURE)

    n = len(citizens)
    rng = _rng_for_trip_generation(
        seed=int(seed),
        day_type=day_type,
        time_band=time_band,
    )
    include_rolls = rng.random(n, dtype=np.float32)
    type_rolls = rng.random(n, dtype=np.float32)
    jitter_upper = (jitter_max_ticks + 1) if jitter_max_ticks > 0 else 1
    jitter_offsets = rng.integers(
        low=0,
        high=jitter_upper,
        size=n,
        dtype=np.int32,
    )

    layout = _plan_trip_request_layout(
        citizens=citizens,
        schedule_by_id=schedule_by_id,
        fallback_schedules=fallback_schedules[day_type],
        poi_by_id=poi_by_id,
        leisure_pois=leisure_pois,
        day_type=day_type,
        time_band=time_band,
        start_tick=start_tick,
        include_rolls=include_rolls,
        type_rolls=type_rolls,
        jitter_offsets=jitter_offsets,
    )

    rows = layout.rows
    trip_requests_list: list[TripRequest] = []
    trip_requests_list_extend = trip_requests_list.append
    next_trip_id = int(start_trip_request_id)
    queued = TripRequestStatus.QUEUED
    for row in rows:
        citizen_id, origin_poi_id, dest_poi_id, planned_depart_tick = row
        trip_requests_list_extend(
            TripRequest.from_internal_values(
                trip_request_id=next_trip_id,
                citizen_id=citizen_id,
                origin_poi_id=origin_poi_id,
                dest_poi_id=dest_poi_id,
                planned_depart_tick=planned_depart_tick,
                day_type=day_type,
                time_band=time_band,
                status=queued,
            )
        )
        next_trip_id += 1
    trip_requests = tuple(trip_requests_list)

    return TripRequestGenerationResult(
        trip_requests=trip_requests,
        metadata={
            "seed": int(seed),
            "day_type": day_type.value,
            "time_band": time_band.value,
            "trip_request_count": len(trip_requests),
            "requested_citizen_count": len(citizens),
            **layout.metadata,
        },
    )


def build_trip_requests(
    population: PopulationGenerationResult,
    zoning: ZoningPlacementResult,
    config: SimulationConfig | None = None,
    *,
    seed: int = 0,
    day_type: DayType | str = DayType.WEEKDAY,
    time_band: TimeBand | str = TimeBand.MORNING,
    start_tick: int = 0,
    jitter_max_ticks: int = 900,
    start_trip_request_id: int = 1,
) -> TripRequestGenerationResult:
    """Alias for generate_trip_requests."""

    return generate_trip_requests(
        population,
        zoning,
        config,
        seed=seed,
        day_type=day_type,
        time_band=time_band,
        start_tick=start_tick,
        jitter_max_ticks=jitter_max_ticks,
        start_trip_request_id=start_trip_request_id,
    )


def activate_trip_requests(
    trip_requests: tuple[TripRequest, ...] | list[TripRequest],
    *,
    current_tick: int,
) -> tuple[TripRequest, ...]:
    """Return trip requests with due queued requests transitioned to activated."""

    current_tick = int(current_tick)
    if current_tick < 0:
        raise ValueError("current_tick must be >= 0")
    out: list[TripRequest] = []
    changed = False
    maybe_sorted_by_depart = True
    last_depart_tick = -1
    for idx, trip in enumerate(trip_requests):
        depart_tick = int(trip.planned_depart_tick)
        if maybe_sorted_by_depart and depart_tick < last_depart_tick:
            maybe_sorted_by_depart = False
        last_depart_tick = depart_tick
        if (
            trip.status == TripRequestStatus.QUEUED
            and depart_tick <= current_tick
        ):
            out.append(_trip_request_with_status(trip, TripRequestStatus.ACTIVATED))
            changed = True
        elif (
            maybe_sorted_by_depart
            and trip.status == TripRequestStatus.QUEUED
            and depart_tick > current_tick
        ):
            if not changed and isinstance(trip_requests, tuple):
                return trip_requests
            out.extend(trip_requests[idx:])
            return tuple(out)
        else:
            out.append(trip)
    if not changed and isinstance(trip_requests, tuple):
        return trip_requests
    return tuple(out)


def _fallback_schedules_by_day(
    schedules: tuple[ScheduleTemplate, ...],
) -> dict[DayType, tuple[ScheduleTemplate, ...]]:
    by_day: dict[DayType, list[ScheduleTemplate]] = {DayType.WEEKDAY: [], DayType.WEEKEND: []}
    for schedule in schedules:
        if schedule.applicable_day_type == "both":
            by_day[DayType.WEEKDAY].append(schedule)
            by_day[DayType.WEEKEND].append(schedule)
        else:
            by_day[DayType(schedule.applicable_day_type)].append(schedule)
    return {k: tuple(v) for k, v in by_day.items() if v}


def _resolve_schedule_template_for_citizen(
    *,
    citizen: Citizen,
    schedule_by_id: dict[int, ScheduleTemplate],
    day_type: DayType,
    fallback_schedules: tuple[ScheduleTemplate, ...],
) -> ScheduleTemplate | None:
    template = schedule_by_id.get(citizen.schedule_template_id)
    if template is not None:
        if template.applicable_day_type == "both" or template.applicable_day_type == day_type:
            return template
        # Preserve schedule semantics as much as possible when a citizen's stored
        # template is not valid for this day type.
        same_profile = tuple(
            s for s in fallback_schedules if s.departure_jitter_profile == template.departure_jitter_profile
        )
        if same_profile:
            return same_profile[(citizen.citizen_id - 1) % len(same_profile)]
    return fallback_schedules[(citizen.citizen_id - 1) % len(fallback_schedules)] if fallback_schedules else None


def _choose_destination_poi_id(
    *,
    citizen: Citizen,
    origin_poi_id: int,
    poi_by_id: dict[int, POI],
    leisure_pois: tuple[POI, ...],
    destination_type_weights: dict[POIType, float],
    roll: float,
    selected_type: POIType | None = None,
) -> int | None:
    if selected_type is None:
        selected_type = _select_weighted_poi_type(destination_type_weights, roll)
    if selected_type == POIType.WORKPLACE and citizen.work_poi_id is not None:
        if citizen.work_poi_id in poi_by_id and citizen.work_poi_id != origin_poi_id:
            return citizen.work_poi_id
    if selected_type == POIType.LEISURE and citizen.leisure_poi_preferences:
        for poi_id, _weight in citizen.leisure_poi_preferences:
            if poi_id in poi_by_id and poi_id != origin_poi_id:
                return int(poi_id)
    if selected_type == POIType.HOME:
        # Home trips are valid only when origin is not home; for baseline T032 we
        # generate from home anchors so home destination falls back below.
        pass

    # Fallback order preserves `origin != destination`.
    if (
        citizen.work_poi_id is not None
        and citizen.work_poi_id in poi_by_id
        and citizen.work_poi_id != origin_poi_id
    ):
        return citizen.work_poi_id
    for poi_id, _weight in citizen.leisure_poi_preferences:
        if poi_id in poi_by_id and poi_id != origin_poi_id:
            return int(poi_id)
    for poi in leisure_pois:
        if poi.poi_id != origin_poi_id:
            return poi.poi_id
    for poi_id in poi_by_id:
        if poi_id != origin_poi_id:
            return poi_id
    return None


def _select_weighted_poi_type(weights: dict[POIType, float], roll: float) -> POIType:
    total = 0.0
    first_type: POIType | None = None
    for poi_type, weight in weights.items():
        if first_type is None:
            first_type = poi_type if isinstance(poi_type, POIType) else POIType(poi_type)
        total += float(weight)
    if total <= 0:
        return POIType.LEISURE
    threshold = float(roll) * total
    cumulative = 0.0
    for poi_type, weight in weights.items():
        cumulative += float(weight)
        if threshold <= cumulative:
            return poi_type if isinstance(poi_type, POIType) else POIType(poi_type)
    if first_type is not None:
        return first_type
    return POIType.LEISURE


def _rng_for_trip_generation(
    *,
    seed: int,
    day_type: DayType,
    time_band: TimeBand,
) -> np.random.Generator:
    token = f"trips|{int(seed)}|{day_type.value}|{time_band.value}"
    digest = hashlib.blake2s(token.encode("utf-8"), digest_size=8).digest()
    local_seed = int.from_bytes(digest, byteorder="little", signed=False)
    return np.random.default_rng(local_seed)


def _plan_trip_request_layout(
    *,
    citizens: tuple[Citizen, ...],
    schedule_by_id: dict[int, ScheduleTemplate],
    fallback_schedules: tuple[ScheduleTemplate, ...],
    poi_by_id: dict[int, POI],
    leisure_pois: tuple[POI, ...],
    day_type: DayType,
    time_band: TimeBand,
    start_tick: int,
    include_rolls: np.ndarray,
    type_rolls: np.ndarray,
    jitter_offsets: np.ndarray,
) -> _TripRequestLayoutPlan:
    """Plan trip-request primitive rows before `TripRequest` materialization."""

    rows: list[tuple[int, int, int, int]] = []
    weight_selection_cache: dict[int, tuple[tuple[POIType, ...], tuple[float, ...], float]] = {}
    schedule_by_id_get = schedule_by_id.get
    fallback_len = len(fallback_schedules)
    fallback_by_jitter: dict[str, tuple[ScheduleTemplate, ...]] = {}
    if fallback_len > 0:
        grouped: dict[str, list[ScheduleTemplate]] = {}
        for template in fallback_schedules:
            grouped.setdefault(str(template.departure_jitter_profile), []).append(template)
        fallback_by_jitter = {k: tuple(v) for k, v in grouped.items()}
    skipped_missing_rule = 0
    skipped_by_propensity = 0
    for idx, citizen in enumerate(citizens):
        citizen_id = int(citizen.citizen_id)
        template = schedule_by_id_get(int(citizen.schedule_template_id))
        if template is not None:
            applicable_day_type = template.applicable_day_type
            if not (applicable_day_type == "both" or applicable_day_type == day_type):
                same_profile = fallback_by_jitter.get(str(template.departure_jitter_profile), ())
                if same_profile:
                    template = same_profile[(citizen_id - 1) % len(same_profile)]
                elif fallback_len > 0:
                    template = fallback_schedules[(citizen_id - 1) % fallback_len]
                else:
                    template = None
        elif fallback_len > 0:
            template = fallback_schedules[(citizen_id - 1) % fallback_len]
        if template is None:
            skipped_missing_rule += 1
            continue
        rule = template.time_band_rules.get(time_band)
        if rule is None:
            skipped_missing_rule += 1
            continue
        if float(include_rolls[idx]) > rule.trip_propensity:
            skipped_by_propensity += 1
            continue

        origin_poi_id = int(citizen.home_poi_id)
        if origin_poi_id not in poi_by_id:
            raise ValueError(
                f"citizen {citizen.citizen_id} home_poi_id {origin_poi_id} not present in zoning POIs"
            )

        selected_type = _select_weighted_poi_type_cached(
            rule.destination_type_weights,
            float(type_rolls[idx]),
            cache=weight_selection_cache,
        )
        dest_poi_id = _choose_destination_poi_id(
            citizen=citizen,
            origin_poi_id=origin_poi_id,
            poi_by_id=poi_by_id,
            leisure_pois=leisure_pois,
            destination_type_weights=rule.destination_type_weights,
            roll=0.0,
            selected_type=selected_type,
        )
        if dest_poi_id is None or dest_poi_id == origin_poi_id:
            skipped_missing_rule += 1
            continue

        rows.append(
            (
                citizen_id,
                origin_poi_id,
                int(dest_poi_id),
                int(start_tick + int(jitter_offsets[idx])),
            )
        )

    return _TripRequestLayoutPlan(
        rows=tuple(rows),
        metadata={
            "skipped_by_propensity": skipped_by_propensity,
            "skipped_missing_rule_or_destination": skipped_missing_rule,
        },
    )


def _trip_request_with_status(trip: TripRequest, status: TripRequestStatus) -> TripRequest:
    return TripRequest.from_internal_values(
        trip_request_id=trip.trip_request_id,
        citizen_id=trip.citizen_id,
        origin_poi_id=trip.origin_poi_id,
        dest_poi_id=trip.dest_poi_id,
        planned_depart_tick=trip.planned_depart_tick,
        day_type=trip.day_type,
        time_band=trip.time_band,
        status=status,
    )


def _select_weighted_poi_type_cached(
    weights: dict[POIType, float],
    roll: float,
    *,
    cache: dict[int, tuple[tuple[POIType, ...], tuple[float, ...], float]],
) -> POIType:
    cache_key = id(weights)
    cached = cache.get(cache_key)
    if cached is None:
        poi_types: list[POIType] = []
        cumulative_weights: list[float] = []
        total = 0.0
        for poi_type, weight in weights.items():
            poi_types.append(poi_type if isinstance(poi_type, POIType) else POIType(poi_type))
            total += float(weight)
            cumulative_weights.append(total)
        cached = (tuple(poi_types), tuple(cumulative_weights), float(total))
        cache[cache_key] = cached

    poi_types, cumulative_weights, total = cached
    if total <= 0.0 or not poi_types:
        return POIType.LEISURE
    threshold = float(roll) * total
    for idx, bound in enumerate(cumulative_weights):
        if threshold <= bound:
            return poi_types[idx]
    return poi_types[0]
