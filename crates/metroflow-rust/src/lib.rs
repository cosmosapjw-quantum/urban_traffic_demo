use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use std::cmp::Ordering;
use std::collections::{BinaryHeap, HashMap, HashSet};

mod common;
mod edge;
mod flow;

use common::{validate_non_negative_f32, AgentBatchResult, FlowBatchResult, ROUTING_INF_COST};
use edge::evolve_edges_batch_impl;
use flow::compute_baseline_flow_arrays_batch_impl;

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

#[derive(Clone, Debug, PartialEq)]
struct RankedRouteHeapState {
    estimated_cost: f32,
    path_cost: f32,
    serial: usize,
    path: Vec<i32>,
    current_node_index: usize,
    incoming_link_index: i32,
    visited_nodes: Vec<bool>,
}

impl Eq for RankedRouteHeapState {}

impl Ord for RankedRouteHeapState {
    fn cmp(&self, other: &Self) -> Ordering {
        other
            .estimated_cost
            .partial_cmp(&self.estimated_cost)
            .unwrap_or(Ordering::Equal)
            .then_with(|| {
                other
                    .path_cost
                    .partial_cmp(&self.path_cost)
                    .unwrap_or(Ordering::Equal)
            })
            .then_with(|| other.serial.cmp(&self.serial))
    }
}

impl PartialOrd for RankedRouteHeapState {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
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

#[allow(clippy::too_many_arguments)]
fn scored_legal_next_link_indices(
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
) -> Vec<(f32, i32, usize)> {
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
            return Vec::new();
        }
    }

    let start = outgoing_indptr[current_node_index] as usize;
    let end = outgoing_indptr[current_node_index + 1] as usize;
    let mut scored = Vec::new();
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
        scored.push((total_cost, link_ids[link_index], link_index));
    }
    scored.sort_by(|left, right| {
        left.0
            .partial_cmp(&right.0)
            .unwrap_or(Ordering::Equal)
            .then_with(|| left.1.cmp(&right.1))
    });
    scored
}

#[allow(clippy::too_many_arguments)]
fn compute_ranked_route_candidates_impl(
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
    max_candidates: usize,
) -> Result<Vec<Vec<i32>>, String> {
    if max_candidates == 0 {
        return Err("max_candidates must be >= 1".to_string());
    }
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

    let mut paths: Vec<Vec<i32>> = Vec::new();
    let mut seen_paths: HashSet<Vec<i32>> = HashSet::new();
    let mut heap = BinaryHeap::new();
    let mut serial = 0usize;
    let mut initial_visited = vec![false; node_count];
    initial_visited[origin_node_index] = true;
    heap.push(RankedRouteHeapState {
        estimated_cost: 0.0,
        path_cost: 0.0,
        serial,
        path: Vec::new(),
        current_node_index: origin_node_index,
        incoming_link_index,
        visited_nodes: initial_visited,
    });

    let max_expansions = max_candidates * usize::max(16, link_ids.len() * 4);
    let mut expansions = 0usize;
    while let Some(state) = heap.pop() {
        if paths.len() >= max_candidates || expansions >= max_expansions {
            break;
        }
        expansions += 1;
        if state.current_node_index == destination_node_index && !state.path.is_empty() {
            if seen_paths.insert(state.path.clone()) {
                paths.push(state.path);
            }
            continue;
        }
        if state.path.len() >= max_hops {
            continue;
        }

        for (_action_cost, link_id, link_index) in scored_legal_next_link_indices(
            state.current_node_index,
            state.incoming_link_index,
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
        ) {
            let next_node_index = link_dst_node_index[link_index] as usize;
            if state.visited_nodes[next_node_index] {
                continue;
            }
            let step_cost = link_travel_time_cost[link_index];
            if !step_cost.is_finite() || step_cost >= ROUTING_INF_COST * 0.5 {
                continue;
            }
            let tail_cost = if next_node_index == destination_node_index {
                0.0
            } else {
                node_cost_to_go[next_node_index]
            };
            if !tail_cost.is_finite() || tail_cost >= ROUTING_INF_COST * 0.5 {
                continue;
            }
            let mut next_path = state.path.clone();
            next_path.push(link_id);
            let next_path_cost = state.path_cost + step_cost;
            let mut next_visited = state.visited_nodes.clone();
            next_visited[next_node_index] = true;
            serial += 1;
            heap.push(RankedRouteHeapState {
                estimated_cost: next_path_cost + tail_cost,
                path_cost: next_path_cost,
                serial,
                path: next_path,
                current_node_index: next_node_index,
                incoming_link_index: link_index as i32,
                visited_nodes: next_visited,
            });
        }
    }

    Ok(paths)
}

