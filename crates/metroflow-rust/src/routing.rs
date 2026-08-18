use std::cmp::Ordering;
use std::collections::{BinaryHeap, HashMap, HashSet};
use rayon::prelude::*;

use crate::common::{validate_non_negative_f32, ROUTING_INF_COST};

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

#[derive(Clone, Debug, PartialEq)]
struct TurnSuccessorLookup {
    has_turns: bool,
    has_successors: Vec<bool>,
    allowed_successors: Vec<Vec<usize>>,
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

pub(crate) fn compute_dynamic_potential_node_costs_impl(
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

pub(crate) fn compute_next_link_action_costs_impl(
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
    turn_lookup: &TurnSuccessorLookup,
    node_cost_to_go: &[f32],
    link_travel_time_cost: &[f32],
    blocked_link_mask: &[bool],
) -> Option<usize> {
    let allowed_successors = allowed_successors_for_incoming(turn_lookup, incoming_link_index)?;

    let start = outgoing_indptr[current_node_index] as usize;
    let end = outgoing_indptr[current_node_index + 1] as usize;
    let mut best_link_index: Option<usize> = None;
    let mut best_cost = ROUTING_INF_COST;
    for pos in start..end {
        let link_index = outgoing_link_indices[pos] as usize;
        if let Some(allowed) = allowed_successors {
            if allowed.binary_search(&link_index).is_err() {
                continue;
            }
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

fn build_turn_successor_lookup(
    link_count: usize,
    turn_from_link_index: &[i32],
    turn_to_link_index: &[i32],
    turn_is_forbidden: &[bool],
) -> TurnSuccessorLookup {
    let mut has_successors = vec![false; link_count];
    let mut allowed_successors = vec![Vec::new(); link_count];
    for turn_index in 0..turn_from_link_index.len() {
        let from_link_index = turn_from_link_index[turn_index] as usize;
        has_successors[from_link_index] = true;
        if !turn_is_forbidden[turn_index] {
            allowed_successors[from_link_index].push(turn_to_link_index[turn_index] as usize);
        }
    }
    for successors in allowed_successors.iter_mut() {
        successors.sort_unstable();
        successors.dedup();
    }
    TurnSuccessorLookup {
        has_turns: !turn_from_link_index.is_empty(),
        has_successors,
        allowed_successors,
    }
}

fn allowed_successors_for_incoming(
    turn_lookup: &TurnSuccessorLookup,
    incoming_link_index: i32,
) -> Option<Option<&[usize]>> {
    if incoming_link_index < 0 || !turn_lookup.has_turns {
        return Some(None);
    }
    let incoming = incoming_link_index as usize;
    if !turn_lookup.has_successors[incoming] {
        return None;
    }
    let allowed = turn_lookup.allowed_successors[incoming].as_slice();
    if allowed.is_empty() {
        return None;
    }
    Some(Some(allowed))
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn compute_greedy_route_candidate_impl(
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
    let turn_lookup = build_turn_successor_lookup(
        link_ids.len(),
        turn_from_link_index,
        turn_to_link_index,
        turn_is_forbidden,
    );

    for _ in 0..max_hops {
        let Some(next_link_index) = best_legal_next_link_index(
            current_node_index,
            current_incoming_link_index,
            link_ids,
            link_dst_node_index,
            outgoing_indptr,
            outgoing_link_indices,
            &turn_lookup,
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
    turn_lookup: &TurnSuccessorLookup,
    node_cost_to_go: &[f32],
    link_travel_time_cost: &[f32],
    blocked_link_mask: &[bool],
) -> Vec<(f32, i32, usize)> {
    let Some(allowed_successors) =
        allowed_successors_for_incoming(turn_lookup, incoming_link_index)
    else {
        return Vec::new();
    };

    let start = outgoing_indptr[current_node_index] as usize;
    let end = outgoing_indptr[current_node_index + 1] as usize;
    let mut scored = Vec::new();
    for pos in start..end {
        let link_index = outgoing_link_indices[pos] as usize;
        if let Some(allowed) = allowed_successors {
            if allowed.binary_search(&link_index).is_err() {
                continue;
            }
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
pub(crate) fn compute_ranked_route_candidates_impl(
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
    let turn_lookup = build_turn_successor_lookup(
        link_ids.len(),
        turn_from_link_index,
        turn_to_link_index,
        turn_is_forbidden,
    );
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
            &turn_lookup,
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

pub(crate) fn compute_route_candidate_metadata_impl(
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

pub(crate) fn select_route_candidate_index_impl(
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

pub(crate) fn compute_multi_destination_dynamic_potentials_impl(
    node_count: usize,
    incoming_indptr: &[i32],
    incoming_link_indices: &[i32],
    link_src_node_index: &[i32],
    link_travel_time_cost: &[f32],
    blocked_link_mask: &[bool],
    destination_node_indices: &[usize],
) -> Result<Vec<Vec<f32>>, String> {
    for &dst in destination_node_indices {
        validate_routing_inputs(
            node_count,
            incoming_indptr,
            incoming_link_indices,
            link_src_node_index,
            link_travel_time_cost,
            blocked_link_mask,
            dst,
        )?;
    }

    let results: Vec<Vec<f32>> = destination_node_indices
        .par_iter()
        .map(|&destination_node_index| {
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
            dist
        })
        .collect();

    Ok(results)
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn compute_ranked_route_candidates_batch_impl(
    node_count: usize,
    link_ids: &[i32],
    link_dst_node_index: &[i32],
    outgoing_indptr: &[i32],
    outgoing_link_indices: &[i32],
    turn_from_link_index: &[i32],
    turn_to_link_index: &[i32],
    turn_is_forbidden: &[bool],
    node_costs_to_go: &[Vec<f32>],
    link_travel_time_cost: &[f32],
    blocked_link_mask: &[bool],
    origins: &[usize],
    destinations: &[usize],
    incomings: &[i32],
    max_hops: usize,
    max_candidates: usize,
) -> Result<Vec<Vec<Vec<i32>>>, String> {
    let pair_count = origins.len();
    if destinations.len() != pair_count
        || incomings.len() != pair_count
        || node_costs_to_go.len() != pair_count
    {
        return Err(
            "origins, destinations, incomings, and node_costs_to_go must have equal lengths"
                .to_string(),
        );
    }

    (0..pair_count)
        .into_par_iter()
        .map(|idx| {
            compute_ranked_route_candidates_impl(
                node_count,
                link_ids,
                link_dst_node_index,
                outgoing_indptr,
                outgoing_link_indices,
                turn_from_link_index,
                turn_to_link_index,
                turn_is_forbidden,
                &node_costs_to_go[idx],
                link_travel_time_cost,
                blocked_link_mask,
                origins[idx],
                destinations[idx],
                incomings[idx],
                max_hops,
                max_candidates,
            )
        })
        .collect()
}


