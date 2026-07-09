use crate::common::{validate_non_negative_f32, FlowBatchResult, FLOW_MIN_TRAVEL_COST};

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

pub(crate) fn compute_baseline_flow_arrays_batch_impl(
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
