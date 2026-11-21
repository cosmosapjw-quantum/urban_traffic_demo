"""Exact-arithmetic FIFO cumulative route and birth-moment oracle.

This research component models FIFO sub-head physical observations, not the
original simulator's IEEE source summation or immutable checkpoint storage.
"""
from dataclasses import dataclass
from fractions import Fraction

@dataclass(frozen=True)
class CohortPart:
    route: int
    mass: Fraction
    birth_moment: Fraction

@dataclass(frozen=True)
class CohortPacket:
    parts: tuple[CohortPart, ...]


def fifo_prefix_moments(
    packets: tuple[CohortPacket, ...], served: Fraction
) -> dict[int, tuple[Fraction, Fraction]]:
    """Cumulative route mass and first birth-time moment at one FIFO cut.

    A packet's original parts are served proportionally with a common fraction;
    neither its route vector nor its birth moment is discarded.
    """
    remaining = Fraction(served)
    if remaining < 0:
        raise ValueError("negative FIFO service volume")
    totals: list[Fraction] = []
    all_routes: set[int] = set()
    for packet in packets:
        if not packet.parts:
            raise ValueError("empty FIFO packet")
        size = Fraction(0)
        for part in packet.parts:
            if part.mass < 0:
                raise ValueError("negative route mass")
            size += part.mass
            all_routes.add(part.route)
        if size <= 0:
            raise ValueError("nonpositive FIFO packet mass")
        totals.append(size)
    if remaining > sum(totals, Fraction(0)):
        raise ValueError("service exceeds available FIFO volume")

    out = {r: (Fraction(0), Fraction(0)) for r in sorted(all_routes)}
    for packet, size in zip(packets, totals):
        if remaining == 0:
            break
        admitted = min(size, remaining)
        alpha = admitted / size
        for part in packet.parts:
            m, b = out[part.route]
            out[part.route] = (
                m + alpha * part.mass, b + alpha * part.birth_moment
            )
        remaining -= admitted
    return out
