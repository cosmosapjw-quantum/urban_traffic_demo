from metroflow.traffic.meso import update_edge_state, project_feasible_movements


def test_update_edge_state_nonnegative():
    st = update_edge_state(queue=0.0, stock=1.0, inflow=2.0, outflow=1.0, free_flow_time=10.0, capacity=2.0)
    assert st.queue >= 0.0
    assert st.stock >= 0.0
    assert st.travel_time >= 10.0


def test_project_feasible_movements():
    out = project_feasible_movements((3.0, 2.0), (1.0, 3.0), (2.0, 2.0))
    assert out == (1.0, 2.0)
