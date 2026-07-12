from dataclasses import replace

import pytest

import metroflow.sim.replay as replay_module
from metroflow.core.contracts import TickSchedule
from metroflow.core.journal import InterventionJournal, InterventionRecord
from metroflow.core.state import GraphState, LandUseState, ReplayState, TrafficState, make_empty_world_state
from metroflow.metrics.benchmarks import record_input_signature_smoke_benchmark
from metroflow.sim.orchestrator import step_world
from metroflow.sim.replay import (
    ReplayBoundary,
    ReplayInputSignatureRecord,
    ReplayRequest,
    ReplayResultRecord,
    ReplayStepInput,
    journal_fingerprint,
    make_replay_boundary,
    make_replay_input_signature,
    replay_input_fingerprint,
    replay_step_world_sequence,
)


def make_materialized_graph(num_edges: int) -> GraphState:
    return GraphState(
        num_nodes=max(num_edges + 1, 0),
        num_edges=num_edges,
        edge_src=tuple(range(num_edges)),
        edge_dst=tuple(range(1, num_edges + 1)),
        edge_class=("road",) * num_edges,
    )


def make_materialized_world(
    num_edges: int = 1,
    step: int = 0,
    seed: int = 17,
    journal_length: int = 0,
):
    return replace(
        make_empty_world_state(seed=seed),
        graph=make_materialized_graph(num_edges),
        traffic=TrafficState(
            step=step,
            edge_queue=(0.0,) * num_edges,
            edge_stock=(1.0,) * num_edges,
            edge_travel_time=(1.0,) * num_edges,
        ),
        replay=ReplayState(seed=seed, journal_length=journal_length),
    )


def run_baseline_sequence(world, schedule: TickSchedule, step_inputs: tuple[ReplayStepInput, ...]):
    current_world = world
    for step_input in step_inputs:
        current_world = step_world(
            current_world,
            schedule=schedule,
            edge_inflow_veh_per_tick=step_input.edge_inflow_veh_per_tick,
            edge_outflow_veh_per_tick=step_input.edge_outflow_veh_per_tick,
            edge_free_flow_time_ticks=step_input.edge_free_flow_time_ticks,
            edge_capacity_veh_per_tick=step_input.edge_capacity_veh_per_tick,
            zonal_travel_times=step_input.zonal_travel_times,
            zone_opportunities=step_input.zone_opportunities,
        )
    return current_world


def test_make_replay_input_signature_record():
    world = make_empty_world_state(seed=7)
    journal = InterventionJournal(records=(InterventionRecord(step=3, kind="incident", payload="edge:1"),))
    rec = make_replay_input_signature(world, num_steps=100, input_fingerprint=1.23, journal=journal)
    assert rec.seed == 7
    assert rec.num_steps == 100
    assert rec.journal_fingerprint
    assert rec.input_fingerprint == "1.23"


def test_replay_input_signature_record_remains_signature_only():
    record = make_replay_input_signature(make_empty_world_state(seed=3), num_steps=2, input_fingerprint="sig")

    assert isinstance(record, ReplayInputSignatureRecord)
    assert not hasattr(record, "final_world")
    assert not hasattr(record, "transition_count")


def test_replay_input_fingerprint_is_deterministic_for_equivalent_inputs():
    journal = InterventionJournal(records=(InterventionRecord(step=8, kind="policy", payload="toll:on"),))
    signature_a = replay_input_fingerprint(11, 20, journal, "obs=a")
    signature_b = replay_input_fingerprint(11, 20, journal, "obs=a")

    assert signature_a == signature_b


def test_replay_input_fingerprint_changes_when_declared_observation_changes():
    journal = InterventionJournal(records=(InterventionRecord(step=8, kind="policy", payload="toll:on"),))
    signature_a = replay_input_fingerprint(11, 20, journal, "obs=a")
    signature_b = replay_input_fingerprint(11, 20, journal, "obs=b")

    assert signature_a != signature_b


def test_journal_fingerprint_rejects_delimiter_collisions():
    journal_a = InterventionJournal(records=(InterventionRecord(step=3, kind="a:b", payload="c"),))
    journal_b = InterventionJournal(records=(InterventionRecord(step=3, kind="a", payload="b:c"),))

    assert journal_fingerprint(journal_a) != journal_fingerprint(journal_b)


