"""Budgeted push-forward of a declared block activity measure to portal delays.

Units: seconds and normalized probability. The caller supplies a pure internal
travel-time quadrature from AreaAccess (external generalized costs must be zero).
Binning is a numerical approximation, not a gauge transformation. Mass, portal
fractions and the first time moment are retained; within-bin variance is reported.
No individual resident, vehicle or geometry is created by this compiler.
"""
from dataclasses import dataclass
from collections import defaultdict
import math


@dataclass(frozen=True, slots=True)
class DelayAtom:
    portal: str
    weight: float
    delay_s: float
    minimum_s: float
    maximum_s: float


@dataclass(frozen=True, slots=True)
class AccessLaw:
    atoms: tuple[DelayAtom, ...]
    bin_s: float
    mean_s: float
    original_variance_s2: float
    compressed_variance_s2: float
    variance_loss_s2: float
    mean_absolute_compression_s: float
    max_pointwise_compression_s: float
    quadrature_mean_bound_s: float
    input_samples: int
    measure: str

    def portal_weights(self):
        """Unconditional gate probabilities, retained separately from conditioning."""
        return tuple((key, math.fsum(a.weight for a in self.atoms if a.portal == key))
                     for key in sorted({a.portal for a in self.atoms}))

    def condition(self, portal):
        """Return (unconditional probability, normalized conditional delay law).

        Multiplying the traffic amount by the first value is mandatory when the
        source population includes multiple gates. Conditioning never creates a
        second copy of the entire population for each gate.
        """
        selected = tuple(a for a in self.atoms if a.portal == portal)
        probability = math.fsum(a.weight for a in selected)
        if probability <= 0:
            raise ValueError('unknown or zero-mass portal')
        return probability, tuple((a.delay_s, a.weight / probability) for a in selected)


def compile_access(profile, bin_s=2., max_atoms=256, *, external_costs=None):
    """Compile a normalized, nonnegative quadrature into finite delay atoms.

    Each tie is split equally, as in the parent AreaAccess observation. Gates
    never merge with each other. Physical delay bins use their conditional mean,
    not bin centres: E[delay] is unchanged by compression. A coupling from each
    original sample to its bin mean bounds the Wasserstein-1 distance by the
    returned mean absolute compression. The parent mean quadrature certificate
    is kept separately and does not certify gate shares, p95, or model error.
    """
    if not math.isfinite(bin_s) or bin_s <= 0:
        raise ValueError('positive finite delay-bin width required')
    if isinstance(max_atoms, bool) or not isinstance(max_atoms, int) or max_atoms < 1:
        raise ValueError('positive integer access atom budget required')
    # The upstream profile does not encode external costs. Its producer must
    # declare them here when present; this version never treats utility as motion.
    if external_costs is not None and any(not math.isfinite(x) or x != 0.
                                          for x in external_costs.values()):
        raise ValueError('external generalized cost is not physical access time')
    samples = tuple(profile.get('quadrature', ()))
    if not samples:
        raise ValueError('nonempty access quadrature required')
    bound = profile.get('error_bound_s')
    if not isinstance(bound, (int, float)) or not math.isfinite(bound) or bound < 0:
        raise ValueError('finite nonnegative quadrature mean bound required')
    bins = defaultdict(list)
    raw = []
    weights = []
    for sample in samples:
        weight, delay = sample['weight'], sample['cost_s']
        gates = tuple(sample['portals'])
        if not all(map(math.isfinite, (weight, delay))) or weight < 0 or delay < 0:
            raise ValueError('invalid access probability or delay')
        if not gates or len(set(gates)) != len(gates) or any(not isinstance(p, str) or not p for p in gates):
            raise ValueError('nonempty distinct physical gate labels required')
        weights.append(weight)
        if not weight:
            continue
        for gate in gates:
            share = weight / len(gates)
            bins[(gate, math.floor(delay / bin_s))].append((share, delay))
            raw.append((share, delay))
    total = math.fsum(weights)
    if abs(total - 1.) > 1e-10:
        raise ValueError('access probability must sum to one; no mass discarded')
    if len(bins) > max_atoms:
        raise ValueError('access atom budget exceeded; no mass discarded')
    atoms, deviations, variance_lost = [], [], []
    maximum_error = 0.
    for (gate, _), values in sorted(bins.items()):
        mass = math.fsum(w for w, _ in values)
        delay = math.fsum(w*t for w, t in values) / mass
        lo, hi = min(t for _, t in values), max(t for _, t in values)
        atoms.append(DelayAtom(gate, mass, delay, lo, hi))
        deviations.extend(w * abs(t-delay) for w, t in values)
        variance_lost.extend(w * (t-delay)**2 for w, t in values)
        maximum_error = max(maximum_error, abs(lo-delay), abs(hi-delay))
    mean = math.fsum(a.weight*a.delay_s for a in atoms)
    original_variance = math.fsum(w*(t-mean)**2 for w, t in raw)
    compressed_variance = math.fsum(a.weight*(a.delay_s-mean)**2 for a in atoms)
    return AccessLaw(tuple(atoms), bin_s, mean, original_variance, compressed_variance,
                     math.fsum(variance_lost), math.fsum(deviations), maximum_error,
                     float(bound), len(samples), str(profile.get('measure', 'declared activity quadrature')))


def activity_access(measure, portals, *, speed_mps=1.4, depth=2, bin_s=2., max_atoms_per_portal=256):
    """Push activity to physical doors, with explicit per-conditional-door budget.

    Only the mean has a quadrature certificate. Variance/p95 are estimates;
    compare refinement levels for those observables. No driveway/road time is
    included here, so a consumer must not add the same private connector again.
    """
    from ..terrain_city.area_access import AreaAccess
    if isinstance(max_atoms_per_portal, bool) or not isinstance(max_atoms_per_portal, int) or not 1 <= max_atoms_per_portal <= 256:
        raise ValueError("conditional portal atom budget must be 1..256")
    portals = tuple(portals)
    if any(p.external_s != 0 for p in portals):
        raise ValueError('external generalized cost is not physical access time')
    area = AreaAccess(measure.block_points)
    samples, bounds = [], []
    for point, weight, radius in measure.quadrature(depth):
        cost, gates = area.portal_costs(point, portals, speed_mps)
        samples.append(dict(xy=point, weight=weight, cost_s=cost, portals=gates))
        bounds.append(weight * radius / speed_mps)
    profile = dict(quadrature=samples, error_bound_s=math.fsum(bounds), measure='declared ' + measure.kind + ' activity; synthetic prior')
    # compile_access preserves its original global-budget API. Compile with the
    # largest possible total, then enforce each conditional law independently.
    law = compile_access(profile, bin_s, max_atoms_per_portal * len(portals))
    if any(sum(a.portal == gate for a in law.atoms) > max_atoms_per_portal for gate, _ in law.portal_weights()):
        raise ValueError('conditional portal atom budget exceeded; no mass discarded')
    ordered = sorted((s['cost_s'], s['weight']) for s in samples)
    cumulative = 0.
    p95 = ordered[-1][0]
    for t, w in ordered:
        cumulative += w
        if cumulative >= .95 - 1e-12:
            p95 = t
            break
    return law, dict(mean_s=law.mean_s, p95_quadrature_s=p95,
                     variance_quadrature_s2=law.original_variance_s2,
                     quadrature_mean_bound_s=law.quadrature_mean_bound_s,
                     quantile_certificate='NOT_CERTIFIED',
                     samples=samples, warnings=measure.warnings)
