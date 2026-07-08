use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

const EPS: f64 = 1e-6;
const FLOW_MIN_TRAVEL_COST: f32 = 1.0e-3;

type FlowBatchResult = (
    Vec<f32>,
    Vec<f32>,
    Vec<f32>,
    Vec<f32>,
    Vec<f32>,
    Vec<f32>,
    Vec<f32>,
    Vec<bool>,
    Vec<i32>,
);

fn validate_same_lengths(lengths: &[(&str, usize)]) -> Result<usize, String> {
    let expected = lengths
        .first()
        .map(|(_, length)| *length)
        .ok_or_else(|| "edge batch must include at least one array".to_string())?;
    for (name, length) in lengths {
        if *length != expected {
            return Err(format!(
                "{name} length must match queue length: got {length}, expected {expected}"
            ));
        }
    }
    Ok(expected)
}

fn validate_non_negative(name: &str, values: &[f64]) -> Result<(), String> {
    for value in values {
        if *value < 0.0 {
            return Err(format!("{name} must be non-negative"));
        }
    }
    Ok(())
}

fn validate_non_negative_f32(name: &str, values: &[f32]) -> Result<(), String> {
    for value in values {
        if *value < 0.0 {
            return Err(format!("{name} must be non-negative"));
        }
    }
    Ok(())
}

fn evolve_edges_batch_impl(
    queue: &[f64],
    stock: &[f64],
    inflow: &[f64],
    outflow: &[f64],
    free_flow: &[f64],
    capacity: &[f64],
) -> Result<(Vec<f64>, Vec<f64>, Vec<f64>), String> {
    let num_edges = validate_same_lengths(&[
        ("queue", queue.len()),
        ("stock", stock.len()),
        ("inflow", inflow.len()),
        ("outflow", outflow.len()),
        ("free_flow", free_flow.len()),
        ("capacity", capacity.len()),
    ])?;

    validate_non_negative("queue", queue)?;
    validate_non_negative("stock", stock)?;
    validate_non_negative("inflow", inflow)?;
    validate_non_negative("outflow", outflow)?;
    validate_non_negative("free_flow_time", free_flow)?;
    validate_non_negative("capacity", capacity)?;

    let mut next_queue = Vec::with_capacity(num_edges);
    let mut next_stock = Vec::with_capacity(num_edges);
    let mut next_travel_time = Vec::with_capacity(num_edges);

    for edge_idx in 0..num_edges {
        let queue_value = queue[edge_idx];
        let stock_value = stock[edge_idx];
        if queue_value > stock_value {
            return Err("queue must not exceed stock".to_string());
        }

        let inflow_value = inflow[edge_idx];
        let outflow_value = outflow[edge_idx];
        let free_flow_value = free_flow[edge_idx];
        let capacity_value = capacity[edge_idx];

        let available_mass = stock_value + inflow_value;
        let feasible_outflow = if capacity_value <= 0.0 {
            0.0
        } else {
            outflow_value.min(available_mass).min(capacity_value)
        };
        let stock_after = available_mass - feasible_outflow;
        let queued_mass = queue_value + (inflow_value - feasible_outflow).max(0.0);
        let queue_after = queued_mass.max(0.0).min(stock_after);
        let travel_time_after = free_flow_value + queue_after / capacity_value.max(EPS);

        next_queue.push(queue_after);
        next_stock.push(stock_after);
        next_travel_time.push(travel_time_after);
    }

    Ok((next_queue, next_stock, next_travel_time))
}

