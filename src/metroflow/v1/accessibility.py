"""M04 spatial accessibility from completed conditional observations, not live truth."""

from dataclasses import dataclass
import math
from .city import reject


@dataclass(frozen=True, slots=True)
class CompletedAccessibility:
    city_identity: str
    stamp_s: float
    costs: tuple[tuple[str, float], ...]
    source_version: str

    def __post_init__(self):
        if (
            not self.city_identity
            or not self.source_version
            or not math.isfinite(self.stamp_s)
            or self.stamp_s < 0
            or not isinstance(self.costs, tuple)
            or len(dict(self.costs)) != len(self.costs)
            or any(not key or math.isnan(value) or value < 0 for key, value in self.costs)
        ):
            reject("invalid completed spatial accessibility")


def compile_accessibility(city_identity, observations, completed_epoch_s):
    """Each block's conditional mean is mass weighted over explicit complete samples.

    Unobserved blocks remain unsupported; no present-truth or zero-time fallback.
    This is a synthetic development indicator, not a population-wide ETA.
    """
    from collections import defaultdict

    groups = defaultdict(list)
    versions = []
    for block, o in observations:
        if o.stamp_s > completed_epoch_s or o.end_s > completed_epoch_s:
            reject("unfinished epoch cannot supply development accessibility")
        if not o.source.startswith(("T04_completed", "completed_")):
            reject("realized completed observations required; predictions/prior unsupported")
        groups[block].append(o)
        versions.append((o.version, o.population))
    costs = tuple(
        sorted(
            (
                block,
                math.fsum(o.mass_veh * o.seconds for o in rows)
                / math.fsum(o.mass_veh for o in rows),
            )
            for block, rows in groups.items()
        )
    )
    import hashlib

    return CompletedAccessibility(
        city_identity,
        completed_epoch_s,
        costs,
        hashlib.sha256(repr(tuple(sorted(versions))).encode()).hexdigest(),
    )
