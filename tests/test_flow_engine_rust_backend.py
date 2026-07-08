import numpy as np
import pytest

import metroflow.flow.engine as flow_engine
from metroflow.flow.engine import (
    FLOW_UPDATE_BACKENDS,
    compute_baseline_flow_arrays,
    compute_baseline_flow_arrays_core,
    update_link_node_flow,
)
from metroflow.flow.state import LinkState, NodeState


def make_link_state() -> LinkState:
    return LinkState(
        queue_vehicles=(5.0, 1.0, 0.0),
        inflow_vehicles=(0.0, 0.0, 0.0),
        outflow_vehicles=(0.0, 0.0, 0.0),
        travel_time_cost=(10.0, 20.0, 30.0),
        capacity_veh_per_tick=(3.0, 4.0, 2.0),
        incident_capacity_multiplier=(1.0, 1.0, 1.0),
        metadata={"free_flow_travel_time_cost": np.asarray([10.0, 20.0, 30.0], dtype=np.float32)},
    )


def make_node_state() -> NodeState:
    return NodeState(
        turn_from_link_index=(0, 0, 1, 2),
        turn_to_link_index=(1, 2, 2, 0),
        turn_demand=(3.0, 2.0, 2.0, 1.0),
        turn_supply=(0.0, 0.0, 0.0, 0.0),
        turn_flow=(0.0, 0.0, 0.0, 0.0),
        signal_phase_index=(0, 1),
        signal_phase_timer=(2, 0),
        metadata={
            "turn_base_priority": np.asarray([1.0, 2.0, 1.0, 1.0], dtype=np.float32),
            "turn_is_forbidden": np.asarray([False, False, True, False], dtype=np.bool_),
        },
    )


def assert_flow_arrays_close(actual: dict[str, np.ndarray], expected: dict[str, np.ndarray]) -> None:
    for key, expected_value in expected.items():
        if key == "base_travel_time_cost":
            continue
        actual_value = actual[key]
        if np.asarray(expected_value).dtype == np.dtype("bool"):
            np.testing.assert_array_equal(actual_value, expected_value, err_msg=key)
        elif np.asarray(expected_value).dtype.kind in {"i", "u"}:
            np.testing.assert_array_equal(actual_value, expected_value, err_msg=key)
        else:
            np.testing.assert_allclose(actual_value, expected_value, rtol=1e-6, atol=1e-6, err_msg=key)


def test_flow_backend_registry_accepts_rust_cpu():
    assert FLOW_UPDATE_BACKENDS == ("baseline", "rust_cpu", "auto")


def test_update_link_node_flow_accepts_rust_cpu_backend_with_wrapper(monkeypatch: pytest.MonkeyPatch):
    links = make_link_state()
    nodes = make_node_state()
    baseline = compute_baseline_flow_arrays(link_state=links, node_state=nodes)

    def fake_rust(**kwargs):
        return baseline

    monkeypatch.setattr(flow_engine, "_compute_baseline_flow_arrays_rust", fake_rust, raising=False)

    result = update_link_node_flow(links, nodes, validate=True, flow_backend="rust_cpu")

    assert tuple(result.node_state.turn_flow.tolist()) == tuple(baseline["turn_flow_next"].tolist())
    assert tuple(result.link_state.queue_vehicles.tolist()) == tuple(baseline["queue_vehicles_next"].tolist())


def test_explicit_rust_flow_backend_is_fail_closed(monkeypatch: pytest.MonkeyPatch):
    def fail_rust(**kwargs):
        raise RuntimeError("Rust CPU flow backend unavailable")

    monkeypatch.setattr(flow_engine, "_compute_baseline_flow_arrays_rust", fail_rust, raising=False)

    with pytest.raises(RuntimeError, match="Rust CPU flow backend unavailable"):
        compute_baseline_flow_arrays_core(
            queue_vehicles=(1.0,),
            effective_capacity_vehicles=(1.0,),
            turn_from_link_index=(),
            turn_to_link_index=(),
            turn_demand=(),
            signal_phase_timer=(0,),
            base_travel_time_cost=(1.0,),
            flow_backend="rust_cpu",
        )


def test_auto_flow_backend_falls_back_to_baseline_when_rust_fails(monkeypatch: pytest.MonkeyPatch):
    def fail_rust(**kwargs):
        raise RuntimeError("simulated rust flow backend failure")

    monkeypatch.setattr(flow_engine, "_compute_baseline_flow_arrays_rust", fail_rust, raising=False)
    kwargs = {
        "queue_vehicles": (5.0, 1.0, 0.0),
        "effective_capacity_vehicles": (3.0, 4.0, 2.0),
        "turn_from_link_index": (0, 0, 1, 2),
        "turn_to_link_index": (1, 2, 2, 0),
        "turn_demand": (3.0, 2.0, 2.0, 1.0),
        "signal_phase_timer": (2, 0),
        "base_travel_time_cost": (10.0, 20.0, 30.0),
        "turn_priority": (1.0, 2.0, 1.0, 1.0),
        "turn_is_forbidden": (False, False, True, False),
    }

    baseline = compute_baseline_flow_arrays_core(**kwargs, flow_backend="baseline")
    automatic = compute_baseline_flow_arrays_core(**kwargs, flow_backend="auto")

    assert_flow_arrays_close(automatic, baseline)


def test_rust_flow_backend_matches_baseline_output():
    rust_module = pytest.importorskip("_metroflow_rust")
    if not hasattr(rust_module, "compute_baseline_flow_arrays_batch"):
        pytest.skip("_metroflow_rust flow backend is not built")
    links = make_link_state()
    nodes = make_node_state()

    baseline = compute_baseline_flow_arrays(link_state=links, node_state=nodes)
    accelerated = compute_baseline_flow_arrays(link_state=links, node_state=nodes, flow_backend="rust_cpu")

    assert_flow_arrays_close(accelerated, baseline)
    assert accelerated["capacity_violation_flags_next"].dtype == np.dtype("bool")
    assert accelerated["signal_phase_timer_next"].dtype == np.dtype("int32")


def test_rust_flow_backend_matches_baseline_for_zero_turn_and_zero_link_cases():
    rust_module = pytest.importorskip("_metroflow_rust")
    if not hasattr(rust_module, "compute_baseline_flow_arrays_batch"):
        pytest.skip("_metroflow_rust flow backend is not built")

    zero_turn_kwargs = {
        "queue_vehicles": (2.0, 0.0),
        "effective_capacity_vehicles": (1.0, 3.0),
        "turn_from_link_index": (),
        "turn_to_link_index": (),
        "turn_demand": (),
        "signal_phase_timer": (4,),
        "base_travel_time_cost": (5.0, 6.0),
    }
    zero_link_kwargs = {
        "queue_vehicles": (),
        "effective_capacity_vehicles": (),
        "turn_from_link_index": (),
        "turn_to_link_index": (),
        "turn_demand": (),
        "signal_phase_timer": (4,),
        "base_travel_time_cost": (),
    }

    for kwargs in (zero_turn_kwargs, zero_link_kwargs):
        baseline = compute_baseline_flow_arrays_core(**kwargs, flow_backend="baseline")
        accelerated = compute_baseline_flow_arrays_core(**kwargs, flow_backend="rust_cpu")
        assert_flow_arrays_close(accelerated, baseline)
