use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use std::cmp::Ordering;
use std::collections::BinaryHeap;

const EPS: f64 = 1e-6;
const FLOW_MIN_TRAVEL_COST: f32 = 1.0e-3;
const ROUTING_INF_COST: f32 = 1.0e12;

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

#[derive(Copy, Clone, Debug, PartialEq)]
struct RoutingHeapState {
    cost: f32,
    node_index: usize,
}

impl Eq for RoutingHeapState {}

impl Ord for RoutingHeapState {
    fn cmp(&self, other: &Self) -> Ordering {
        other
            .cost
            .partial_cmp(&self.cost)
            .unwrap_or(Ordering::Equal)
            .then_with(|| other.node_index.cmp(&self.node_index))
    }
}

impl PartialOrd for RoutingHeapState {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

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

fn validate_routing_inputs(
    node_count: usize,
    incoming_indptr: &[i32],
    incoming_link_indices: &[i32],
    link_src_node_index: &[i32],
    link_travel_time_cost: &[f32],
    blocked_link_mask: &[bool],
    destination_node_index: usize,
) -> Result<usize, String> {
    if destination_node_index >= node_count {
        return Err("destination_node_index out of range".to_string());
    }
    if incoming_indptr.len() != node_count + 1 {
        return Err(format!(
            "incoming_indptr length must be node_count + 1: got {}, expected {}",
            incoming_indptr.len(),
            node_count + 1
        ));
    }
    if incoming_indptr.first().copied().unwrap_or_default() != 0 {
        return Err("incoming_indptr must start at 0".to_string());
    }
    for pair in incoming_indptr.windows(2) {
        if pair[0] > pair[1] {
            return Err("incoming_indptr must be non-decreasing".to_string());
        }
        if pair[0] < 0 || pair[1] < 0 {
            return Err("incoming_indptr must be non-negative".to_string());
        }
    }

    let link_count = link_src_node_index.len();
    if incoming_link_indices.len() != link_count {
        return Err(format!(
            "incoming_link_indices length must match link_src_node_index length: got {}, expected {}",
            incoming_link_indices.len(),
            link_count
        ));
    }
    if link_travel_time_cost.len() != link_count {
        return Err(format!(
            "link_travel_time_cost length must match link_src_node_index length: got {}, expected {}",
            link_travel_time_cost.len(),
            link_count
        ));
    }
    if blocked_link_mask.len() != link_count {
        return Err(format!(
            "blocked_link_mask length must match link_src_node_index length: got {}, expected {}",
            blocked_link_mask.len(),
            link_count
        ));
    }
    if incoming_indptr.last().copied().unwrap_or_default() as usize != link_count {
        return Err("incoming_indptr last value must equal link count".to_string());
    }
    for value in incoming_link_indices {
        if *value < 0 || (*value as usize) >= link_count {
            return Err("incoming_link_indices contains out-of-range link indices".to_string());
        }
    }
    for value in link_src_node_index {
        if *value < 0 || (*value as usize) >= node_count {
            return Err("link_src_node_index contains out-of-range node indices".to_string());
        }
    }
    validate_non_negative_f32("link_travel_time_cost", link_travel_time_cost)?;
    Ok(link_count)
}

fn compute_dynamic_potential_node_costs_impl(
    node_count: usize,
    incoming_indptr: &[i32],
    incoming_link_indices: &[i32],
    link_src_node_index: &[i32],
    link_travel_time_cost: &[f32],
    blocked_link_mask: &[bool],
    destination_node_index: usize,
) -> Result<Vec<f32>, String> {
    validate_routing_inputs(
        node_count,
        incoming_indptr,
        incoming_link_indices,
        link_src_node_index,
        link_travel_time_cost,
        blocked_link_mask,
        destination_node_index,
    )?;

    let mut dist = vec![ROUTING_INF_COST; node_count];
    let mut heap = BinaryHeap::new();
    dist[destination_node_index] = 0.0;
    heap.push(RoutingHeapState {
        cost: 0.0,
        node_index: destination_node_index,
    });

    while let Some(RoutingHeapState { cost, node_index }) = heap.pop() {
        if cost > dist[node_index] {
            continue;
        }
        let start = incoming_indptr[node_index] as usize;
        let end = incoming_indptr[node_index + 1] as usize;
        for pos in start..end {
            let link_index = incoming_link_indices[pos] as usize;
            if blocked_link_mask[link_index] {
                continue;
            }
            let prev_node_index = link_src_node_index[link_index] as usize;
            let candidate = cost + link_travel_time_cost[link_index].max(1.0e-6_f32);
            if candidate < dist[prev_node_index] {
                dist[prev_node_index] = candidate;
                heap.push(RoutingHeapState {
                    cost: candidate,
                    node_index: prev_node_index,
                });
            }
        }
    }
    Ok(dist)
}

fn compute_next_link_action_costs_impl(
    candidate_link_indices: &[i32],
    link_dst_node_index: &[i32],
    node_cost_to_go: &[f32],
    link_travel_time_cost: &[f32],
    blocked_link_mask: &[bool],
) -> Result<Vec<f32>, String> {
    let link_count = link_dst_node_index.len();
    if link_travel_time_cost.len() != link_count {
        return Err(format!(
            "link_travel_time_cost length must match link_dst_node_index length: got {}, expected {}",
            link_travel_time_cost.len(),
            link_count
        ));
    }
    if blocked_link_mask.len() != link_count {
        return Err(format!(
            "blocked_link_mask length must match link_dst_node_index length: got {}, expected {}",
            blocked_link_mask.len(),
            link_count
        ));
    }
    for value in link_dst_node_index {
        if *value < 0 || (*value as usize) >= node_cost_to_go.len() {
            return Err("link_dst_node_index contains out-of-range node indices".to_string());
        }
    }
    for value in candidate_link_indices {
        if *value < 0 || (*value as usize) >= link_count {
            return Err("candidate_link_indices contains out-of-range link indices".to_string());
        }
    }
    validate_non_negative_f32("node_cost_to_go", node_cost_to_go)?;
    validate_non_negative_f32("link_travel_time_cost", link_travel_time_cost)?;

    let mut out = Vec::with_capacity(candidate_link_indices.len());
    for value in candidate_link_indices {
        let link_index = *value as usize;
        let tail = node_cost_to_go[link_dst_node_index[link_index] as usize];
        let total = link_travel_time_cost[link_index] + tail;
        if blocked_link_mask[link_index] || !tail.is_finite() || tail >= ROUTING_INF_COST * 0.5 {
            out.push(ROUTING_INF_COST);
        } else if total >= ROUTING_INF_COST * 0.5 {
            out.push(ROUTING_INF_COST);
        } else {
            out.push(total);
        }
    }
    Ok(out)
}

#[allow(clippy::too_many_arguments)]
fn validate_greedy_route_inputs(
    node_count: usize,
    link_ids: &[i32],
    link_dst_node_index: &[i32],
    outgoing_indptr: &[i32],
    outgoing_link_indices: &[i32],
    turn_from_link_index: &[i32],
    turn_to_link_index: &[i32],
    turn_is_forbidden: &[bool],
    node_cost_to_go: &[f32],
    link_travel_time_cost: &[f32],
    blocked_link_mask: &[bool],
    origin_node_index: usize,
    destination_node_index: usize,
    incoming_link_index: i32,
    max_hops: usize,
) -> Result<usize, String> {
    if max_hops == 0 {
        return Err("max_hops must be >= 1".to_string());
    }
    if origin_node_index >= node_count {
        return Err("origin_node_index out of range".to_string());
    }
    if destination_node_index >= node_count {
        return Err("destination_node_index out of range".to_string());
    }
    if node_cost_to_go.len() != node_count {
        return Err(format!(
            "node_cost_to_go length must match node_count: got {}, expected {}",
            node_cost_to_go.len(),
            node_count
        ));
    }

    let link_count = link_ids.len();
    for (name, length) in [
        ("link_dst_node_index", link_dst_node_index.len()),
        ("link_travel_time_cost", link_travel_time_cost.len()),
        ("blocked_link_mask", blocked_link_mask.len()),
    ] {
        if length != link_count {
            return Err(format!(
                "{name} length must match link_ids length: got {length}, expected {link_count}"
            ));
        }
    }
    if outgoing_indptr.len() != node_count + 1 {
        return Err(format!(
            "outgoing_indptr length must be node_count + 1: got {}, expected {}",
            outgoing_indptr.len(),
            node_count + 1
        ));
    }
    if outgoing_indptr.first().copied().unwrap_or_default() != 0 {
        return Err("outgoing_indptr must start at 0".to_string());
    }
    for pair in outgoing_indptr.windows(2) {
        if pair[0] > pair[1] {
            return Err("outgoing_indptr must be non-decreasing".to_string());
        }
        if pair[0] < 0 || pair[1] < 0 {
            return Err("outgoing_indptr must be non-negative".to_string());
        }
    }
    if outgoing_indptr.last().copied().unwrap_or_default() as usize != outgoing_link_indices.len() {
        return Err("outgoing_indptr last value must equal outgoing link index count".to_string());
    }
    if outgoing_link_indices.len() != link_count {
        return Err(format!(
            "outgoing_link_indices length must match link_ids length: got {}, expected {}",
            outgoing_link_indices.len(),
            link_count
        ));
    }
    for value in outgoing_link_indices {
        if *value < 0 || (*value as usize) >= link_count {
            return Err("outgoing_link_indices contains out-of-range link indices".to_string());
        }
    }
    for value in link_dst_node_index {
        if *value < 0 || (*value as usize) >= node_count {
            return Err("link_dst_node_index contains out-of-range node indices".to_string());
        }
    }
    if incoming_link_index != -1
        && (incoming_link_index < 0 || incoming_link_index as usize >= link_count)
    {
        return Err("incoming_link_index out of range".to_string());
    }

    let turn_count = turn_from_link_index.len();
    if turn_to_link_index.len() != turn_count {
        return Err(format!(
            "turn_to_link_index length must match turn_from_link_index length: got {}, expected {}",
            turn_to_link_index.len(),
            turn_count
        ));
    }
    if turn_is_forbidden.len() != turn_count {
        return Err(format!(
            "turn_is_forbidden length must match turn_from_link_index length: got {}, expected {}",
            turn_is_forbidden.len(),
            turn_count
        ));
    }
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
    validate_non_negative_f32("node_cost_to_go", node_cost_to_go)?;
    validate_non_negative_f32("link_travel_time_cost", link_travel_time_cost)?;
    Ok(link_count)
}

#[allow(clippy::too_many_arguments)]
fn best_legal_next_link_index(
    current_node_index: usize,
    incoming_link_index: i32,
    link_ids: &[i32],
    link_dst_node_index: &[i32],
    outgoing_indptr: &[i32],
    outgoing_link_indices: &[i32],
    turn_from_link_index: &[i32],
    turn_to_link_index: &[i32],
    turn_is_forbidden: &[bool],
    node_cost_to_go: &[f32],
    link_travel_time_cost: &[f32],
    blocked_link_mask: &[bool],
) -> Option<usize> {
    let link_count = link_ids.len();
    let mut allowed_by_turn = vec![false; link_count];
    let mut require_turn_successor = false;
    if incoming_link_index >= 0 && !turn_from_link_index.is_empty() {
        require_turn_successor = true;
        let incoming = incoming_link_index;
        let mut saw_successor = false;
        for turn_index in 0..turn_from_link_index.len() {
            if turn_from_link_index[turn_index] == incoming {
                saw_successor = true;
                if !turn_is_forbidden[turn_index] {
                    allowed_by_turn[turn_to_link_index[turn_index] as usize] = true;
                }
            }
        }
        if !saw_successor {
            return None;
        }
    }

    let start = outgoing_indptr[current_node_index] as usize;
    let end = outgoing_indptr[current_node_index + 1] as usize;
    let mut best_link_index: Option<usize> = None;
    let mut best_cost = ROUTING_INF_COST;
    for pos in start..end {
        let link_index = outgoing_link_indices[pos] as usize;
        if require_turn_successor && !allowed_by_turn[link_index] {
            continue;
        }
        if blocked_link_mask[link_index] {
            continue;
        }
        let tail = node_cost_to_go[link_dst_node_index[link_index] as usize];
        if !tail.is_finite() || tail >= ROUTING_INF_COST * 0.5 {
            continue;
        }
        let total_cost = link_travel_time_cost[link_index] + tail;
        if total_cost >= ROUTING_INF_COST * 0.5 {
            continue;
        }
        match best_link_index {
            None => {
                best_link_index = Some(link_index);
                best_cost = total_cost;
            }
            Some(current_best) => {
                if total_cost < best_cost
                    || (total_cost == best_cost && link_ids[link_index] < link_ids[current_best])
                {
                    best_link_index = Some(link_index);
                    best_cost = total_cost;
                }
            }
        }
    }
    best_link_index
}

#[allow(clippy::too_many_arguments)]
fn compute_greedy_route_candidate_impl(
    node_count: usize,
    link_ids: &[i32],
    link_dst_node_index: &[i32],
    outgoing_indptr: &[i32],
    outgoing_link_indices: &[i32],
    turn_from_link_index: &[i32],
    turn_to_link_index: &[i32],
    turn_is_forbidden: &[bool],
    node_cost_to_go: &[f32],
    link_travel_time_cost: &[f32],
    blocked_link_mask: &[bool],
    origin_node_index: usize,
    destination_node_index: usize,
    incoming_link_index: i32,
    max_hops: usize,
) -> Result<Vec<i32>, String> {
    validate_greedy_route_inputs(
        node_count,
        link_ids,
        link_dst_node_index,
        outgoing_indptr,
        outgoing_link_indices,
        turn_from_link_index,
        turn_to_link_index,
        turn_is_forbidden,
        node_cost_to_go,
        link_travel_time_cost,
        blocked_link_mask,
        origin_node_index,
        destination_node_index,
        incoming_link_index,
        max_hops,
    )?;

    if origin_node_index == destination_node_index {
        return Ok(Vec::new());
    }

    let mut current_node_index = origin_node_index;
    let mut current_incoming_link_index = incoming_link_index;
    let mut visited_nodes = vec![false; node_count];
    visited_nodes[current_node_index] = true;
    let mut path = Vec::new();

    for _ in 0..max_hops {
        let Some(next_link_index) = best_legal_next_link_index(
            current_node_index,
            current_incoming_link_index,
            link_ids,
            link_dst_node_index,
            outgoing_indptr,
            outgoing_link_indices,
            turn_from_link_index,
            turn_to_link_index,
            turn_is_forbidden,
            node_cost_to_go,
            link_travel_time_cost,
            blocked_link_mask,
        ) else {
            return Ok(Vec::new());
        };
        path.push(link_ids[next_link_index]);
        current_incoming_link_index = next_link_index as i32;
        current_node_index = link_dst_node_index[next_link_index] as usize;
        if current_node_index == destination_node_index {
            return Ok(path);
        }
        if visited_nodes[current_node_index] {
            return Ok(Vec::new());
        }
        visited_nodes[current_node_index] = true;
    }

    Ok(Vec::new())
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

#[pymodule]
fn _metroflow_rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(evolve_edges_batch, m)?)?;
    m.add_function(wrap_pyfunction!(compute_baseline_flow_arrays_batch, m)?)?;
    m.add_function(wrap_pyfunction!(compute_dynamic_potential_node_costs, m)?)?;
    m.add_function(wrap_pyfunction!(compute_next_link_action_costs, m)?)?;
    m.add_function(wrap_pyfunction!(compute_greedy_route_candidate, m)?)?;
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
}