def test_replay_input_fingerprint_is_order_sensitive():
    journal_a = InterventionJournal(
        records=(
            InterventionRecord(step=1, kind="policy", payload="a"),
            InterventionRecord(step=2, kind="incident", payload="b"),
        )
    )
    journal_b = InterventionJournal(
        records=(
            InterventionRecord(step=2, kind="incident", payload="b"),
            InterventionRecord(step=1, kind="policy", payload="a"),
        )
    )

    assert replay_input_fingerprint(11, 20, journal_a, "obs=a") != replay_input_fingerprint(11, 20, journal_b, "obs=a")


def test_replay_input_fingerprint_treats_delimiter_collision_cases_as_distinct():
    journal_a = InterventionJournal(records=(InterventionRecord(step=3, kind="a:b", payload="c"),))
    journal_b = InterventionJournal(records=(InterventionRecord(step=3, kind="a", payload="b:c"),))

    assert replay_input_fingerprint(11, 20, journal_a, "obs=a") != replay_input_fingerprint(11, 20, journal_b, "obs=a")


def test_record_input_signature_smoke_benchmark_populates_proxy_fields():
    world = make_empty_world_state(seed=13)
    record = make_replay_input_signature(world, num_steps=12, input_fingerprint="abc")
    bench = record_input_signature_smoke_benchmark(record, step_proxy_score=2.5, state_proxy_score=64.0)

    assert bench.step_proxy_score == 2.5
    assert bench.state_proxy_score == 64.0
    assert bench.signature == "abc"


def test_replay_round_trip_reproduces_baseline_step_world_sequence():
    journal = InterventionJournal(records=(InterventionRecord(step=0, kind="scenario", payload="baseline"),))
    world = make_materialized_world(num_edges=1, step=1, seed=17, journal_length=1)
    schedule = TickSchedule(fast_every=1, medium_every=10, slow_every=100)
    step_inputs = (
        ReplayStepInput(
            edge_inflow_veh_per_tick=(1.0,),
            edge_outflow_veh_per_tick=(0.25,),
            edge_free_flow_time_ticks=(2.0,),
            edge_capacity_veh_per_tick=(1.5,),
        ),
        ReplayStepInput(
            edge_inflow_veh_per_tick=(0.5,),
            edge_outflow_veh_per_tick=(0.5,),
            edge_free_flow_time_ticks=(3.0,),
            edge_capacity_veh_per_tick=(2.0,),
        ),
    )
    request = ReplayRequest(
        name="replay_baseline_sequence",
        initial_world=world,
        declared_boundary=make_replay_boundary(world, journal),
        journal=journal,
        schedule=schedule,
        num_steps=2,
        step_inputs=step_inputs,
    )

    replay_result = replay_step_world_sequence(request)
    baseline_final_world = run_baseline_sequence(world, schedule, step_inputs)

    assert isinstance(replay_result, ReplayResultRecord)
    assert replay_result.name == "replay_step_world_sequence"
    assert replay_result.final_world == baseline_final_world
    assert replay_result.final_traffic_step == baseline_final_world.traffic.step
    assert replay_result.transition_count == 2


def test_identical_replay_requests_reproduce_identical_outputs():
    journal = InterventionJournal(records=(InterventionRecord(step=0, kind="scenario", payload="equivalent"),))
    world = make_materialized_world(num_edges=1, step=1, seed=21, journal_length=1)
    schedule = TickSchedule(fast_every=1, medium_every=10, slow_every=100)
    request = ReplayRequest(
        name="replay_equivalent_sequence",
        initial_world=world,
        declared_boundary=make_replay_boundary(world, journal),
        journal=journal,
        schedule=schedule,
        num_steps=1,
        step_inputs=(
            ReplayStepInput(
                edge_inflow_veh_per_tick=(0.75,),
                edge_outflow_veh_per_tick=(0.25,),
                edge_free_flow_time_ticks=(4.0,),
                edge_capacity_veh_per_tick=(2.0,),
            ),
        ),
    )

    result_a = replay_step_world_sequence(request)
    result_b = replay_step_world_sequence(request)

    assert result_a == result_b


def test_replay_empty_world_remains_contract_valid():
    world = replace(make_empty_world_state(seed=5), traffic=TrafficState(step=1))
    journal = InterventionJournal()
    request = ReplayRequest(
        name="replay_empty_world",
        initial_world=world,
        declared_boundary=make_replay_boundary(world, journal),
        journal=journal,
        schedule=TickSchedule(fast_every=1, medium_every=10, slow_every=100),
        num_steps=2,
        step_inputs=(ReplayStepInput(), ReplayStepInput()),
    )

    result = replay_step_world_sequence(request)

    assert result.final_world.traffic.step == 3
    assert result.final_world.accessibility.zonal_costs == ()
    assert result.transition_count == 2


