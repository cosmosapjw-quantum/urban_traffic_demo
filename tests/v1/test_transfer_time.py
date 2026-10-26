"""T04 timing: independent analytic paths, conservation and declared split errors."""

from dataclasses import replace
import math
import pickle
import pytest
from metroflow.foundation_kinetics import passage
from metroflow.active_suffix.common import Signal, BudgetExceeded
from metroflow.packet_network import Part, combine, _portion
from metroflow.v1.kinetics import advance_bulk, KineticEnvironment
from metroflow.v1.transport import BoundaryFlux, TransportModel
from metroflow.v1.timing_oracles import timing_fixture, timing_oracles
from metroflow.v1.city import CityContractError


def test_two_link_210m_counterexample_improves_without_changing_tolerances():
    row = timing_oracles()[0]
    assert row["legacy_dt10_mean_s"] == pytest.approx(41.005)
    assert row["analytic_zero_queue_s"] == 21
    assert row["same_input_point_refined"][1]["whole_population_mean_s"] < 22
    assert row["same_input_point_refined"][1]["whole_population_mean_s"] < row["legacy_dt10_mean_s"]
    assert all(r["status"] == "PASS" for r in row["refined"])
    coarse, fine = row["refined"]
    assert 21 <= fine["whole_population_mean_s"] <= 22
    assert abs(coarse["whole_population_mean_s"] - fine["whole_population_mean_s"]) <= max(
        1.0, 0.02 * fine["whole_population_mean_s"]
    )
    assert fine["whole_population_mean_s"] < coarse["whole_population_mean_s"]


def test_overload_source_and_destination_curves_meet_two_percent_gate():
    row = timing_oracles()[1]
    assert row["status"] == "PASS"
    assert row["curve_error_fraction"] <= 0.02
    assert row["unfinished_fraction_error"] <= 0.02
    assert row["source_fraction_error"] <= 0.02
    assert all(r["source_pending_veh"] > 0 and r["active_veh"] > 0 for r in row["refined"])
    assert all(r["whole_population_mean_s"] is None for r in row["refined"])


def test_finite_response_is_actual_packet_motion_and_uses_persistent_velocity():
    model = timing_fixture(0.1, window=0.0, mass=0.1, entry_speed=2.0, lengths=(10.0,))
    s = model.advance(model.initial(), 0.1)
    assert s.road.cells[0].speed_mps == 2.0
    eta = model.link_eta(s, "0")
    c = model.motion.templates[0].vehicle
    expected = passage(c, 2.0, 10.0, 10.0)[0]
    assert eta.elapsed_s == pytest.approx(expected, abs=1e-10)
    bulk = model.motion.bulk(model.network, model.network.groups[0], s.road.cells[0], s.road.time_s)
    direct = advance_bulk(bulk, KineticEnvironment(10000.0, 10.0, 0.1), 0.1)
    later = model.advance(s, 0.2)
    assert later.road.cells[0].speed_mps == pytest.approx(direct.state.speed_mps)
    assert later.road.cells[0].progress_m - s.road.cells[0].progress_m == pytest.approx(
        direct.distance_m
    )
    final = model.advance(later, 10.0)
    sink = [e for e in final.events if e.destination is None]
    assert min(e.start_s for e in sink) == pytest.approx(0.1 + expected, abs=1e-9)
    assert model.report(final)["status"] == "PASS"


def test_start_from_rest_retains_finite_acceleration_not_instant_preferred_speed():
    model = timing_fixture(0.1, window=0.0, mass=0.1, entry_speed=0.0, lengths=(10.0,))
    s = model.advance(model.initial(), 0.2)
    assert s.road.cells[0].speed_mps == pytest.approx(0.2)
    assert s.road.cells[0].progress_m == pytest.approx(0.01)
    exact = passage(model.motion.templates[0].vehicle, 0.0, 10.0, 10.0)[0]
    s = model.advance(s, 10.0)
    assert abs(model.report(s)["whole_population_mean_s"] - exact) <= 0.3


def test_flux_fragmentation_and_route_relabel_preserve_observations():
    a = timing_fixture(0.1)
    b = timing_fixture(0.1, fluxes=tuple(BoundaryFlux("trip", 0.0, 1.0, 0.25) for _ in range(4)))
    assert a.identity == b.identity
    sa, sb = a.advance(a.initial(), 35.0), b.advance(b.initial(), 35.0)
    assert a.report(sa) == b.report(sb)
    assert sa.events == sb.events
    from metroflow.ordered_network import Route
    from metroflow.v1.lanegroups import LaneGroupContract

    net = a.network
    contract = LaneGroupContract(
        "synthetic-timing",
        net.groups,
        frozenset({("0", "1")}),
        (),
        tuple(net.space_capacities_m.items()),
        (),
        (),
    )
    c = TransportModel(
        contract,
        (Route("renamed", ("0", "1")),),
        {"renamed": next(iter(net.vehicle_classes.values()))},
        (BoundaryFlux("renamed", 0, 1, 1),),
        max_step_s=0.1,
        templates=a.motion.templates,
        entry_speeds={"car": 10},
    )
    sc = c.advance(c.initial(), 35.0)
    assert c.report(sc)["mean_completed_s"] == pytest.approx(
        a.report(sa)["mean_completed_s"], abs=1e-10
    )


