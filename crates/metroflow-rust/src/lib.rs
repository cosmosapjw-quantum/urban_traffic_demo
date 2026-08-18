use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
mod agent;
mod common;
mod edge;
mod flow;
mod reroute;
mod routing;

use agent::advance_active_agents_batch_impl;
#[cfg(test)]
use common::ROUTING_INF_COST;
use common::{AgentBatchResult, FlowBatchResult};
use edge::evolve_edges_batch_impl;
use flow::compute_baseline_flow_arrays_batch_impl;
use reroute::compute_reroute_decision_batch_impl;
use routing::{
    compute_dynamic_potential_node_costs_impl, compute_greedy_route_candidate_impl,
    compute_multi_destination_dynamic_potentials_impl, compute_next_link_action_costs_impl,
    compute_ranked_route_candidates_batch_impl, compute_ranked_route_candidates_impl,
    compute_route_candidate_metadata_impl, select_route_candidate_index_impl,
};

#[pyfunction]
fn evolve_edges_batch(
    queue: Vec<f64>,
    stock: Vec<f64>,
    inflow: Vec<f64>,
    outflow: Vec<f64>,
    free_flow: Vec<f64>,
    capacity: Vec<f64>,
) -> PyResult<(Vec<f64>, Vec<f64>, Vec<f64>)> {
    evolve_edges_batch_impl(&queue, &stock, &inflow, &outflow, &free_flow, &capacity)
        .map_err(PyValueError::new_err)
}

#[pyfunction]
fn compute_baseline_flow_arrays_batch(
    queue_vehicles: Vec<f32>,
    effective_capacity_vehicles: Vec<f32>,
    turn_from_link_index: Vec<i32>,
    turn_to_link_index: Vec<i32>,
    turn_demand: Vec<f32>,
    signal_phase_timer: Vec<i32>,
    base_travel_time_cost: Vec<f32>,
    turn_priority: Vec<f32>,
    turn_is_forbidden: Vec<bool>,
) -> PyResult<FlowBatchResult> {
    compute_baseline_flow_arrays_batch_impl(
        &queue_vehicles,
        &effective_capacity_vehicles,
        &turn_from_link_index,
        &turn_to_link_index,
        &turn_demand,
        &signal_phase_timer,
        &base_travel_time_cost,
        &turn_priority,
        &turn_is_forbidden,
    )
    .map_err(PyValueError::new_err)
}

#[pyfunction]
fn compute_dynamic_potential_node_costs(
    node_count: usize,
    incoming_indptr: Vec<i32>,
    incoming_link_indices: Vec<i32>,
    link_src_node_index: Vec<i32>,
    link_travel_time_cost: Vec<f32>,
    blocked_link_mask: Vec<bool>,
    destination_node_index: usize,
) -> PyResult<Vec<f32>> {
    compute_dynamic_potential_node_costs_impl(
        node_count,
        &incoming_indptr,
        &incoming_link_indices,
        &link_src_node_index,
        &link_travel_time_cost,
        &blocked_link_mask,
        destination_node_index,
    )
    .map_err(PyValueError::new_err)
}

#[pyfunction]
fn compute_multi_destination_dynamic_potentials(
    node_count: usize,
    incoming_indptr: Vec<i32>,
    incoming_link_indices: Vec<i32>,
    link_src_node_index: Vec<i32>,
    link_travel_time_cost: Vec<f32>,
    blocked_link_mask: Vec<bool>,
    destination_node_indices: Vec<usize>,
) -> PyResult<Vec<Vec<f32>>> {
    compute_multi_destination_dynamic_potentials_impl(
        node_count,
        &incoming_indptr,
        &incoming_link_indices,
        &link_src_node_index,
        &link_travel_time_cost,
        &blocked_link_mask,
        &destination_node_indices,
    )
    .map_err(PyValueError::new_err)
}

