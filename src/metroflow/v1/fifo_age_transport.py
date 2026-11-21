"""Route-resolved exact FIFO age and experienced travel-time transport.

Independent Fraction reference physics, not the original f64 Rust runtime or
binary packet serializer. All units: mass (vehicle/people equivalent), seconds,
and birth-time moment (mass seconds). Within each packet, the stored moment
is the proportional mean birth clock of that packet's route component.
"""
from dataclasses import dataclass
from fractions import Fraction as F
from metroflow.v1.fifo_cohort_moments import CohortPacket, fifo_prefix_moments


@dataclass(frozen=True)
class AgeSnapshot:
    clock: F
    served: F
    route_mass: dict[int, F]
    route_birth_moment: dict[int, F]
    route_age_moment: dict[int, F]
    mean_departed_age: dict[int, F | None]


@dataclass(frozen=True)
class DelayTransport:
    route_served_mass: dict[int, F]
    route_birth_moment: dict[int, F]
    route_exit_time_moment: dict[int, F]
    route_delay_total: dict[int, F]
    final_time: F


def departure_age_snapshot(
    cohorts: tuple[CohortPacket, ...], clock: F, served: F
) -> AgeSnapshot:
    """Current-time age of served cohort, not past realized exit delay."""
    observed = fifo_prefix_moments(cohorts, F(served))
    masses = {r: m for r, (m, _) in observed.items()}
    births = {r: b for r, (_, b) in observed.items()}
    ages = {r: F(clock)*m-b for r, (m,b) in observed.items()}
    means = {r: None if m==0 else ages[r]/m for r,m in masses.items()}
    return AgeSnapshot(F(clock), F(served), masses, births, ages, means)


def fifo_route_delay(
    cohorts: tuple[CohortPacket, ...],
    schedule: tuple[tuple[F,F,F], ...],
) -> DelayTransport:
    """Integrate exact time of exit minus birth for each route along FIFO z.

    Each interval (t0,t1,rate) has constant nonnegative service rate.
    The whole mass must have been served; inter-interval idle gaps are allowed.
    Sums are rational, and no interpolation changes route mass shares.
    """
    if not schedule:
        raise ValueError("nonempty service history required")
    # Validation and cumulative source label partitions.
    packets = []
    total = F(0)
    masses: dict[int,F] = {}
    birth: dict[int,F] = {}
    for packet in cohorts:
        if not packet.parts:
            raise ValueError("empty original FIFO packet")
        size=F(0)
        for part in packet.parts:
            if part.mass < 0:
                raise ValueError("negative source mass")
            size += F(part.mass)
            masses.setdefault(part.route,F(0))
            birth.setdefault(part.route,F(0))
        if size <= 0:
            raise ValueError("nonpositive source packet mass")
        packets.append((total,total+size,packet,size))
        total += size
    if total <= 0:
        raise ValueError("no physical input mass")
    route_exit = {r:F(0) for r in masses}
    route_birth = {r:F(0) for r in masses}
    route_served = {r:F(0) for r in masses}
    cumulative=F(0)
    previous_end: F | None = None
    for first,last,rate in schedule:
        first,last,rate=F(first),F(last),F(rate)
        if last<=first or rate<0:
            raise ValueError("time interval and service rate must be admissible")
        if previous_end is not None and first<previous_end:
            raise ValueError("service clock segments out of time order")
        previous_end=last
        start=cumulative
        end=start+rate*(last-first)
        if end>total:
            raise ValueError("service exceeds original FIFO mass")
        if rate>0:
            for lower,upper,packet,size in packets:
                left=max(start,lower)
                right=min(end,upper)
                if right<=left:continue
                zwidth=right-left
                # T(z) = first + (z-start)/rate, for served mass label z.
                exit_integral=first*zwidth+(
                    (right-start)**2-(left-start)**2
                )/(2*rate)
                for part in packet.parts:
                    fraction=F(part.mass)/size
                    route_served[part.route] += fraction*zwidth
                    route_birth[part.route] += F(part.birth_moment)/size*zwidth
                    route_exit[part.route] += fraction*exit_integral
        cumulative=end
    if cumulative!=total:
        raise ValueError("insufficient service to complete physical input")
    # Per-route total experienced delay: ∫ (actual exit clock - birth clock)dMass.
    route_delays={r:route_exit[r]-route_birth[r] for r in masses}
    return DelayTransport(route_served,route_birth,route_exit,route_delays,previous_end)