def test_entry_intervals_survive_compression_and_portioning():
    a = Part("r", ("g",), 1.0, 0.2, 0.0, 0.5)
    b = Part("r", ("g",), 1.0, 0.8, 0.5, 1.0)
    assert len(combine((a, b))) == 2
    assert len(combine((a, a))) == 1
    assert combine((a, a))[0].birth_moment == 0.4
    assert _portion((a,), 0.25)[0].entry_end_s == 0.5
    model = timing_fixture(0.1)
    s = model.advance(model.initial(), 2.0)
    spans = {
        (p.entry_start_s, p.entry_end_s) for packet in s.road.cells[0].packets for p in packet.parts
    }
    assert len(spans) > 1
    assert all(a is not None and a <= b for a, b in spans)


def test_arbitrary_source_endpoint_and_first_birth_moment_are_integrated_exactly():
    model = timing_fixture(0.1, window=0.35, mass=7.0)
    s = model.advance(model.initial(), 0.35)
    r = model.report(s)
    assert r["released_veh"] == pytest.approx(7.0, abs=1e-12)
    assert r["birth_moment_veh_s"] == pytest.approx(7 * 0.35 / 2, abs=1e-12)
    assert r["not_yet_released_veh"] == pytest.approx(0.0, abs=1e-12)
    assert r["mean_completed_s"] is None
    assert r["status"] == "PASS"


def test_source_transfer_holds_and_residence_are_separate():
    model = timing_fixture(0.1)
    s = model.advance(model.initial(), 35.0)
    r = model.report(s)
    assert r["source_quantization_veh_s"] == pytest.approx(0.15)
    assert r["source_queue_veh_s"] == pytest.approx(0, abs=1e-12)
    assert 0 <= r["transfer_quantization_veh_s"] <= 0.1 + 1e-9
    assert r["peak_packets"] > 0
    assert abs(r["mass_residual_veh"]) < 1e-9
    assert abs(r["residence_residual_veh_s"]) < 1e-8
    assert r["p95_s"] is None and r["p95_status"].startswith("UNSUPPORTED")


def test_exit_curve_first_moment_matches_actual_endpoint_completion():
    model = timing_fixture(0.1)
    s = model.advance(model.initial(), 35.0)
    sink = [e for e in s.events if e.destination is None]
    assert math.fsum(e.mass * (e.start_s + e.end_s) / 2 for e in sink) == pytest.approx(
        s.road.exit_moment, abs=1e-9
    )
    assert model.completed_at(s, 35.0) == pytest.approx(s.road.completed, abs=1e-10)
    assert all(e.start_s <= e.end_s for e in s.events)


def test_checkpoint_resume_and_macro_partition_preserve_observations():
    model = timing_fixture(0.1)
    saved = model.advance(model.initial(), 10.0)
    restored = pickle.loads(pickle.dumps(saved))
    a, b = model.advance(saved, 35.0), model.advance(restored, 35.0)
    assert a == b
    direct = model.advance(model.initial(), 35.0)
    assert model.report(a)["mean_completed_s"] == pytest.approx(
        model.report(direct)["mean_completed_s"], abs=1e-9
    )
    assert saved.road.time_s == 10.0 and saved.road.completed == 0


def test_no_full_population_claim_before_future_source_is_released():
    model = timing_fixture(0.1, fluxes=(BoundaryFlux("trip", 10.0, 11.0, 1.0),))
    s = model.advance(model.initial(), 5.0)
    report = model.report(s)
    assert report["released_veh"] == 0 and report["scheduled_veh"] == 1
    assert report["not_yet_released_veh"] == 1 and report["whole_population_mean_s"] is None
    assert report["unfinished_fraction"] == 1


def test_adaptive_cuts_respect_red_boundaries_and_closure_braking():
    from metroflow.v1.lanegroups import LaneGroupContract
    from metroflow.ordered_network import Route

    base = timing_fixture(0.1, lengths=(10.0,))
    g = replace(base.network.groups[0], signal=Signal(2.0, 1.0))
    contract = LaneGroupContract("signal", (g,), frozenset(), (), (("0", 10000.0),), (), ())
    cls = next(iter(base.network.vehicle_classes.values()))
    model = TransportModel(
        contract,
        (Route("trip", ("0",)),),
        {"trip": cls},
        (BoundaryFlux("trip", 0.0, 0.35, 1.0),),
        max_step_s=0.1,
        templates=base.motion.templates,
        entry_speeds={"car": 10.0},
    )
    s = model.advance(model.initial(), 4.0)
    assert all(not 1 <= e.start_s % 2 < 2 for e in s.events)
    g = replace(g, signal=None)
    contract = replace(
        contract,
        groups=(replace(g, physics=replace(g.physics, length_m=1000.0)),),
        windows=(("0", 0.2, 0.4, 0.0),),
    )
    model = TransportModel(
        contract,
        (Route("trip", ("0",)),),
        {"trip": cls},
        (BoundaryFlux("trip", 0.0, 0.0, 0.1),),
        max_step_s=0.1,
        templates=base.motion.templates,
        entry_speeds={"car": 20.0},
    )
    before = model.advance(model.initial(), 0.2)
    assert model.link_eta(before, "0").status == "UNREACHABLE"
    closed = model.advance(before, 0.3)
    assert (
        0
        < before.road.cells[0].speed_mps - closed.road.cells[0].speed_mps
        <= cls.brake_mps2 * 0.1 + 1e-10
    )
    assert closed.road.released == 0.1 and closed.road.completed == 0