def test_replay_and_fingerprint_surfaces_remain_distinct():
    signature = make_replay_input_signature(make_empty_world_state(seed=9), num_steps=3, input_fingerprint="sig")
    journal = InterventionJournal()
    world = replace(make_empty_world_state(seed=9), traffic=TrafficState(step=1))
    result = replay_step_world_sequence(
        ReplayRequest(
            name="replay_distinct_surface",
            initial_world=world,
            declared_boundary=make_replay_boundary(world, journal),
            journal=journal,
            schedule=TickSchedule(),
            num_steps=1,
            step_inputs=(ReplayStepInput(),),
        )
    )

    assert isinstance(signature, ReplayInputSignatureRecord)
    assert isinstance(result, ReplayResultRecord)
    assert not hasattr(signature, "final_world")
    assert not hasattr(signature, "transition_count")
    assert result.name.startswith("replay_")
    assert result.final_world.traffic.step == 2


def test_replay_continues_to_target_step_world_not_runtime_routing_wrapper(monkeypatch: pytest.MonkeyPatch):
    journal = InterventionJournal()
    world = make_materialized_world(num_edges=1, step=1, seed=9, journal_length=0)
    schedule = TickSchedule()
    calls: list[int] = []

    def fake_step_world(current_world, **kwargs):
        calls.append(current_world.traffic.step)
        return replace(
            current_world,
            traffic=replace(current_world.traffic, step=current_world.traffic.step + 1),
        )

    def fail_if_wrapper_called(*args, **kwargs):
        raise AssertionError("replay must not call step_world_with_routing")

    monkeypatch.setattr(replay_module, "step_world", fake_step_world)
    monkeypatch.setattr(replay_module, "step_world_with_routing", fail_if_wrapper_called, raising=False)

    result = replay_step_world_sequence(
        ReplayRequest(
            name="replay_core_boundary_only",
            initial_world=world,
            declared_boundary=make_replay_boundary(world, journal),
            journal=journal,
            schedule=schedule,
            num_steps=2,
            step_inputs=(ReplayStepInput(), ReplayStepInput()),
        )
    )

    assert calls == [1, 2]
    assert result.final_traffic_step == 3


def test_replay_boundary_and_result_record_edge_backend():
    pytest.importorskip("jax")
    world = make_materialized_world(seed=21, step=1, num_edges=1)
    journal = InterventionJournal()
    boundary = make_replay_boundary(world, journal, edge_backend="jax")

    result = replay_step_world_sequence(
        ReplayRequest(
            name="replay_jax_edge_backend",
            initial_world=world,
            declared_boundary=boundary,
            journal=journal,
            schedule=TickSchedule(fast_every=1, medium_every=10, slow_every=100),
            num_steps=1,
            step_inputs=(ReplayStepInput(),),
            edge_backend="jax",
        )
    )

    assert result.initial_boundary.edge_backend == "jax"
    assert result.edge_backend == "jax"


def test_replay_boundary_and_result_record_preserve_rust_cpu_edge_backend():
    world = replace(make_empty_world_state(seed=21), traffic=TrafficState(step=1))
    journal = InterventionJournal()
    boundary = make_replay_boundary(world, journal, edge_backend="rust_cpu")

    result = replay_step_world_sequence(
        ReplayRequest(
            name="replay_rust_cpu_edge_backend",
            initial_world=world,
            declared_boundary=boundary,
            journal=journal,
            schedule=TickSchedule(fast_every=1, medium_every=10, slow_every=100),
            num_steps=1,
            step_inputs=(ReplayStepInput(),),
            edge_backend="rust_cpu",
        )
    )

    assert result.initial_boundary.edge_backend == "rust_cpu"
    assert result.edge_backend == "rust_cpu"


def test_replay_rejects_edge_backend_boundary_mismatch():
    world = make_materialized_world(seed=21, step=1, num_edges=1)
    journal = InterventionJournal()
    boundary = make_replay_boundary(world, journal, edge_backend="baseline")

    with pytest.raises(ValueError, match="edge_backend"):
        replay_step_world_sequence(
            ReplayRequest(
                name="replay_backend_mismatch",
                initial_world=world,
                declared_boundary=boundary,
                journal=journal,
                schedule=TickSchedule(fast_every=1, medium_every=10, slow_every=100),
                num_steps=1,
                step_inputs=(ReplayStepInput(),),
                edge_backend="jax",
            )
        )


