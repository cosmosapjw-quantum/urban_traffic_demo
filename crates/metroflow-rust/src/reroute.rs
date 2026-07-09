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

pub(crate) fn compute_reroute_decision_batch_impl(
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