#[pyfunction]
fn compute_next_link_action_costs(
    candidate_link_indices: Vec<i32>,
    link_dst_node_index: Vec<i32>,
    node_cost_to_go: Vec<f32>,
    link_travel_time_cost: Vec<f32>,
    blocked_link_mask: Vec<bool>,
) -> PyResult<Vec<f32>> {
    compute_next_link_action_costs_impl(
        &candidate_link_indices,
        &link_dst_node_index,
        &node_cost_to_go,
        &link_travel_time_cost,
        &blocked_link_mask,
    )
    .map_err(PyValueError::new_err)
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn compute_greedy_route_candidate(
    node_count: usize,
    link_ids: Vec<i32>,
    link_dst_node_index: Vec<i32>,
    outgoing_indptr: Vec<i32>,
    outgoing_link_indices: Vec<i32>,
    turn_from_link_index: Vec<i32>,
    turn_to_link_index: Vec<i32>,
    turn_is_forbidden: Vec<bool>,
    node_cost_to_go: Vec<f32>,
    link_travel_time_cost: Vec<f32>,
    blocked_link_mask: Vec<bool>,
    origin_node_index: usize,
    destination_node_index: usize,
    incoming_link_index: i32,
    max_hops: usize,
) -> PyResult<Vec<i32>> {
    compute_greedy_route_candidate_impl(
        node_count,
        &link_ids,
        &link_dst_node_index,
        &outgoing_indptr,
        &outgoing_link_indices,
        &turn_from_link_index,
        &turn_to_link_index,
        &turn_is_forbidden,
        &node_cost_to_go,
        &link_travel_time_cost,
        &blocked_link_mask,
        origin_node_index,
        destination_node_index,
        incoming_link_index,
        max_hops,
    )
    .map_err(PyValueError::new_err)
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn compute_ranked_route_candidates(
    node_count: usize,
    link_ids: Vec<i32>,
    link_dst_node_index: Vec<i32>,
    outgoing_indptr: Vec<i32>,
    outgoing_link_indices: Vec<i32>,
    turn_from_link_index: Vec<i32>,
    turn_to_link_index: Vec<i32>,
    turn_is_forbidden: Vec<bool>,
    node_cost_to_go: Vec<f32>,
    link_travel_time_cost: Vec<f32>,
    blocked_link_mask: Vec<bool>,
    origin_node_index: usize,
    destination_node_index: usize,
    incoming_link_index: i32,
    max_hops: usize,
    max_candidates: usize,
) -> PyResult<Vec<Vec<i32>>> {
    compute_ranked_route_candidates_impl(
        node_count,
        &link_ids,
        &link_dst_node_index,
        &outgoing_indptr,
        &outgoing_link_indices,
        &turn_from_link_index,
        &turn_to_link_index,
        &turn_is_forbidden,
        &node_cost_to_go,
        &link_travel_time_cost,
        &blocked_link_mask,
        origin_node_index,
        destination_node_index,
        incoming_link_index,
        max_hops,
        max_candidates,
    )
    .map_err(PyValueError::new_err)
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn compute_ranked_route_candidates_batch(
    node_count: usize,
    link_ids: Vec<i32>,
    link_dst_node_index: Vec<i32>,
    outgoing_indptr: Vec<i32>,
    outgoing_link_indices: Vec<i32>,
    turn_from_link_index: Vec<i32>,
    turn_to_link_index: Vec<i32>,
    turn_is_forbidden: Vec<bool>,
    node_costs_to_go: Vec<Vec<f32>>,
    link_travel_time_cost: Vec<f32>,
    blocked_link_mask: Vec<bool>,
    origins: Vec<usize>,
    destinations: Vec<usize>,
    incomings: Vec<i32>,
    max_hops: usize,
    max_candidates: usize,
) -> PyResult<Vec<Vec<Vec<i32>>>> {
    compute_ranked_route_candidates_batch_impl(
        node_count,
        &link_ids,
        &link_dst_node_index,
        &outgoing_indptr,
        &outgoing_link_indices,
        &turn_from_link_index,
        &turn_to_link_index,
        &turn_is_forbidden,
        &node_costs_to_go,
        &link_travel_time_cost,
        &blocked_link_mask,
        &origins,
        &destinations,
        &incomings,
        max_hops,
        max_candidates,
    )
    .map_err(PyValueError::new_err)
}

#[pyfunction]
fn compute_route_candidate_metadata(
    link_ids: Vec<i32>,
    link_length_m: Vec<f32>,
    link_travel_time_cost: Vec<f32>,
    candidate_paths: Vec<Vec<i32>>,
) -> PyResult<(Vec<f32>, Vec<f32>)> {
    compute_route_candidate_metadata_impl(
        &link_ids,
        &link_length_m,
        &link_travel_time_cost,
        &candidate_paths,
    )
    .map_err(PyValueError::new_err)
}

#[pyfunction]
fn select_route_candidate_index(
    candidate_ids: Vec<i32>,
    candidate_paths: Vec<Vec<i32>>,
    candidate_path_costs: Vec<f32>,
    candidate_path_size_factors: Vec<f32>,
    path_size_gamma: f32,
) -> PyResult<(i32, f32)> {
    select_route_candidate_index_impl(
        &candidate_ids,
        &candidate_paths,
        &candidate_path_costs,
        &candidate_path_size_factors,
        path_size_gamma,
    )
    .map_err(PyValueError::new_err)
}

#[pyfunction]
fn compute_reroute_decision_batch(
    reroute_willingness: Vec<f32>,
    delay_sensitivity: Vec<f32>,
    exploration_bias: Vec<f32>,
    persistence_bias: Vec<f32>,
    improvement_ratio: Vec<f32>,
) -> PyResult<(Vec<bool>, Vec<f32>)> {
    compute_reroute_decision_batch_impl(
        &reroute_willingness,
        &delay_sensitivity,
        &exploration_bias,
        &persistence_bias,
        &improvement_ratio,
    )
    .map_err(PyValueError::new_err)
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn advance_active_agents_batch(
    slot_ids: Vec<i32>,
    trip_ids: Vec<i32>,
    current_link_ids: Vec<i32>,
    route_ptrs: Vec<i32>,
    cooldown_ticks: Vec<i32>,
    route_offsets: Vec<i32>,
    route_link_ids: Vec<i32>,
    movement_budget_link_ids: Vec<i32>,
    movement_budget_counts: Vec<i32>,
    completion_budget_link_ids: Vec<i32>,
    completion_budget_counts: Vec<i32>,
    skip_slot_ids: Vec<i32>,
) -> PyResult<AgentBatchResult> {
    advance_active_agents_batch_impl(
        &slot_ids,
        &trip_ids,
        &current_link_ids,
        &route_ptrs,
        &cooldown_ticks,
        &route_offsets,
        &route_link_ids,
        &movement_budget_link_ids,
        &movement_budget_counts,
        &completion_budget_link_ids,
        &completion_budget_counts,
        &skip_slot_ids,
    )
    .map_err(PyValueError::new_err)
}

#[pymodule]
fn _metroflow_rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(evolve_edges_batch, m)?)?;
    m.add_function(wrap_pyfunction!(compute_baseline_flow_arrays_batch, m)?)?;
    m.add_function(wrap_pyfunction!(compute_dynamic_potential_node_costs, m)?)?;
    m.add_function(wrap_pyfunction!(compute_multi_destination_dynamic_potentials, m)?)?;
    m.add_function(wrap_pyfunction!(compute_next_link_action_costs, m)?)?;
    m.add_function(wrap_pyfunction!(compute_greedy_route_candidate, m)?)?;
    m.add_function(wrap_pyfunction!(compute_ranked_route_candidates, m)?)?;
    m.add_function(wrap_pyfunction!(compute_ranked_route_candidates_batch, m)?)?;
    m.add_function(wrap_pyfunction!(compute_route_candidate_metadata, m)?)?;
    m.add_function(wrap_pyfunction!(select_route_candidate_index, m)?)?;
    m.add_function(wrap_pyfunction!(compute_reroute_decision_batch, m)?)?;
    m.add_function(wrap_pyfunction!(advance_active_agents_batch, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn evolves_normal_batch() {
        let (queue, stock, travel_time) = evolve_edges_batch_impl(
            &[0.0, 1.0],
            &[1.0, 2.0],
            &[2.0, 0.5],
            &[1.0, 1.5],
            &[10.0, 12.0],
            &[2.0, 4.0],
        )
        .expect("batch should evolve");

        assert_eq!(queue, vec![1.0, 1.0]);
        assert_eq!(stock, vec![2.0, 1.0]);
        assert_eq!(travel_time, vec![10.5, 12.25]);
    }

    #[test]
    fn evolves_zero_capacity_with_eps_travel_time() {
        let (queue, stock, travel_time) =
            evolve_edges_batch_impl(&[0.0], &[1.0], &[2.0], &[1.0], &[5.0], &[0.0])
                .expect("zero capacity is a valid closed edge");

        assert_eq!(queue, vec![2.0]);
        assert_eq!(stock, vec![3.0]);
        assert_eq!(travel_time, vec![2_000_005.0]);
    }

    #[test]
    fn rejects_negative_input() {
        let error = evolve_edges_batch_impl(&[-1.0], &[1.0], &[0.0], &[0.0], &[1.0], &[1.0])
            .expect_err("negative queue should be rejected");

        assert_eq!(error, "queue must be non-negative");
    }

    #[test]
    fn rejects_length_mismatch() {
        let error = evolve_edges_batch_impl(
            &[0.0, 0.0],
            &[1.0],
            &[0.0, 0.0],
            &[0.0, 0.0],
            &[1.0, 1.0],
            &[1.0, 1.0],
        )
        .expect_err("length mismatch should be rejected");

        assert!(error.contains("stock length must match queue length"));
    }

    #[test]
    fn rejects_queue_above_stock() {
        let error = evolve_edges_batch_impl(&[2.0], &[1.0], &[0.0], &[0.0], &[1.0], &[1.0])
            .expect_err("queue above stock should be rejected");

        assert_eq!(error, "queue must not exceed stock");
    }

    #[test]
    fn edge_module_preserves_batch_evolution_contract() {
        let (queue, stock, travel_time) =
            crate::edge::evolve_edges_batch_impl(&[0.0], &[1.0], &[2.0], &[1.0], &[10.0], &[2.0])
                .expect("edge module should evolve a batch");

        assert_eq!(queue, vec![1.0]);
        assert_eq!(stock, vec![2.0]);
        assert_eq!(travel_time, vec![10.5]);
    }

    #[test]
    fn computes_flow_normal_update() {
        let result = compute_baseline_flow_arrays_batch_impl(
            &[4.0, 0.0],
            &[2.0, 2.0],
            &[0],
            &[1],
            &[3.0],
            &[0],
            &[2.0, 2.0],
            &[1.0],
            &[false],
        )
        .expect("flow batch should update");

        assert_eq!(result.0, vec![3.0]);
        assert_eq!(result.2, vec![2.0]);
        assert_eq!(result.3, vec![0.0, 2.0]);
        assert_eq!(result.4, vec![2.0, 0.0]);
        assert_eq!(result.5, vec![2.0, 2.0]);
        assert_eq!(result.7, vec![false, false]);
        assert_eq!(result.8, vec![1]);
    }

    #[test]
    fn flow_module_preserves_baseline_array_contract() {
        let result = crate::flow::compute_baseline_flow_arrays_batch_impl(
            &[4.0, 0.0],
            &[2.0, 2.0],
            &[0],
            &[1],
            &[3.0],
            &[0],
            &[2.0, 2.0],
            &[1.0],
            &[false],
        )
        .expect("flow module should compute baseline arrays");

        assert_eq!(result.2, vec![2.0]);
        assert_eq!(result.5, vec![2.0, 2.0]);
        assert_eq!(result.8, vec![1]);
    }

    #[test]
    fn flow_point_queue_uses_rate_supply_and_additive_waiting_ticks() {
        let result = compute_baseline_flow_arrays_batch_impl(
            &[1.0, 2.0],
            &[1.0, 2.0],
            &[0],
            &[1],
            &[1.0],
            &[0, 0],
            &[2.0, 4.0],
            &[1.0],
            &[false],
        )
        .expect("point-queue flow should update");

        assert_eq!(result.2, vec![1.0]);
        assert_eq!(result.5, vec![0.0, 3.0]);
        assert_eq!(result.6, vec![2.0, 5.5]);
    }

    #[test]
    fn computes_flow_zero_turns() {
        let result = compute_baseline_flow_arrays_batch_impl(
            &[2.0, 0.0],
            &[1.0, 3.0],
            &[],
            &[],
            &[],
            &[4],
            &[5.0, 6.0],
            &[],
            &[],
        )
        .expect("zero-turn flow batch should update");

        assert!(result.0.is_empty());
        assert_eq!(result.5, vec![2.0, 0.0]);
        assert_eq!(result.7, vec![false, false]);
        assert_eq!(result.8, vec![5]);
    }

    #[test]
    fn computes_flow_zero_links() {
        let result =
            compute_baseline_flow_arrays_batch_impl(&[], &[], &[], &[], &[], &[4], &[], &[], &[])
                .expect("zero-link flow batch should update");

        assert!(result.3.is_empty());
        assert!(result.5.is_empty());
        assert!(result.7.is_empty());
        assert_eq!(result.8, vec![5]);
    }

    #[test]
    fn computes_flow_with_forbidden_and_priority_weighting() {
        let result = compute_baseline_flow_arrays_batch_impl(
            &[6.0, 0.0, 0.0],
            &[4.0, 10.0, 10.0],
            &[0, 0, 1],
            &[1, 2, 2],
            &[1.0, 3.0, 5.0],
            &[0],
            &[1.0, 1.0, 1.0],
            &[1.0, 3.0, 1.0],
            &[false, false, true],
        )
        .expect("priority and forbidden turns should update");

        assert!(result.2[1] > result.2[0]);
        assert_eq!(result.2[2], 0.0);
    }

    #[test]
    fn rejects_flow_length_mismatch() {
        let error = compute_baseline_flow_arrays_batch_impl(
            &[1.0, 2.0],
            &[1.0],
            &[],
            &[],
            &[],
            &[0],
            &[1.0, 1.0],
            &[],
            &[],
        )
        .expect_err("length mismatch should be rejected");

        assert!(error.contains("effective_capacity_vehicles length must match"));
    }

    #[test]
    fn rejects_flow_invalid_turn_index() {
        let error = compute_baseline_flow_arrays_batch_impl(
            &[1.0],
            &[1.0],
            &[1],
            &[0],
            &[1.0],
            &[0],
            &[1.0],
            &[1.0],
            &[false],
        )
        .expect_err("invalid turn index should be rejected");

        assert_eq!(
            error,
            "turn_from_link_index contains out-of-range link indices"
        );
    }

    #[test]
    fn rejects_flow_negative_numeric_input() {
        let error = compute_baseline_flow_arrays_batch_impl(
            &[-1.0],
            &[1.0],
            &[],
            &[],
            &[],
            &[0],
            &[1.0],
            &[],
            &[],
        )
        .expect_err("negative queue should be rejected");

        assert_eq!(error, "queue_vehicles must be non-negative");
    }

    #[test]
    fn computes_routing_potential_normal_path() {
        let node_cost = compute_dynamic_potential_node_costs_impl(
            3,
            &[0, 0, 1, 2],
            &[0, 1],
            &[0, 1],
            &[2.0, 3.0],
            &[false, false],
            2,
        )
        .expect("routing potential should compute");

        assert_eq!(node_cost, vec![5.0, 3.0, 0.0]);
    }

    #[test]
    fn routing_module_preserves_dynamic_potential_contract() {
        let node_cost = crate::routing::compute_dynamic_potential_node_costs_impl(
            3,
            &[0, 0, 1, 2],
            &[0, 1],
            &[0, 1],
            &[2.0, 3.0],
            &[false, false],
            2,
        )
        .expect("routing module should compute potential");

        assert_eq!(node_cost, vec![5.0, 3.0, 0.0]);
    }

    #[test]
    fn computes_routing_potential_with_blocked_link() {
        let node_cost = compute_dynamic_potential_node_costs_impl(
            3,
            &[0, 0, 1, 2],
            &[0, 1],
            &[0, 1],
            &[2.0, 3.0],
            &[true, false],
            2,
        )
        .expect("blocked routing potential should compute");

        assert!(node_cost[0] >= 1.0e11_f32);
        assert_eq!(node_cost[1], 3.0);
        assert_eq!(node_cost[2], 0.0);
    }

    #[test]
    fn computes_routing_potential_for_zero_links() {
        let node_cost =
            compute_dynamic_potential_node_costs_impl(2, &[0, 0, 0], &[], &[], &[], &[], 1)
                .expect("zero-link routing potential should compute");

        assert!(node_cost[0] >= 1.0e11_f32);
        assert_eq!(node_cost[1], 0.0);
    }

    #[test]
    fn rejects_routing_invalid_index() {
        let error = compute_dynamic_potential_node_costs_impl(
            2,
            &[0, 0, 1],
            &[0],
            &[2],
            &[1.0],
            &[false],
            1,
        )
        .expect_err("invalid link source should be rejected");

        assert_eq!(
            error,
            "link_src_node_index contains out-of-range node indices"
        );
    }

    #[test]
    fn rejects_routing_length_mismatch() {
        let error = compute_dynamic_potential_node_costs_impl(
            2,
            &[0, 0, 1],
            &[0],
            &[0],
            &[1.0, 2.0],
            &[false],
            1,
        )
        .expect_err("routing length mismatch should be rejected");

        assert!(error.contains("link_travel_time_cost length must match"));
    }

    #[test]
    fn computes_greedy_route_candidate_normal_path() {
        let path = compute_greedy_route_candidate_impl(
            4,
            &[10, 11, 12, 13],
            &[1, 3, 2, 3],
            &[0, 2, 3, 4, 4],
            &[0, 2, 1, 3],
            &[],
            &[],
            &[],
            &[2.0, 1.0, 1.0, 0.0],
            &[50.0, 1.0, 1.0, 1.0],
            &[false, false, false, false],
            0,
            3,
            -1,
            8,
        )
        .expect("greedy route should compute");

        assert_eq!(path, vec![12, 13]);
    }

    #[test]
    fn computes_greedy_route_candidate_with_forbidden_turn() {
        let path = compute_greedy_route_candidate_impl(
            4,
            &[10, 11, 12, 13],
            &[1, 3, 2, 3],
            &[0, 1, 3, 4, 4],
            &[0, 1, 2, 3],
            &[0, 0, 2],
            &[1, 2, 3],
            &[true, false, false],
            &[7.0, 2.0, 1.0, 0.0],
            &[1.0, 1.0, 5.0, 1.0],
            &[false, false, false, false],
            0,
            3,
            -1,
            8,
        )
        .expect("forbidden-turn greedy route should compute");

        assert_eq!(path, vec![10, 12, 13]);
    }

    #[test]
    fn computes_greedy_route_candidate_empty_when_unreachable() {
        let path = compute_greedy_route_candidate_impl(
            4,
            &[10, 11, 12, 13],
            &[1, 3, 2, 3],
            &[0, 2, 3, 4, 4],
            &[0, 2, 1, 3],
            &[],
            &[],
            &[],
            &[2.0, 1.0, 1.0, 0.0],
            &[50.0, 1.0, 1.0, 1.0],
            &[true, false, true, false],
            0,
            3,
            -1,
            8,
        )
        .expect("unreachable greedy route should return no path");

        assert!(path.is_empty());
    }

    #[test]
    fn computes_ranked_route_candidates_normal_paths() {
        let paths = compute_ranked_route_candidates_impl(
            4,
            &[10, 11, 12, 13],
            &[1, 3, 2, 3],
            &[0, 2, 3, 4, 4],
            &[0, 2, 1, 3],
            &[],
            &[],
            &[],
            &[2.0, 1.0, 1.0, 0.0],
            &[50.0, 1.0, 1.0, 1.0],
            &[false, false, false, false],
            0,
            3,
            -1,
            8,
            2,
        )
        .expect("ranked routes should compute");

        assert_eq!(paths, vec![vec![12, 13], vec![10, 11]]);
    }

    #[test]
    fn computes_ranked_route_candidates_with_forbidden_turn() {
        let paths = compute_ranked_route_candidates_impl(
            4,
            &[10, 11, 12, 13],
            &[1, 3, 2, 3],
            &[0, 1, 3, 4, 4],
            &[0, 1, 2, 3],
            &[0, 0, 2],
            &[1, 2, 3],
            &[true, false, false],
            &[7.0, 2.0, 1.0, 0.0],
            &[1.0, 1.0, 5.0, 1.0],
            &[false, false, false, false],
            0,
            3,
            -1,
            8,
            2,
        )
        .expect("forbidden-turn ranked routes should compute");

        assert_eq!(paths, vec![vec![10, 12, 13]]);
    }

    #[test]
    fn computes_route_candidate_metadata_costs_and_path_size() {
        let (costs, path_size) = compute_route_candidate_metadata_impl(
            &[10, 11, 12],
            &[100.0, 50.0, 50.0],
            &[2.0, 3.0, 5.0],
            &[vec![10, 11], vec![10, 12]],
        )
        .expect("route metadata should compute");

        assert_eq!(costs, vec![5.0, 7.0]);
        assert_eq!(path_size, vec![2.0 / 3.0, 2.0 / 3.0]);
    }

    #[test]
    fn computes_route_candidate_metadata_empty_path() {
        let (costs, path_size) =
            compute_route_candidate_metadata_impl(&[10], &[100.0], &[2.0], &[vec![]])
                .expect("empty route metadata should compute");

        assert_eq!(costs, vec![0.0]);
        assert_eq!(path_size, vec![1.0]);
    }

    #[test]
    fn rejects_route_candidate_metadata_unknown_link_id() {
        let error = compute_route_candidate_metadata_impl(&[10], &[100.0], &[2.0], &[vec![11]])
            .expect_err("unknown link id should be rejected");

        assert_eq!(error, "candidate_paths contains unknown link id");
    }

    #[test]
    fn rejects_route_candidate_metadata_length_mismatch() {
        let error =
            compute_route_candidate_metadata_impl(&[10, 11], &[100.0], &[2.0, 3.0], &[vec![10]])
                .expect_err("length mismatch should be rejected");

        assert!(error.contains("link_length_m length must match link_ids length"));
    }

    #[test]
    fn selects_route_candidate_with_path_size_utility() {
        let (index, utility) = select_route_candidate_index_impl(
            &[7, 8],
            &[vec![10], vec![10, 11]],
            &[2.0, 3.0],
            &[0.2, 1.0],
            2.0,
        )
        .expect("candidate selection should compute");

        assert_eq!(index, 1);
        assert_eq!(utility, -3.0);
    }

    #[test]
    fn selects_route_candidate_first_viable_when_costs_are_missing() {
        let (index, utility) =
            select_route_candidate_index_impl(&[7, 8], &[vec![], vec![10]], &[], &[], 2.0)
                .expect("missing cost selection should compute");

        assert_eq!(index, 1);
        assert_eq!(utility, 0.0);
    }

    #[test]
    fn selects_route_candidate_tie_by_candidate_id_then_path() {
        let (index, _utility) = select_route_candidate_index_impl(
            &[9, 7, 7],
            &[vec![10, 11], vec![20], vec![10, 12]],
            &[3.0, 3.0, 3.0],
            &[1.0, 1.0, 1.0],
            0.0,
        )
        .expect("tie-break selection should compute");

        assert_eq!(index, 2);
    }

    #[test]
    fn selects_route_candidate_empty_when_no_viable_path() {
        let (index, utility) =
            select_route_candidate_index_impl(&[7], &[vec![]], &[2.0], &[1.0], 0.0)
                .expect("empty selection should compute");

        assert_eq!(index, -1);
        assert_eq!(utility, 0.0);
    }

    #[test]
    fn rejects_route_candidate_selection_negative_link_id() {
        let error = select_route_candidate_index_impl(&[7], &[vec![-10]], &[2.0], &[1.0], 0.0)
            .expect_err("negative link id should be rejected");

        assert_eq!(error, "candidate_paths must contain non-negative link ids");
    }

    #[test]
    fn computes_reroute_decision_batch() {
        let (should, scores) = compute_reroute_decision_batch_impl(
            &[0.9, 0.1],
            &[1.0, 0.0],
            &[0.2, 0.0],
            &[0.0, 2.0],
            &[0.5, 0.1],
        )
        .expect("reroute decision should compute");

        assert_eq!(should, vec![true, false]);
        assert!((scores[0] - 0.641875).abs() < 1.0e-6);
        assert!((scores[1] - 0.07125).abs() < 1.0e-6);
    }

    #[test]
    fn reroute_module_preserves_decision_contract() {
        let (should, scores) = crate::reroute::compute_reroute_decision_batch_impl(
            &[0.9],
            &[1.0],
            &[0.2],
            &[0.0],
            &[0.5],
        )
        .expect("reroute module should compute decisions");

        assert_eq!(should, vec![true]);
        assert!((scores[0] - 0.641875).abs() < 1.0e-6);
    }

    #[test]
    fn rejects_reroute_decision_length_mismatch() {
        let error = compute_reroute_decision_batch_impl(
            &[0.9, 0.1],
            &[1.0],
            &[0.2, 0.0],
            &[0.0, 2.0],
            &[0.5, 0.1],
        )
        .expect_err("length mismatch should be rejected");

        assert_eq!(error, "reroute decision inputs must have equal lengths");
    }

    #[test]
    fn rejects_greedy_route_invalid_outgoing_index() {
        let error = compute_greedy_route_candidate_impl(
            2,
            &[10],
            &[1],
            &[0, 1, 1],
            &[3],
            &[],
            &[],
            &[],
            &[1.0, 0.0],
            &[1.0],
            &[false],
            0,
            1,
            -1,
            4,
        )
        .expect_err("invalid outgoing link index should be rejected");

        assert_eq!(
            error,
            "outgoing_link_indices contains out-of-range link indices"
        );
    }

    #[test]
    fn rejects_greedy_route_length_mismatch() {
        let error = compute_greedy_route_candidate_impl(
            2,
            &[10],
            &[1, 1],
            &[0, 1, 1],
            &[0],
            &[],
            &[],
            &[],
            &[1.0, 0.0],
            &[1.0],
            &[false],
            0,
            1,
            -1,
            4,
        )
        .expect_err("link length mismatch should be rejected");

        assert!(error.contains("link_dst_node_index length must match"));
    }

    #[test]
    fn computes_next_link_action_costs_normal_batch() {
        let costs = compute_next_link_action_costs_impl(
            &[0, 2],
            &[1, 3, 2, 3],
            &[2.0, 1.0, 1.0, 0.0],
            &[50.0, 1.0, 1.0, 1.0],
            &[false, false, false, false],
        )
        .expect("next-link action costs should compute");

        assert_eq!(costs, vec![51.0, 2.0]);
    }

    #[test]
    fn computes_next_link_action_costs_with_blocked_and_unreachable_links() {
        let costs = compute_next_link_action_costs_impl(
            &[0, 1, 2],
            &[1, 3, 2, 3],
            &[0.0, ROUTING_INF_COST, 1.0, 0.0],
            &[50.0, 1.0, 1.0, 1.0],
            &[false, true, false, false],
        )
        .expect("blocked and unreachable action costs should compute");

        assert!(costs[0] >= ROUTING_INF_COST * 0.5);
        assert!(costs[1] >= ROUTING_INF_COST * 0.5);
        assert_eq!(costs[2], 2.0);
    }

    #[test]
    fn rejects_next_link_action_cost_invalid_candidate_index() {
        let error = compute_next_link_action_costs_impl(
            &[4],
            &[1, 3, 2, 3],
            &[2.0, 1.0, 1.0, 0.0],
            &[50.0, 1.0, 1.0, 1.0],
            &[false, false, false, false],
        )
        .expect_err("invalid candidate link should be rejected");

        assert_eq!(
            error,
            "candidate_link_indices contains out-of-range link indices"
        );
    }

    #[test]
    fn rejects_next_link_action_cost_length_mismatch() {
        let error = compute_next_link_action_costs_impl(
            &[0],
            &[1, 3],
            &[2.0, 1.0, 1.0, 0.0],
            &[50.0],
            &[false, false],
        )
        .expect_err("length mismatch should be rejected");

        assert!(error.contains("link_travel_time_cost length must match"));
    }

    #[test]
    fn advances_active_agent_with_movement_budget() {
        let result = advance_active_agents_batch_impl(
            &[0],
            &[101],
            &[10],
            &[0],
            &[2],
            &[0, 2],
            &[10, 11],
            &[10],
            &[1],
            &[],
            &[],
            &[],
        )
        .expect("agent action plan should compute");

        assert_eq!(result.0, vec![11]);
        assert_eq!(result.1, vec![1]);
        assert_eq!(result.2, vec![1]);
        assert_eq!(result.3, vec![0]);
        assert!(result.4.is_empty());
        assert!(result.5.is_empty());
        assert!(result.6.is_empty());
    }

    #[test]
    fn agent_module_preserves_action_planner_contract() {
        let result = crate::agent::advance_active_agents_batch_impl(
            &[0],
            &[100],
            &[10],
            &[0],
            &[2],
            &[0, 2],
            &[10, 11],
            &[10],
            &[1],
            &[],
            &[],
            &[],
        )
        .expect("agent module should plan movement");

        assert_eq!(result.0, vec![11]);
        assert_eq!(result.1, vec![1]);
        assert_eq!(result.3, vec![0]);
    }

    #[test]
    fn active_agent_waits_at_sink_when_completion_budget_is_zero() {
        let result = advance_active_agents_batch_impl(
            &[0],
            &[101],
            &[11],
            &[1],
            &[0],
            &[0, 2],
            &[10, 11],
            &[],
            &[],
            &[11],
            &[0],
            &[],
        )
        .expect("sink wait action plan should compute");

        assert_eq!(result.4, vec![0]);
        assert!(result.5.is_empty());
        assert!(result.6.is_empty());
    }

    #[test]
    fn active_agent_completes_when_sink_budget_is_available() {
        let result = advance_active_agents_batch_impl(
            &[0],
            &[101],
            &[11],
            &[1],
            &[0],
            &[0, 2],
            &[10, 11],
            &[],
            &[],
            &[11],
            &[1],
            &[],
        )
        .expect("completion action plan should compute");

        assert!(result.4.is_empty());
        assert_eq!(result.5, vec![0]);
        assert_eq!(result.6, vec![101]);
    }

    #[test]
    fn active_agent_skip_slot_does_not_move() {
        let result = advance_active_agents_batch_impl(
            &[0],
            &[101],
            &[10],
            &[0],
            &[2],
            &[0, 2],
            &[10, 11],
            &[10],
            &[1],
            &[],
            &[],
            &[0],
        )
        .expect("skipped action plan should compute");

        assert_eq!(result.0, vec![10]);
        assert_eq!(result.1, vec![0]);
        assert_eq!(result.2, vec![2]);
        assert!(result.3.is_empty());
    }

    #[test]
    fn active_agent_empty_route_releases_slot() {
        let result = advance_active_agents_batch_impl(
            &[0],
            &[101],
            &[10],
            &[0],
            &[0],
            &[0, 0],
            &[],
            &[10],
            &[1],
            &[],
            &[],
            &[],
        )
        .expect("empty route release should compute");

        assert_eq!(result.5, vec![0]);
        assert_eq!(result.6, vec![101]);
    }

    #[test]
    fn active_agent_shared_link_budget_uses_slot_order() {
        let result = advance_active_agents_batch_impl(
            &[0, 1],
            &[101, 102],
            &[10, 10],
            &[0, 0],
            &[0, 0],
            &[0, 2, 4],
            &[10, 11, 10, 12],
            &[10],
            &[1],
            &[],
            &[],
            &[],
        )
        .expect("shared budget should compute");

        assert_eq!(result.0, vec![11, 10]);
        assert_eq!(result.1, vec![1, 0]);
        assert_eq!(result.3, vec![0]);
    }

    #[test]
    fn rejects_active_agent_length_mismatch() {
        let error = advance_active_agents_batch_impl(
            &[0],
            &[101, 102],
            &[10],
            &[0],
            &[0],
            &[0, 2],
            &[10, 11],
            &[],
            &[],
            &[],
            &[],
            &[],
        )
        .expect_err("length mismatch should be rejected");

        assert!(error.contains("trip_ids length must match slot_ids length"));
    }

    #[test]
    fn rejects_active_agent_route_offset_mismatch() {
        let error = advance_active_agents_batch_impl(
            &[0],
            &[101],
            &[10],
            &[0],
            &[0],
            &[0, 3],
            &[10, 11],
            &[],
            &[],
            &[],
            &[],
            &[],
        )
        .expect_err("invalid route offset should be rejected");

        assert_eq!(error, "route_offsets contains out-of-range offsets");
    }
}