def test_replay_is_order_sensitive_through_journal_fingerprint():
    world = make_materialized_world(num_edges=1, step=1, seed=8, journal_length=2)
    schedule = TickSchedule()
    step_inputs = (ReplayStepInput(edge_inflow_veh_per_tick=(1.0,), edge_outflow_veh_per_tick=(0.0,)),)
    journal_a = InterventionJournal(
        records=(
            InterventionRecord(step=1, kind="policy", payload="a"),
            InterventionRecord(step=2, kind="incident", payload="b"),
        )
    )
    journal_b = InterventionJournal(
        records=(
            InterventionRecord(step=2, kind="incident", payload="b"),
            InterventionRecord(step=1, kind="policy", payload="a"),
        )
    )
    request_a = ReplayRequest(
        name="replay_order_a",
        initial_world=world,
        declared_boundary=make_replay_boundary(world, journal_a),
        journal=journal_a,
        schedule=schedule,
        num_steps=1,
        step_inputs=step_inputs,
    )
    request_b = ReplayRequest(
        name="replay_order_b",
        initial_world=world,
        declared_boundary=make_replay_boundary(world, journal_b),
        journal=journal_b,
        schedule=schedule,
        num_steps=1,
        step_inputs=step_inputs,
    )

    result_a = replay_step_world_sequence(request_a)
    result_b = replay_step_world_sequence(request_b)

    assert result_a.journal_fingerprint != result_b.journal_fingerprint


def test_replay_rejects_declared_boundary_mismatch():
    world = make_materialized_world(num_edges=1, step=0, seed=13, journal_length=1)
    journal = InterventionJournal(records=(InterventionRecord(step=0, kind="scenario", payload="mismatch"),))
    mismatched_boundary = ReplayBoundary(
        seed=world.replay.seed,
        initial_traffic_step=99,
        graph_version=world.graph.version,
        landuse_version=world.landuse.version,
        accessibility_version=world.accessibility.version,
        policy_version=world.policy.version,
        journal_length=1,
        journal_fingerprint=journal_fingerprint(journal),
    )

    with pytest.raises(ValueError, match="declared replay boundary must match the supplied initial world"):
        replay_step_world_sequence(
            ReplayRequest(
                name="replay_mismatch",
                initial_world=world,
                declared_boundary=mismatched_boundary,
                journal=journal,
                schedule=TickSchedule(),
                num_steps=1,
                step_inputs=(ReplayStepInput(),),
            )
        )


def test_replay_rejects_num_steps_and_step_inputs_length_mismatch():
    world = make_empty_world_state(seed=1)

    with pytest.raises(ValueError, match="num_steps must match len\\(step_inputs\\)"):
        replay_step_world_sequence(
            ReplayRequest(
                name="replay_length_mismatch",
                initial_world=world,
                declared_boundary=make_replay_boundary(world, InterventionJournal()),
                journal=InterventionJournal(),
                schedule=TickSchedule(),
                num_steps=2,
                step_inputs=(ReplayStepInput(),),
            )
        )


@pytest.mark.parametrize(
    ("schedule", "world", "step_input", "message"),
    (
        (
            TickSchedule(fast_every=5, medium_every=3, slow_every=10),
            make_empty_world_state(seed=4),
            ReplayStepInput(),
            "Invalid multirate ordering",
        ),
        (
            TickSchedule(fast_every=1, medium_every=1, slow_every=5),
            replace(
                make_empty_world_state(seed=4),
                traffic=TrafficState(step=1),
                landuse=LandUseState(
                    version=1,
                    zone_labels=("A",),
                    housing_capacity=(100.0,),
                    jobs_capacity=(120.0,),
                ),
            ),
            ReplayStepInput(),
            "zonal_travel_times and zone_opportunities are required for medium cadence",
        ),
    ),
)
def test_replay_surfaces_invalid_runtime_inputs(schedule, world, step_input, message):
    journal = InterventionJournal()

    with pytest.raises(ValueError, match=message):
        replay_step_world_sequence(
            ReplayRequest(
                name="replay_invalid_runtime_inputs",
                initial_world=world,
                declared_boundary=make_replay_boundary(world, journal),
                journal=journal,
                schedule=schedule,
                num_steps=1,
                step_inputs=(step_input,),
            )
        )
