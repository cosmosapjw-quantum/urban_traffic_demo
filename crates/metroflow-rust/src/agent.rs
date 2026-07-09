use std::collections::{HashMap, HashSet};

use crate::common::AgentBatchResult;

#[allow(clippy::too_many_arguments)]
pub(crate) fn advance_active_agents_batch_impl(
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