fn compute_route_candidate_metadata_impl(
    link_ids: &[i32],
    link_length_m: &[f32],
    link_travel_time_cost: &[f32],
    candidate_paths: &[Vec<i32>],
) -> Result<(Vec<f32>, Vec<f32>), String> {
    let link_count = link_ids.len();
    if link_length_m.len() != link_count {
        return Err(format!(
            "link_length_m length must match link_ids length: got {}, expected {}",
            link_length_m.len(),
            link_count
        ));
    }
    if link_travel_time_cost.len() != link_count {
        return Err(format!(
            "link_travel_time_cost length must match link_ids length: got {}, expected {}",
            link_travel_time_cost.len(),
            link_count
        ));
    }
    validate_non_negative_f32("link_length_m", link_length_m)?;
    validate_non_negative_f32("link_travel_time_cost", link_travel_time_cost)?;

    let mut link_index_by_id: HashMap<i32, usize> = HashMap::with_capacity(link_count);
    for (index, link_id) in link_ids.iter().enumerate() {
        if link_index_by_id.insert(*link_id, index).is_some() {
            return Err("link_ids must be unique".to_string());
        }
    }

    let mut usage_count: HashMap<i32, usize> = HashMap::new();
    for path in candidate_paths {
        for link_id in path {
            if !link_index_by_id.contains_key(link_id) {
                return Err("candidate_paths contains unknown link id".to_string());
            }
            *usage_count.entry(*link_id).or_insert(0) += 1;
        }
    }

    let mut costs = Vec::with_capacity(candidate_paths.len());
    let mut path_size_factors = Vec::with_capacity(candidate_paths.len());
    for path in candidate_paths {
        let mut cost = 0.0_f32;
        let mut lengths = Vec::with_capacity(path.len());
        for link_id in path {
            let link_index = *link_index_by_id
                .get(link_id)
                .ok_or_else(|| "candidate_paths contains unknown link id".to_string())?;
            cost += link_travel_time_cost[link_index];
            lengths.push(link_length_m[link_index].max(1.0e-6_f32));
        }
        costs.push(cost);

        let total_length: f32 = lengths.iter().sum();
        if total_length <= 0.0 {
            path_size_factors.push(1.0);
            continue;
        }
        let mut factor = 0.0_f32;
        for (link_id, length_m) in path.iter().zip(lengths.iter()) {
            let usage = *usage_count.get(link_id).unwrap_or(&1) as f32;
            factor += (*length_m / total_length) * (1.0 / usage.max(1.0));
        }
        path_size_factors.push(factor.max(1.0e-12_f32));
    }

    Ok((costs, path_size_factors))
}

fn route_candidate_utility(cost: f32, path_size_factor: f32, path_size_gamma: f32) -> f32 {
    if !cost.is_finite() {
        return f32::NEG_INFINITY;
    }
    let path_size = if path_size_factor.is_finite() && path_size_factor > 0.0 {
        path_size_factor
    } else {
        1.0e-12_f32
    };
    -cost + path_size_gamma.max(0.0) * path_size.ln()
}

fn route_path_tiebreak_greater(candidate: &[i32], best: &[i32]) -> bool {
    for (candidate_link, best_link) in candidate.iter().zip(best.iter()) {
        if candidate_link != best_link {
            return candidate_link < best_link;
        }
    }
    candidate.len() > best.len()
}

fn route_selection_tiebreak_greater(
    candidate_index: usize,
    candidate_path: &[i32],
    best_index: usize,
    best_path: &[i32],
    candidate_ids: &[i32],
) -> bool {
    let candidate_id = candidate_ids
        .get(candidate_index)
        .copied()
        .unwrap_or(candidate_index as i32);
    let best_id = candidate_ids
        .get(best_index)
        .copied()
        .unwrap_or(best_index as i32);
    if candidate_id != best_id {
        return candidate_id < best_id;
    }
    route_path_tiebreak_greater(candidate_path, best_path)
}

