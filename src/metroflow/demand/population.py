"""Citizen population, behavior profiles, and schedule template generation."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from metroflow.city.zones import POI, POIType, ZoningPlacementResult
from metroflow.sim.config import DayType, SimulationConfig, TimeBand
from metroflow.sim.rng import fold_in_path, key_from_seed, seed_from_key

__all__ = [
    "TimeBandRule",
    "ScheduleTemplate",
    "RouteChoiceProfile",
    "Citizen",
    "PopulationGenerationResult",
    "generate_schedule_templates",
    "build_schedule_templates",
    "generate_behavior_profiles",
    "build_behavior_profiles",
    "generate_citizen_population",
    "build_citizen_population",
]


@dataclass(slots=True)
class TimeBandRule:
    """Per-time-band trip propensity and destination type preference weights."""

    trip_propensity: float
    destination_type_weights: dict[POIType, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.trip_propensity = float(self.trip_propensity)
        if self.trip_propensity < 0:
            raise ValueError("trip_propensity must be >= 0")
        weights = {POIType(k): float(v) for k, v in dict(self.destination_type_weights).items()}
        if any(v < 0 for v in weights.values()):
            raise ValueError("destination_type_weights must be non-negative")
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("destination_type_weights must have positive total weight")
        self.destination_type_weights = {k: v / total for k, v in weights.items()}


@dataclass(slots=True)
class ScheduleTemplate:
    """Demand schedule template keyed by day type and time bands."""

    schedule_template_id: int
    applicable_day_type: DayType | str  # allows "both" in addition to enum values
    time_band_rules: dict[TimeBand, TimeBandRule]
    departure_jitter_profile: str

    def __post_init__(self) -> None:
        self.schedule_template_id = int(self.schedule_template_id)
        if self.applicable_day_type != "both":
            self.applicable_day_type = DayType(self.applicable_day_type)
        self.time_band_rules = {
            TimeBand(k): (v if isinstance(v, TimeBandRule) else TimeBandRule(**dict(v)))
            for k, v in dict(self.time_band_rules).items()
        }
        self.departure_jitter_profile = str(self.departure_jitter_profile)
        if not self.time_band_rules:
            raise ValueError("time_band_rules must not be empty")
        if not self.departure_jitter_profile:
            raise ValueError("departure_jitter_profile must not be empty")


@dataclass(slots=True)
class RouteChoiceProfile:
    """Behavior diversity profile for baseline routing and future reroute logic."""

    behavior_profile_id: int
    delay_sensitivity: float
    reroute_willingness: float
    persistence_bias: float
    exploration_bias: float

    def __post_init__(self) -> None:
        self.behavior_profile_id = int(self.behavior_profile_id)
        self.delay_sensitivity = float(self.delay_sensitivity)
        self.reroute_willingness = float(self.reroute_willingness)
        self.persistence_bias = float(self.persistence_bias)
        self.exploration_bias = float(self.exploration_bias)
        if not 0.0 <= self.reroute_willingness <= 1.0:
            raise ValueError("reroute_willingness must be in [0, 1]")


@dataclass(slots=True)
class Citizen:
    """A simulated traveler with assigned anchors and behavior/schedule ids."""

    citizen_id: int
    home_poi_id: int
    work_poi_id: int | None
    leisure_poi_preferences: tuple[tuple[int, float], ...]
    schedule_template_id: int
    behavior_profile_id: int

    def __post_init__(self) -> None:
        self.citizen_id = int(self.citizen_id)
        self.home_poi_id = int(self.home_poi_id)
        self.work_poi_id = None if self.work_poi_id is None else int(self.work_poi_id)
        prefs: list[tuple[int, float]] = []
        for poi_id, weight in self.leisure_poi_preferences:
            prefs.append((int(poi_id), float(weight)))
        self.leisure_poi_preferences = tuple(prefs)
        self.schedule_template_id = int(self.schedule_template_id)
        self.behavior_profile_id = int(self.behavior_profile_id)
        if self.home_poi_id < 0:
            raise ValueError("home_poi_id must be >= 0")
        if any(weight < 0 for _, weight in self.leisure_poi_preferences):
            raise ValueError("leisure_poi_preferences weights must be non-negative")


@dataclass(slots=True)
class PopulationGenerationResult:
    """Output bundle for T031 population primitives."""

    citizens: tuple[Citizen, ...]
    behavior_profiles: tuple[RouteChoiceProfile, ...]
    schedule_templates: tuple[ScheduleTemplate, ...]
    metadata: dict[str, int | str | float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.citizens = tuple(self.citizens)
        self.behavior_profiles = tuple(self.behavior_profiles)
        self.schedule_templates = tuple(self.schedule_templates)
        if not isinstance(self.metadata, dict):
            self.metadata = dict(self.metadata)


@dataclass(slots=True)
class _PopulationLayoutPlan:
    """Primitive assignment plan used before citizen dataclass materialization."""

    home_poi_ids: tuple[int, ...]
    work_poi_ids: tuple[int | None, ...]
    schedule_template_ids: tuple[int, ...]
    behavior_profile_ids: tuple[int, ...]
    leisure_pref_cache: tuple[tuple[tuple[int, float], ...], ...]
    metadata: dict[str, int | str | float]


def generate_schedule_templates(
    config: SimulationConfig | None = None,
    *,
    seed: int = 0,
) -> tuple[ScheduleTemplate, ...]:
    """Create deterministic weekday/weekend schedule templates across time bands."""

    cfg = config if config is not None else SimulationConfig()
    _ = int(seed)  # Reserved for future stochastic profile variants.

    def rules(
        morning: tuple[float, dict[POIType, float]],
        lunch: tuple[float, dict[POIType, float]],
        evening: tuple[float, dict[POIType, float]],
        night: tuple[float, dict[POIType, float]],
    ) -> dict[TimeBand, TimeBandRule]:
        by_band = {
            TimeBand.MORNING: TimeBandRule(*morning),
            TimeBand.LUNCH: TimeBandRule(*lunch),
            TimeBand.EVENING: TimeBandRule(*evening),
            TimeBand.NIGHT: TimeBandRule(*night),
        }
        return {band: by_band[band] for band in cfg.time_bands if band in by_band}

    templates = (
        ScheduleTemplate(
            schedule_template_id=1,
            applicable_day_type=DayType.WEEKDAY,
            departure_jitter_profile="commute_peaky",
            time_band_rules=rules(
                (0.95, {POIType.WORKPLACE: 0.85, POIType.LEISURE: 0.15}),
                (0.35, {POIType.WORKPLACE: 0.45, POIType.LEISURE: 0.55}),
                (0.80, {POIType.HOME: 0.65, POIType.LEISURE: 0.35}),
                (0.10, {POIType.HOME: 0.85, POIType.LEISURE: 0.15}),
            ),
        ),
        ScheduleTemplate(
            schedule_template_id=2,
            applicable_day_type=DayType.WEEKDAY,
            departure_jitter_profile="shift_staggered",
            time_band_rules=rules(
                (0.60, {POIType.WORKPLACE: 0.70, POIType.LEISURE: 0.30}),
                (0.45, {POIType.WORKPLACE: 0.55, POIType.LEISURE: 0.45}),
                (0.55, {POIType.HOME: 0.55, POIType.LEISURE: 0.45}),
                (0.20, {POIType.HOME: 0.70, POIType.LEISURE: 0.30}),
            ),
        ),
        ScheduleTemplate(
            schedule_template_id=3,
            applicable_day_type=DayType.WEEKEND,
            departure_jitter_profile="weekend_dispersed",
            time_band_rules=rules(
                (0.35, {POIType.LEISURE: 0.60, POIType.WORKPLACE: 0.05, POIType.HOME: 0.35}),
                (0.60, {POIType.LEISURE: 0.75, POIType.HOME: 0.25}),
                (0.70, {POIType.LEISURE: 0.65, POIType.HOME: 0.35}),
                (0.25, {POIType.HOME: 0.85, POIType.LEISURE: 0.15}),
            ),
        ),
        ScheduleTemplate(
            schedule_template_id=4,
            applicable_day_type="both",
            departure_jitter_profile="balanced_default",
            time_band_rules=rules(
                (0.50, {POIType.WORKPLACE: 0.40, POIType.LEISURE: 0.20, POIType.HOME: 0.40}),
                (0.45, {POIType.WORKPLACE: 0.30, POIType.LEISURE: 0.40, POIType.HOME: 0.30}),
                (0.55, {POIType.HOME: 0.55, POIType.LEISURE: 0.45}),
                (0.15, {POIType.HOME: 0.90, POIType.LEISURE: 0.10}),
            ),
        ),
    )
    return templates


def build_schedule_templates(
    config: SimulationConfig | None = None,
    *,
    seed: int = 0,
) -> tuple[ScheduleTemplate, ...]:
    """Alias for generate_schedule_templates."""

    return generate_schedule_templates(config=config, seed=seed)


def generate_behavior_profiles(
    *,
    seed: int = 0,
    count: int = 8,
) -> tuple[RouteChoiceProfile, ...]:
    """Generate deterministic route-choice behavior profiles for population sampling."""

    count = max(1, int(count))
    key = key_from_seed(seed)
    reroute_rng = np.random.default_rng(
        seed_from_key(fold_in_path(key, "behavior_profiles", "reroute_jitter"))
    )
    explore_rng = np.random.default_rng(
        seed_from_key(fold_in_path(key, "behavior_profiles", "explore_noise"))
    )
    reroute_jitter = [
        float(v)
        for v in reroute_rng.uniform(
            low=-0.05,
            high=0.05,
            size=(count,),
        ).tolist()
    ]
    explore_noise = [
        float(v)
        for v in explore_rng.uniform(
            low=0.0,
            high=1.0,
            size=(count,),
        ).tolist()
    ]
    profiles: list[RouteChoiceProfile] = []
    for idx in range(count):
        base = idx / max(1, count - 1)
        profiles.append(
            RouteChoiceProfile(
                behavior_profile_id=idx + 1,
                delay_sensitivity=0.5 + 1.5 * base,
                reroute_willingness=min(1.0, max(0.0, 0.15 + 0.7 * base + reroute_jitter[idx])),
                persistence_bias=0.2 + 1.2 * (1.0 - base),
                exploration_bias=max(0.0, 0.05 + 0.25 * explore_noise[idx]),
            )
        )
    return tuple(profiles)


def build_behavior_profiles(*, seed: int = 0, count: int = 8) -> tuple[RouteChoiceProfile, ...]:
    """Alias for generate_behavior_profiles."""

    return generate_behavior_profiles(seed=seed, count=count)


def generate_citizen_population(
    zoning: ZoningPlacementResult,
    config: SimulationConfig | None = None,
    *,
    seed: int = 0,
    population_target: int | None = None,
    schedule_templates: tuple[ScheduleTemplate, ...] | None = None,
    behavior_profiles: tuple[RouteChoiceProfile, ...] | None = None,
) -> PopulationGenerationResult:
    """Create a deterministic citizen population anchored to generated POIs."""

    cfg = config if config is not None else SimulationConfig()

    if schedule_templates is None:
        schedule_templates = generate_schedule_templates(cfg, seed=seed)
    if behavior_profiles is None:
        behavior_profiles = generate_behavior_profiles(seed=seed)
    schedule_templates = tuple(schedule_templates)
    behavior_profiles = tuple(behavior_profiles)
    if not schedule_templates:
        raise ValueError("schedule_templates must not be empty")
    if not behavior_profiles:
        raise ValueError("behavior_profiles must not be empty")

    layout = _plan_citizen_population_layout(
        zoning=zoning,
        config=cfg,
        seed=seed,
        population_target=population_target,
        schedule_templates=schedule_templates,
        behavior_profiles=behavior_profiles,
    )

    citizens: list[Citizen] = []
    for idx, home_poi_id in enumerate(layout.home_poi_ids, start=1):
        start_index = (idx - 1) % len(layout.leisure_pref_cache) if layout.leisure_pref_cache else 0
        citizens.append(
            Citizen(
                citizen_id=idx,
                home_poi_id=home_poi_id,
                work_poi_id=layout.work_poi_ids[idx - 1],
                leisure_poi_preferences=(
                    layout.leisure_pref_cache[start_index] if layout.leisure_pref_cache else ()
                ),
                schedule_template_id=layout.schedule_template_ids[idx - 1],
                behavior_profile_id=layout.behavior_profile_ids[idx - 1],
            )
        )

    return PopulationGenerationResult(
        citizens=tuple(citizens),
        behavior_profiles=tuple(behavior_profiles),
        schedule_templates=tuple(schedule_templates),
        metadata=dict(layout.metadata),
    )


def build_citizen_population(
    zoning: ZoningPlacementResult,
    config: SimulationConfig | None = None,
    *,
    seed: int = 0,
    population_target: int | None = None,
    schedule_templates: tuple[ScheduleTemplate, ...] | None = None,
    behavior_profiles: tuple[RouteChoiceProfile, ...] | None = None,
) -> PopulationGenerationResult:
    """Alias for generate_citizen_population."""

    return generate_citizen_population(
        zoning,
        config,
        seed=seed,
        population_target=population_target,
        schedule_templates=schedule_templates,
        behavior_profiles=behavior_profiles,
    )


def _resolve_population_target(
    *,
    explicit: int | None,
    config: SimulationConfig,
    zoning: ZoningPlacementResult,
) -> int:
    if explicit is not None:
        return int(explicit)
    if "population_target" in zoning.metadata:
        return int(zoning.metadata["population_target"])
    return int(config.population_target)


def _plan_citizen_population_layout(
    *,
    zoning: ZoningPlacementResult,
    config: SimulationConfig,
    seed: int,
    population_target: int | None,
    schedule_templates: tuple[ScheduleTemplate, ...],
    behavior_profiles: tuple[RouteChoiceProfile, ...],
) -> _PopulationLayoutPlan:
    """Plan primitive population assignments before dataclass materialization.

    The planning/materialization split keeps a numeric assignment stage separable
    from object creation for future JAX-porting work.
    """

    pois = tuple(zoning.pois)
    home_pois = tuple(poi for poi in pois if poi.poi_type == POIType.HOME)
    work_pois = tuple(poi for poi in pois if poi.poi_type == POIType.WORKPLACE)
    leisure_pois = tuple(poi for poi in pois if poi.poi_type == POIType.LEISURE)
    if not home_pois:
        raise ValueError("zoning must contain at least one home POI")

    resolved_population_target = max(
        1,
        int(_resolve_population_target(explicit=population_target, config=config, zoning=zoning)),
    )
    zone_population_capacity_total = sum(max(0, int(z.population_capacity)) for z in zoning.zones)
    home_capacity_total = _capacity_total(home_pois)
    capacity_caps = [resolved_population_target]
    if zone_population_capacity_total > 0:
        capacity_caps.append(zone_population_capacity_total)
    if home_capacity_total > 0:
        capacity_caps.append(home_capacity_total)
    citizen_count = max(1, min(capacity_caps))

    home_slots = _build_assignment_slots(home_pois, citizen_count)
    if len(home_slots) != citizen_count:
        raise ValueError("home assignment slot count mismatch")

    both_templates = tuple(t for t in schedule_templates if t.applicable_day_type == "both")
    weekday_templates = tuple(
        t for t in schedule_templates if t.applicable_day_type in (DayType.WEEKDAY, "both")
    )
    weekend_templates = tuple(
        t for t in schedule_templates if t.applicable_day_type in (DayType.WEEKEND, "both")
    )
    if not weekday_templates or not weekend_templates:
        raise ValueError("schedule_templates must cover weekday and weekend")
    if not both_templates:
        raise ValueError("schedule_templates must include at least one 'both' citizen template")
    schedule_template_ids = tuple(
        both_templates[i % len(both_templates)].schedule_template_id for i in range(citizen_count)
    )

    behavior_profile_ids = tuple(
        behavior_profiles[i % len(behavior_profiles)].behavior_profile_id for i in range(citizen_count)
    )

    worker_share = 0.62 if work_pois else 0.0
    worker_target = int(round(citizen_count * worker_share))
    work_capacity_total = _capacity_total(work_pois)
    if work_capacity_total > 0:
        worker_target = min(worker_target, work_capacity_total)
    worker_target = max(0, min(worker_target, citizen_count))

    key = key_from_seed(seed)
    worker_rng = np.random.default_rng(seed_from_key(fold_in_path(key, "population", "worker_order")))
    worker_order = (
        tuple(
            int(v)
            for v in worker_rng.permutation(citizen_count).tolist()
        )
        if citizen_count
        else ()
    )
    worker_indices = set(worker_order[:worker_target])
    work_slots = _build_assignment_slots(work_pois, worker_target) if worker_target else ()
    work_slot_idx = 0
    work_poi_ids: list[int | None] = [None] * citizen_count
    for idx in range(citizen_count):
        if idx in worker_indices and work_slot_idx < len(work_slots):
            work_poi_ids[idx] = work_slots[work_slot_idx]
            work_slot_idx += 1

    leisure_pref_cache = _build_leisure_pref_cache(
        leisure_pois if leisure_pois else home_pois,
        seed=seed,
    )

    return _PopulationLayoutPlan(
        home_poi_ids=home_slots,
        work_poi_ids=tuple(work_poi_ids),
        schedule_template_ids=schedule_template_ids,
        behavior_profile_ids=behavior_profile_ids,
        leisure_pref_cache=leisure_pref_cache,
        metadata={
            "seed": int(seed),
            "citizen_count": citizen_count,
            "home_poi_count": len(home_pois),
            "work_poi_count": len(work_pois),
            "leisure_poi_count": len(leisure_pois),
            "population_target": resolved_population_target,
            "zone_population_capacity_total": zone_population_capacity_total,
            "home_capacity_total": home_capacity_total,
            "work_capacity_total": work_capacity_total,
            "citizen_count_capped": int(citizen_count < resolved_population_target),
        },
    )


def _capacity_total(pool: tuple[POI, ...]) -> int:
    return sum(max(0, int(poi.capacity_hint)) for poi in pool)


def _build_assignment_slots(pool: tuple[POI, ...], assignment_count: int) -> tuple[int, ...]:
    if assignment_count <= 0:
        return ()
    if not pool:
        raise ValueError("assignment pool must not be empty")
    capacities = [max(0, int(poi.capacity_hint)) for poi in pool]
    total_capacity = sum(capacities)
    if total_capacity <= 0:
        return tuple(pool[i % len(pool)].poi_id for i in range(int(assignment_count)))

    assignment_count = min(int(assignment_count), total_capacity)
    scaled = [assignment_count * (cap / total_capacity) for cap in capacities]
    quotas = [int(value) for value in scaled]
    remainder = assignment_count - sum(quotas)
    if remainder > 0:
        order = sorted(
            range(len(pool)),
            key=lambda i: (scaled[i] - quotas[i], capacities[i], -i),
            reverse=True,
        )
        for idx in order[:remainder]:
            quotas[idx] += 1

    slots: list[int] = []
    for poi, quota in zip(pool, quotas, strict=True):
        if quota > 0:
            slots.extend([poi.poi_id] * quota)
    if len(slots) != assignment_count:
        raise ValueError("assignment slot planner produced mismatched slot count")
    return tuple(slots)


def _build_leisure_pref_cache(
    pool: tuple[POI, ...],
    *,
    seed: int,
) -> tuple[tuple[tuple[int, float], ...], ...]:
    if not pool:
        return ()
    n = min(3, len(pool))
    weight_rng = np.random.default_rng(
        seed_from_key(fold_in_path(key_from_seed(seed), "population", "leisure_pref_weights"))
    )
    weight_rows = weight_rng.uniform(
        low=0.5,
        high=1.5,
        size=(len(pool), n),
    ).tolist()
    cache: list[tuple[tuple[int, float], ...]] = []
    for start in range(len(pool)):
        selected = [pool[(start + i) % len(pool)] for i in range(n)]
        raw = [float(v) for v in weight_rows[start]]
        total = sum(raw)
        cache.append(
            tuple((poi.poi_id, weight / total) for poi, weight in zip(selected, raw, strict=True))
        )
    return tuple(cache)