fn validate_flow_lengths(
    queue_vehicles: &[f32],
    effective_capacity_vehicles: &[f32],
    base_travel_time_cost: &[f32],
    turn_from_link_index: &[i32],
    turn_to_link_index: &[i32],
    turn_demand: &[f32],
    turn_priority: &[f32],
    turn_is_forbidden: &[bool],
) -> Result<(usize, usize), String> {
    let link_count = queue_vehicles.len();
    if effective_capacity_vehicles.len() != link_count {
        return Err(format!(
            "effective_capacity_vehicles length must match queue_vehicles length: got {}, expected {}",
            effective_capacity_vehicles.len(),
            link_count
        ));
    }
    if base_travel_time_cost.len() != link_count {
        return Err(format!(
            "base_travel_time_cost length must match queue_vehicles length: got {}, expected {}",
            base_travel_time_cost.len(),
            link_count
        ));
    }

    let turn_count = turn_demand.len();
    for (name, length) in [
        ("turn_from_link_index", turn_from_link_index.len()),
        ("turn_to_link_index", turn_to_link_index.len()),
        ("turn_priority", turn_priority.len()),
        ("turn_is_forbidden", turn_is_forbidden.len()),
    ] {
        if length != turn_count {
            return Err(format!(
                "{name} length must match turn_demand length: got {length}, expected {turn_count}"
            ));
        }
    }
    Ok((link_count, turn_count))
}

fn validate_turn_indices(
    turn_from_link_index: &[i32],
    turn_to_link_index: &[i32],
    link_count: usize,
) -> Result<(), String> {
    for value in turn_from_link_index {
        if *value < 0 || (*value as usize) >= link_count {
            return Err("turn_from_link_index contains out-of-range link indices".to_string());
        }
    }
    for value in turn_to_link_index {
        if *value < 0 || (*value as usize) >= link_count {
            return Err("turn_to_link_index contains out-of-range link indices".to_string());
        }
    }
    Ok(())
}

fn segment_sum_f32(values: &[f32], indices: &[i32], segment_count: usize) -> Vec<f32> {
    let mut out = vec![0.0_f32; segment_count];
    for (value, index) in values.iter().zip(indices.iter()) {
        out[*index as usize] += *value;
    }
    out
}

fn update_flow_travel_time_cost(
    base_travel_time_cost: &[f32],
    queue_vehicles: &[f32],
    effective_capacity_vehicles: &[f32],
) -> Vec<f32> {
    base_travel_time_cost
        .iter()
        .zip(queue_vehicles.iter())
        .zip(effective_capacity_vehicles.iter())
        .map(|((base, queue), capacity)| {
            let base_value = base.max(FLOW_MIN_TRAVEL_COST);
            let queue_value = queue.max(0.0);
            let capacity_value = capacity.max(FLOW_MIN_TRAVEL_COST);
            let congestion_ratio = queue_value / (capacity_value + FLOW_MIN_TRAVEL_COST);
            base_value * (1.0 + congestion_ratio)
        })
        .collect()
}

fn increment_signal_timers(signal_phase_timer: &[i32]) -> Vec<i32> {
    signal_phase_timer.iter().map(|timer| timer + 1).collect()
}