fn select_route_candidate_index_impl(
    candidate_ids: &[i32],
    candidate_paths: &[Vec<i32>],
    candidate_path_costs: &[f32],
    candidate_path_size_factors: &[f32],
    path_size_gamma: f32,
) -> Result<(i32, f32), String> {
    for candidate_id in candidate_ids {
        if *candidate_id < 0 {
            return Err("candidate_ids must be non-negative".to_string());
        }
    }
    for path in candidate_paths {
        for link_id in path {
            if *link_id < 0 {
                return Err("candidate_paths must contain non-negative link ids".to_string());
            }
        }
    }

    let viable_indices: Vec<usize> = candidate_paths
        .iter()
        .enumerate()
        .filter_map(|(index, path)| if path.is_empty() { None } else { Some(index) })
        .collect();
    if viable_indices.is_empty() {
        return Ok((-1, 0.0));
    }
    if candidate_path_costs.len() < candidate_paths.len() {
        return Ok((viable_indices[0] as i32, 0.0));
    }

    let mut best_index = viable_indices[0];
    let mut best_utility = route_candidate_utility(
        candidate_path_costs[best_index],
        candidate_path_size_factors
            .get(best_index)
            .copied()
            .unwrap_or(1.0),
        path_size_gamma,
    );
    for candidate_index in viable_indices.iter().copied().skip(1) {
        let utility = route_candidate_utility(
            candidate_path_costs[candidate_index],
            candidate_path_size_factors
                .get(candidate_index)
                .copied()
                .unwrap_or(1.0),
            path_size_gamma,
        );
        let is_better = utility > best_utility
            || (utility == best_utility
                && route_selection_tiebreak_greater(
                    candidate_index,
                    &candidate_paths[candidate_index],
                    best_index,
                    &candidate_paths[best_index],
                    candidate_ids,
                ));
        if is_better {
            best_index = candidate_index;
            best_utility = utility;
        }
    }

    Ok((best_index as i32, best_utility))
}

fn clamp01(value: f32) -> f32 {
    if value < 0.0 {
        0.0
    } else if value > 1.0 {
        1.0
    } else {
        value
    }
}

fn nonnegative_or_nan(value: f32) -> f32 {
    if value < 0.0 {
        0.0
    } else {
        value
    }
}

fn compute_reroute_decision_batch_impl(
    reroute_willingness: &[f32],
    delay_sensitivity: &[f32],
    exploration_bias: &[f32],
    persistence_bias: &[f32],
    improvement_ratio: &[f32],
) -> Result<(Vec<bool>, Vec<f32>), String> {
    let len = reroute_willingness.len();
    if delay_sensitivity.len() != len
        || exploration_bias.len() != len
        || persistence_bias.len() != len
        || improvement_ratio.len() != len
    {
        return Err("reroute decision inputs must have equal lengths".to_string());
    }

    let mut should = Vec::with_capacity(len);
    let mut scores = Vec::with_capacity(len);
    for index in 0..len {
        let reroute = clamp01(reroute_willingness[index]);
        let delay = delay_sensitivity[index];
        let explore = clamp01(exploration_bias[index]);
        let improvement = nonnegative_or_nan(improvement_ratio[index]);
        let delay_norm = if delay > 0.0 {
            delay / (1.0 + delay)
        } else {
            0.0
        };
        let trigger_score = 0.45 * reroute
            + 0.35 * (improvement * (0.75 + 0.75 * delay_norm)).min(1.0)
            + 0.20 * explore;
        let persistence = persistence_bias[index].abs();
        let resistance = 0.40
            + 0.15
                * if persistence > 0.0 {
                    persistence / (1.0 + persistence)
                } else {
                    0.0
                };
        should.push(trigger_score >= resistance && reroute_willingness[index] > 0.0);
        scores.push(trigger_score);
    }
    Ok((should, scores))
}

