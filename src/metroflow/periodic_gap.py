"""Closed periodic-motif reduction, not an arbitrary pair-distribution closure.

K representative states repeat r times on a ring whose length scales with r.
The local deterministic controller and class pattern are translation invariant.
All controls use the OLD state, then all gaps use the SAME leader displacements.
No external leader acceleration is supplied. Exact local observations are used.
"""

from dataclasses import dataclass, replace
from collections import defaultdict
import math
from .foundation_kinetics import VehicleClass
from .gap_transport import PairBin, LeaderReport, control, ViabilityError
from .stopping_envelope import motion, interval_closure


@dataclass(frozen=True, slots=True)
class RingCell:
    vehicle: VehicleClass
    gap_m: float
    speed_mps: float
    travelled_m: float = 0.0


@dataclass(frozen=True, slots=True)
class RingState:
    cells: tuple[RingCell, ...]
    repetitions: int
    lane_length_m: float
    time_s: float = 0.0


def _validate(state):
    if (
        not isinstance(state.cells, tuple)
        or not state.cells
        or isinstance(state.repetitions, bool)
        or not isinstance(state.repetitions, int)
        or state.repetitions < 1
    ):
        raise ValueError("nonempty periodic motif and integer repetitions required")
    if not math.isfinite(state.time_s) or state.time_s < 0:
        raise ValueError("invalid ring time")
    for c in state.cells:
        if not isinstance(c.vehicle, VehicleClass) or any(
            not math.isfinite(x) or x < 0 for x in (c.gap_m, c.speed_mps, c.travelled_m)
        ):
            raise ValueError("invalid representative state")
    required = state.repetitions * math.fsum(c.gap_m + c.vehicle.length_m for c in state.cells)
    if (
        not math.isfinite(state.lane_length_m)
        or state.lane_length_m <= 0
        or abs(required - state.lane_length_m) > 1e-10 * max(1.0, required)
    ):
        raise ValueError("fixed ring length incompatible with gaps and vehicle lengths")


def make_ring(cells, repetitions=1):
    cells = tuple(cells)
    if (
        not cells
        or isinstance(repetitions, bool)
        or not isinstance(repetitions, int)
        or repetitions < 1
    ):
        raise ValueError("nonempty motif and positive integer repetition required")
    state = RingState(
        cells, repetitions, repetitions * math.fsum(c.gap_m + c.vehicle.length_m for c in cells)
    )
    _validate(state)
    return state


def advance_ring(state, dt, cap_mps):
    """Simultaneous safe held-control update on a physically realized cycle.

    Safety inherits exact local gaps/speeds, instantaneous actuation and known
    braking bounds. Periodicity is an initial-condition symmetry, not a generic
    coarse graining. Broken periodicity requires more representatives.
    """
    _validate(state)
    if not math.isfinite(dt) or dt <= 0 or not math.isfinite(cap_mps) or cap_mps <= 0:
        raise ValueError("positive finite step and speed cap required")
    cells = state.cells
    k = len(cells)
    controls = []
    try:
        for i, c in enumerate(cells):
            lead = cells[(i + 1) % k]
            pair = PairBin(c.vehicle, 1.0, c.gap_m, c.speed_mps, lead.speed_mps, c.travelled_m)
            controls.append(
                control(
                    pair,
                    LeaderReport(state.time_s, lead.speed_mps),
                    state.time_s,
                    dt,
                    cap_mps,
                    lead.vehicle.brake_mps2,
                )
            )
        moved = tuple(motion(c.speed_mps, u, dt) for c, u in zip(cells, controls))
        updated = []
        proof = []
        for i, c in enumerate(cells):
            j = (i + 1) % k
            closing, witness = interval_closure(
                c.speed_mps, cells[j].speed_mps, controls[i], controls[j], dt
            )
            minimum = c.gap_m - closing
            if minimum < c.vehicle.min_gap_m - 1e-9:
                raise ArithmeticError("simultaneous applied motion violates gap bound")
            updated.append(
                replace(
                    c,
                    gap_m=c.gap_m + moved[j][0] - moved[i][0],
                    speed_mps=moved[i][1],
                    travelled_m=c.travelled_m + moved[i][0],
                )
            )
            proof.append(
                dict(
                    min_gap_m=minimum,
                    witness_s=state.time_s + witness,
                    acceleration_mps2=controls[i],
                    leader_acceleration_mps2=controls[j],
                )
            )
        result = replace(state, cells=tuple(updated), time_s=state.time_s + dt)
        _validate(result)
        return result, tuple(proof)
    except (ViabilityError, ValueError, ArithmeticError) as exc:
        exc.checkpoint = state
        raise


def observe_ring(state):
    """Follower and leader marked marginals are exactly the same cyclic multiset."""
    _validate(state)
    cells = state.cells
    k = len(cells)
    count = k * state.repetitions
    follower = defaultdict(int)
    leader = defaultdict(int)
    for i, c in enumerate(cells):
        n = cells[(i + 1) % k]
        follower[(c.vehicle, c.speed_mps)] += state.repetitions
        leader[(n.vehicle, n.speed_mps)] += state.repetitions
    l1 = sum(abs(follower[x] - leader[x]) for x in follower.keys() | leader.keys()) / count
    mean = math.fsum(c.speed_mps for c in cells) / k
    required = state.repetitions * math.fsum(c.gap_m + c.vehicle.length_m for c in cells)
    return dict(
        vehicles=count,
        representatives=k,
        lane_length_m=state.lane_length_m,
        density_veh_m=count / state.lane_length_m,
        mean_speed_mps=mean,
        variance_speed=math.fsum((c.speed_mps - mean) ** 2 for c in cells) / k,
        length_residual_m=required - state.lane_length_m,
        pair_marginal_l1=l1,
        vehicle_metres=state.repetitions * math.fsum(c.travelled_m for c in cells),
    )