fn compute_baseline_flow_arrays_batch_impl(
    queue_vehicles: &[f32],
    effective_capacity_vehicles: &[f32],
    turn_from_link_index: &[i32],
    turn_to_link_index: &[i32],
    turn_demand: &[f32],
    signal_phase_timer: &[i32],
    base_travel_time_cost: &[f32],
    turn_priority: &[f32],
    turn_is_forbidden: &[bool],
) -> Result<FlowBatchResult, String> {
    let (link_count, turn_count) = validate_flow_lengths(
        queue_vehicles,
        effective_capacity_vehicles,
        base_travel_time_cost,
        turn_from_link_index,
        turn_to_link_index,
        turn_demand,
        turn_priority,
        turn_is_forbidden,
    )?;
    validate_non_negative_f32("queue_vehicles", queue_vehicles)?;
    validate_non_negative_f32("effective_capacity_vehicles", effective_capacity_vehicles)?;
    validate_non_negative_f32("turn_demand", turn_demand)?;
    validate_non_negative_f32("base_travel_time_cost", base_travel_time_cost)?;
    validate_non_negative_f32("turn_priority", turn_priority)?;

    let zeros_link = vec![0.0_f32; link_count];
    let zeros_turn = vec![0.0_f32; turn_count];
    let signal_phase_timer_next = increment_signal_timers(signal_phase_timer);

    if link_count == 0 {
        return Ok((
            turn_demand.to_vec(),
            zeros_turn.clone(),
            zeros_turn,
            zeros_link.clone(),
            zeros_link.clone(),
            zeros_link.clone(),
            update_flow_travel_time_cost(base_travel_time_cost, &zeros_link, &zeros_link),
            vec![false; link_count],
            signal_phase_timer_next,
        ));
    }
    if turn_count == 0 {
        return Ok((
            turn_demand.to_vec(),
            zeros_turn.clone(),
            zeros_turn,
            zeros_link.clone(),
            zeros_link,
            queue_vehicles.to_vec(),
            update_flow_travel_time_cost(
                base_travel_time_cost,
                queue_vehicles,
                effective_capacity_vehicles,
            ),
            vec![false; link_count],
            signal_phase_timer_next,
        ));
    }

    validate_turn_indices(turn_from_link_index, turn_to_link_index, link_count)?;

    let mut weighted_demand = Vec::with_capacity(turn_count);
    for turn_idx in 0..turn_count {
        let priority_weight = if turn_is_forbidden[turn_idx] {
            0.0
        } else {
            turn_priority[turn_idx].max(0.0)
        };
        let weighted = if turn_demand[turn_idx] > 0.0 {
            turn_demand[turn_idx] * priority_weight
        } else {
            0.0
        };
        weighted_demand.push(weighted);
    }

    let from_available_link: Vec<f32> = queue_vehicles
        .iter()
        .zip(effective_capacity_vehicles.iter())
        .map(|(queue, capacity)| queue.min(*capacity))
        .collect();
    let receiving_supply_link: Vec<f32> = queue_vehicles
        .iter()
        .zip(effective_capacity_vehicles.iter())
        .map(|(queue, capacity)| (capacity - queue).max(0.0))
        .collect();

    let weighted_by_from = segment_sum_f32(&weighted_demand, turn_from_link_index, link_count);
    let weighted_by_to = segment_sum_f32(&weighted_demand, turn_to_link_index, link_count);

    let mut turn_supply = Vec::with_capacity(turn_count);
    let mut turn_flow = Vec::with_capacity(turn_count);
    for turn_idx in 0..turn_count {
        let from_idx = turn_from_link_index[turn_idx] as usize;
        let to_idx = turn_to_link_index[turn_idx] as usize;
        let from_den = weighted_by_from[from_idx];
        let to_den = weighted_by_to[to_idx];
        let from_share = if from_den > 0.0 {
            weighted_demand[turn_idx] / from_den
        } else {
            0.0
        };
        let to_share = if to_den > 0.0 {
            weighted_demand[turn_idx] / to_den
        } else {
            0.0
        };
        let supply = (from_available_link[from_idx] * from_share)
            .min(receiving_supply_link[to_idx] * to_share);
        let flow = if turn_is_forbidden[turn_idx] {
            0.0
        } else {
            turn_demand[turn_idx].min(supply)
        };
        turn_supply.push(supply.max(0.0));
        turn_flow.push(flow.max(0.0));
    }

    let outflow_vehicles_next = segment_sum_f32(&turn_flow, turn_from_link_index, link_count);
    let inflow_vehicles_next = segment_sum_f32(&turn_flow, turn_to_link_index, link_count);
    let queue_vehicles_next: Vec<f32> = queue_vehicles
        .iter()
        .zip(outflow_vehicles_next.iter())
        .zip(inflow_vehicles_next.iter())
        .map(|((queue, outflow), inflow)| (queue - outflow + inflow).max(0.0))
        .collect();
    let travel_time_cost_next = update_flow_travel_time_cost(
        base_travel_time_cost,
        &queue_vehicles_next,
        effective_capacity_vehicles,
    );
    let capacity_violation_flags_next: Vec<bool> = outflow_vehicles_next
        .iter()
        .zip(effective_capacity_vehicles.iter())
        .map(|(outflow, capacity)| *outflow > (*capacity + 1.0e-6_f32))
        .collect();

    Ok((
        turn_demand.to_vec(),
        turn_supply,
        turn_flow,
        inflow_vehicles_next,
        outflow_vehicles_next,
        queue_vehicles_next,
        travel_time_cost_next,
        capacity_violation_flags_next,
        signal_phase_timer_next,
    ))
}

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

#[pymodule]
fn _metroflow_rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(evolve_edges_batch, m)?)?;
    m.add_function(wrap_pyfunction!(compute_baseline_flow_arrays_batch, m)?)?;
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
}
