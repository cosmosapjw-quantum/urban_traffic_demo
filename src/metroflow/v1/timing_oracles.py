"""T04 underloaded/overloaded timing fixtures with declared numerical holds."""

from ..ordered_lane import Lane
from ..ordered_network import Group, Route
from ..foundation_kinetics import VehicleClass
from ..packet_network import PacketNetwork
from .kinetics import ClassMass
from .lanegroups import LaneGroupContract
from .transport import TransportModel, BoundaryFlux


def timing_fixture(
    step=0.1,
    *,
    mass=1.0,
    window=1.0,
    exit_rate=100.0,
    entry_rate=100.0,
    fluxes=None,
    entry_speed=10.0,
    lengths=(100.0, 110.0),
):
    groups = tuple(
        Group(
            str(i),
            str(i),
            str(i + 1),
            Lane(length, 10.0, entry_rate, exit_rate, 10000.0, interaction_rate=0.0),
        )
        for i, length in enumerate(lengths)
    )
    turns = frozenset((str(i), str(i + 1)) for i in range(len(groups) - 1))
    contract = LaneGroupContract(
        "synthetic-timing", groups, turns, (), tuple((g.id, 10000.0) for g in groups), (), ()
    )
    route = Route("trip", tuple(g.id for g in groups))
    vehicle = VehicleClass(preferred_mps=10.0)
    fluxes = fluxes if fluxes is not None else (BoundaryFlux("trip", 0.0, window, mass),)
    model = TransportModel(
        contract,
        (route,),
        {"trip": vehicle},
        fluxes,
        max_step_s=step,
        templates=(ClassMass(vehicle, 1.0, 1.0, 0.0, 0.0),),
        entry_speeds={"car": entry_speed},
    )
    return model


def timing_oracles():
    rows = []
    # Frozen original counterexample: two links, 210m, U=10, large service.
    reference = timing_fixture(1.0)
    old = PacketNetwork(reference.network.groups, (Route("trip", ("0", "1")),), dt_s=10.0)
    s = old.initial()
    for k in range(6):
        s, _ = old.step(s, (("trip", 1.0),) if k == 0 else ())
    baseline = (s.exit_moment - s.birth_moment) / s.completed
    reports = []
    for dt in (0.2, 0.1):
        model = timing_fixture(dt)
        state = model.advance(model.initial(), 35.0)
        report = model.report(state)
        reports.append(report)
    matched = []
    for dt in (0.2, 0.1):
        model = timing_fixture(dt, window=0.0)
        state = model.advance(model.initial(), 35.0)
        matched.append(model.report(state))
    exact = 21.0
    improvement = reports[-1]["whole_population_mean_s"] - exact
    rows.append(
        dict(
            case="two_link_210m",
            status="PASS"
            if reports[-1]["completed_veh"] > 0
            and abs(improvement) <= 1.0
            and abs(reports[0]["whole_population_mean_s"] - reports[1]["whole_population_mean_s"])
            <= 1.0
            and abs(matched[1]["whole_population_mean_s"] - exact) <= 1.0
            else "NUMERICAL_ERROR",
            analytic_zero_queue_s=exact,
            source_contract="legacy and same_input_point_refined use identical 1veh point source at t=0; primary refined uses uniform [0,1] source",
            same_input_point_refined=matched,
            legacy_dt10_mean_s=baseline,
            refined=reports,
        )
    )
    models = [
        timing_fixture(dt, mass=20.0, window=10.0, exit_rate=1.0, entry_rate=0.5)
        for dt in (0.2, 0.1)
    ]
    states = [m.advance(m.initial(), 30.0) for m in models]
    error = (
        max(
            abs(models[0].completed_at(states[0], t) - models[1].completed_at(states[1], t))
            for t in range(31)
        )
        / 20.0
    )
    reports = [m.report(s) for m, s in zip(models, states)]
    unfinished = abs(reports[0]["unfinished_fraction"] - reports[1]["unfinished_fraction"])
    source = abs(reports[0]["source_pending_veh"] - reports[1]["source_pending_veh"]) / 20.0
    rows.append(
        dict(
            case="overloaded_refinement",
            status="PASS" if max(error, unfinished, source) <= 0.02 else "NUMERICAL_ERROR",
            curve_error_fraction=error,
            unfinished_fraction_error=unfinished,
            source_fraction_error=source,
            refined=reports,
        )
    )
    return rows
