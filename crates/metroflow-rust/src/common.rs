pub(crate) const EPS: f64 = 1e-6;
pub(crate) const FLOW_MIN_TRAVEL_COST: f32 = 1.0e-3;
pub(crate) const ROUTING_INF_COST: f32 = 1.0e12;

pub(crate) type FlowBatchResult = (
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

pub(crate) type AgentBatchResult = (
    Vec<i32>,
    Vec<i32>,
    Vec<i32>,
    Vec<i32>,
    Vec<i32>,
    Vec<i32>,
    Vec<i32>,
);

pub(crate) fn validate_same_lengths(lengths: &[(&str, usize)]) -> Result<usize, String> {
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

pub(crate) fn validate_non_negative(name: &str, values: &[f64]) -> Result<(), String> {
    for value in values {
        if *value < 0.0 {
            return Err(format!("{name} must be non-negative"));
        }
    }
    Ok(())
}

pub(crate) fn validate_non_negative_f32(name: &str, values: &[f32]) -> Result<(), String> {
    for value in values {
        if *value < 0.0 {
            return Err(format!("{name} must be non-negative"));
        }
    }
    Ok(())
}