#[allow(clippy::too_many_arguments)]
fn advance_active_agents_batch_impl(
    slot_ids: &[i32],
    trip_ids: &[i32],
    current_link_ids: &[i32],
    route_ptrs: &[i32],
    cooldown_ticks: &[i32],
    route_offsets: &[i32],
    route_link_ids: &[i32],
    movement_budget_link_ids: &[i32],
    movement_budget_counts: &[i32],
    completion_budget_link_ids: &[i32],
    completion_budget_counts: &[i32],
    skip_slot_ids: &[i32],
) -> Result<AgentBatchResult, String> {
    let slot_count = slot_ids.len();
    for (name, length) in [
        ("trip_ids", trip_ids.len()),
        ("current_link_ids", current_link_ids.len()),
        ("route_ptrs", route_ptrs.len()),
        ("cooldown_ticks", cooldown_ticks.len()),
    ] {
        if length != slot_count {
            return Err(format!(
                "{name} length must match slot_ids length: got {length}, expected {slot_count}"
            ));
        }
    }
    if route_offsets.len() != slot_count + 1 {
        return Err(format!(
            "route_offsets length must be slot_ids length + 1: got {}, expected {}",
            route_offsets.len(),
            slot_count + 1
        ));
    }
    if movement_budget_link_ids.len() != movement_budget_counts.len() {
        return Err("movement budget ids/counts must have equal lengths".to_string());
    }
    if completion_budget_link_ids.len() != completion_budget_counts.len() {
        return Err("completion budget ids/counts must have equal lengths".to_string());
    }

    let mut previous_offset = 0_i32;
    for offset in route_offsets {
        if *offset < previous_offset {
            return Err("route_offsets must be non-decreasing".to_string());
        }
        if *offset < 0 || (*offset as usize) > route_link_ids.len() {
            return Err("route_offsets contains out-of-range offsets".to_string());
        }
        previous_offset = *offset;
    }
    if route_offsets.last().copied().unwrap_or_default() as usize != route_link_ids.len() {
        return Err("route_offsets last value must equal route_link_ids length".to_string());
    }
    for (name, values) in [
        ("slot_ids", slot_ids),
        ("trip_ids", trip_ids),
        ("current_link_ids", current_link_ids),
        ("route_ptrs", route_ptrs),
        ("cooldown_ticks", cooldown_ticks),
        ("route_link_ids", route_link_ids),
        ("movement_budget_link_ids", movement_budget_link_ids),
        ("movement_budget_counts", movement_budget_counts),
        ("completion_budget_link_ids", completion_budget_link_ids),
        ("completion_budget_counts", completion_budget_counts),
        ("skip_slot_ids", skip_slot_ids),
    ] {
        if values.iter().any(|value| *value < 0) {
            return Err(format!("{name} must be non-negative"));
        }
    }

    let mut movement_budget: HashMap<i32, i32> = HashMap::new();
    for (link_id, count) in movement_budget_link_ids
        .iter()
        .zip(movement_budget_counts.iter())
    {
        movement_budget
            .entry(*link_id)
            .and_modify(|existing| *existing += *count)
            .or_insert(*count);
    }
    let mut completion_budget: HashMap<i32, i32> = HashMap::new();
    for (link_id, count) in completion_budget_link_ids
        .iter()
        .zip(completion_budget_counts.iter())
    {
        completion_budget
            .entry(*link_id)
            .and_modify(|existing| *existing += *count)
            .or_insert(*count);
    }
    let skip_slots: HashSet<i32> = skip_slot_ids.iter().copied().collect();
    let mut next_current_link_ids = current_link_ids.to_vec();
    let mut next_route_ptrs = route_ptrs.to_vec();
    let mut next_cooldown_ticks = cooldown_ticks.to_vec();
    let mut moved_slot_ids = Vec::new();
    let mut sink_wait_slot_ids = Vec::new();
    let mut released_slot_ids = Vec::new();
    let mut completed_trip_ids = Vec::new();

    for idx in 0..slot_count {
        let slot_id = slot_ids[idx];
        if skip_slots.contains(&slot_id) {
            continue;
        }
        let start = route_offsets[idx] as usize;
        let end = route_offsets[idx + 1] as usize;
        let path = &route_link_ids[start..end];
        if path.is_empty() {
            released_slot_ids.push(slot_id);
            completed_trip_ids.push(trip_ids[idx]);
            continue;
        }
        let current_link_id = current_link_ids[idx];
        let ptr = route_ptrs[idx] as usize;
        if ptr >= path.len().saturating_sub(1) {
            let remaining = completion_budget
                .get(&current_link_id)
                .copied()
                .unwrap_or(0);
            if remaining <= 0 {
                sink_wait_slot_ids.push(slot_id);
                continue;
            }
            completion_budget.insert(current_link_id, remaining - 1);
            released_slot_ids.push(slot_id);
            completed_trip_ids.push(trip_ids[idx]);
            continue;
        }
        let remaining = movement_budget.get(&current_link_id).copied().unwrap_or(0);
        if remaining <= 0 {
            continue;
        }
        movement_budget.insert(current_link_id, remaining - 1);
        let next_ptr = ptr + 1;
        next_route_ptrs[idx] = next_ptr as i32;
        next_current_link_ids[idx] = path[next_ptr];
        next_cooldown_ticks[idx] = (cooldown_ticks[idx] - 1).max(0);
        moved_slot_ids.push(slot_id);
    }

    Ok((
        next_current_link_ids,
        next_route_ptrs,
        next_cooldown_ticks,
        moved_slot_ids,
        sink_wait_slot_ids,
        released_slot_ids,
        completed_trip_ids,
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
    m.add_function(wrap_pyfunction!(compute_next_link_action_costs, m)?)?;
    m.add_function(wrap_pyfunction!(compute_greedy_route_candidate, m)?)?;
    m.add_function(wrap_pyfunction!(compute_ranked_route_candidates, m)?)?;
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