def test_record_budget_is_explicit_and_preserves_last_valid_progress():
    base = timing_fixture(0.1)
    from metroflow.v1.lanegroups import LaneGroupContract
    from metroflow.ordered_network import Route

    net = base.network
    contract = LaneGroupContract(
        "budget",
        net.groups,
        frozenset({("0", "1")}),
        (),
        tuple(net.space_capacities_m.items()),
        (),
        (),
    )
    model = TransportModel(
        contract,
        (Route("trip", ("0", "1")),),
        dict(net.vehicle_classes),
        base.fluxes,
        max_step_s=0.1,
        templates=base.motion.templates,
        record_budget=1,
    )
    initial = model.initial()
    with pytest.raises(BudgetExceeded) as exc:
        model.advance(initial, 3.0)
    checkpoint = exc.value.checkpoint
    model.check(checkpoint)
    assert checkpoint.road.time_s > 0
    assert exc.value.request_checkpoint is initial
    assert initial.road.released == 0
    small = TransportModel(
        contract,
        (Route("trip", ("0", "1")),),
        dict(net.vehicle_classes),
        base.fluxes,
        max_step_s=0.1,
        templates=base.motion.templates,
        substep_budget=1,
    )
    with pytest.raises(BudgetExceeded, match="substep") as cap:
        small.advance(small.initial(), 3.0)
    small.check(cap.value.checkpoint)
    assert cap.value.checkpoint.road.time_s == 0.1
    with pytest.raises(CityContractError, match="2M"):
        TransportModel(
            contract, (Route("trip", ("0", "1")),), dict(net.vehicle_classes), record_budget=2000001
        )


def test_invalid_birth_mark_or_forged_mass_ledger_are_rejected():
    with pytest.raises(CityContractError, match="birth"):
        BoundaryFlux("r", 0, 1, 1, 1)
    model = timing_fixture(0.1)
    s = model.initial()
    with pytest.raises(CityContractError, match="ledger"):
        model.report(replace(s, deferred=(("trip", 1.0, 0.0, 0.0, 0.0),)))


def test_same_constant_flux_temporal_partition_is_an_exact_measure_quotient():
    a = timing_fixture(0.1)
    b = timing_fixture(
        0.1, fluxes=(BoundaryFlux("trip", 0, 0.5, 0.5), BoundaryFlux("trip", 0.5, 1.0, 0.5))
    )
    assert a.fluxes == b.fluxes
    assert a.identity == b.identity


def test_timing_cli_runs_the_selected_transport(tmp_path):
    import subprocess
    import sys
    import json

    out = tmp_path / "timing.json"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "metroflow.v1",
            "physics-oracles",
            "--suite",
            "timing",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    data = json.loads(out.read_text())
    assert data["status"] == "PASS"
    assert {r["case"] for r in data["cases"]} == {"two_link_210m", "overloaded_refinement"}


def test_different_flux_entry_windows_keep_fifo_and_only_overlaps_mix():
    from metroflow.packet_network import interval_packets

    a = Part("a", ("g",), 2.0, 0.0, 0.0, 2.0)
    b = Part("b", ("g",), 4.0, 0.4, 1.0, 3.0)
    packets = interval_packets((a, b), 100.0, 100)
    assert len(packets) == 3
    assert {p.tag for p in packets[0].parts} == {"a"}
    assert {p.tag for p in packets[1].parts} == {"a", "b"}
    assert {p.tag for p in packets[2].parts} == {"b"}
    assert math.fsum(p.mass for packet in packets for p in packet.parts) == 6
    assert math.fsum(p.birth_moment for packet in packets for p in packet.parts) == 0.4


def test_point_source_cursor_survives_roundoff_at_a_resume_boundary():
    model = timing_fixture(0.1, fluxes=(BoundaryFlux("trip", 0.3, 0.3, 1.0),))
    state = model.advance(model.initial(), 3 * 0.1)
    model.check(state)
    restored = pickle.loads(pickle.dumps(state))
    final = model.advance(restored, 1.0)
    assert model.report(final)["released_veh"] == 1.0
    assert len(final.consumed_points) == 1
