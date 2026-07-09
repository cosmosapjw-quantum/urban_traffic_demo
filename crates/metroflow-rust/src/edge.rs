use crate::common::{validate_non_negative, validate_same_lengths, EPS};

pub(crate) fn evolve_edges_batch_impl(
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
