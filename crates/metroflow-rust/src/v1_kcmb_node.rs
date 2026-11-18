//! Research-only opt-in KCMB finite-volume node allocator.
//! Each sending group shares one turn-mixture scale theta, or has one movement
//! per group (separate turning pockets). Every destination's count and physical
//! lane-metres budget is satisfied simultaneously. This is NOT a proof of the
//! network FIFO invariant-junction/entropy property or maximum throughput.
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

type NodeMovement = (usize, isize, f64, f64);

fn invalid(msg: &'static str) -> PyErr {
    PyValueError::new_err(msg)
}

#[pyfunction]
pub(crate) fn allocate_kcmb_nodes(
    groups: Vec<Vec<NodeMovement>>,
    receive_count: Vec<f64>,
    receive_metres: Vec<f64>,
    weights: Vec<f64>,
    theta_limits: Vec<f64>,
) -> PyResult<Vec<(usize, usize, f64)>> {
    let g_len = groups.len();
    let r_len = receive_count.len();
    if weights.len() != g_len
        || theta_limits.len() != g_len
        || r_len != receive_metres.len()
        || g_len > 100_000
        || r_len > 100_000
        || g_len.checked_mul(r_len).is_none_or(|v| v > 2_000_000)
    {
        return Err(invalid("KCMB allocator dimension/budget mismatch"));
    }
    if receive_count
        .iter()
        .chain(receive_metres.iter())
        .any(|v| !v.is_finite() || *v < 0.)
    {
        return Err(invalid("KCMB invalid receiving capacity"));
    }
    let mut qcoeff = vec![vec![0.0; r_len]; g_len];
    let mut mcoeff = vec![vec![0.0; r_len]; g_len];
    for (g, rows) in groups.iter().enumerate() {
        if !weights[g].is_finite()
            || weights[g] <= 0.
            || !theta_limits[g].is_finite()
            || !(0.0..=1.0).contains(&theta_limits[g])
        {
            return Err(invalid("KCMB invalid group priority/limit"));
        }
        if rows.len() > 100_000 {
            return Err(invalid("KCMB oversized movement group"));
        }
        for &(_, dest, amount, footprint) in rows {
            if !amount.is_finite()
                || amount < 0.
                || !footprint.is_finite()
                || footprint <= 0.
                || dest < -1
                || (dest >= 0 && dest as usize >= r_len)
            {
                return Err(invalid("KCMB invalid movement/destination"));
            }
            if dest >= 0 {
                let j = dest as usize;
                qcoeff[g][j] += amount;
                mcoeff[g][j] += amount * footprint;
            }
        }
    }

    let mut theta = vec![0.0; g_len];
    let mut used_q = vec![0.0; r_len];
    let mut used_m = vec![0.0; r_len];
    for _ in 0..(g_len + 2 * r_len + 2) {
        let active = (0..g_len)
            .filter(|&g| {
                if theta[g] >= theta_limits[g] - 1e-13 || !groups[g].iter().any(|x| x.2 > 0.) {
                    return false;
                }
                for j in 0..r_len {
                    if (qcoeff[g][j] > 0. && used_q[j] >= receive_count[j] - 1e-12)
                        || (mcoeff[g][j] > 0. && used_m[j] >= receive_metres[j] - 1e-12)
                    {
                        return false;
                    }
                }
                true
            })
            .collect::<Vec<_>>();
        if active.is_empty() {
            break;
        }
        let mut step = f64::INFINITY;
        for &g in &active {
            step = step.min((theta_limits[g] - theta[g]) / weights[g]);
        }
        for j in 0..r_len {
            let qrate: f64 = active.iter().map(|&g| weights[g] * qcoeff[g][j]).sum();
            if qrate > 0. {
                step = step.min((receive_count[j] - used_q[j]).max(0.) / qrate);
            }
            let mrate: f64 = active.iter().map(|&g| weights[g] * mcoeff[g][j]).sum();
            if mrate > 0. {
                step = step.min((receive_metres[j] - used_m[j]).max(0.) / mrate);
            }
        }
        if step <= 1e-14 {
            break;
        }
        if !step.is_finite() {
            return Err(invalid("KCMB invalid progressive filling step"));
        }
        for &g in &active {
            theta[g] = theta_limits[g].min(theta[g] + step * weights[g]);
        }
        for j in 0..r_len {
            used_q[j] = (0..g_len).map(|g| theta[g] * qcoeff[g][j]).sum();
            used_m[j] = (0..g_len).map(|g| theta[g] * mcoeff[g][j]).sum();
            if used_q[j] > receive_count[j] + 1e-8 || used_m[j] > receive_metres[j] + 1e-8 {
                return Err(invalid("KCMB node exceeded physical receiving budget"));
            }
        }
    }
    let mut output = Vec::new();
    for (g, group) in groups.iter().enumerate() {
        for (i, value) in group.iter().enumerate() {
            output.push((g, i, theta[g] * value.2));
        }
    }
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn weighted_merge_and_lane_metres_conserve_resources() {
        let raw = vec![vec![(0, 0, 1., 5.)], vec![(1, 0, 1., 5.)]];
        let rows =
            allocate_kcmb_nodes(raw, vec![1.], vec![100.], vec![2., 1.], vec![1., 1.]).unwrap();
        assert!((rows[0].2 - 2. / 3.).abs() < 1e-12);
        assert!((rows[1].2 - 1. / 3.).abs() < 1e-12);
        let raw = vec![vec![(0, 0, 1., 5.)], vec![(1, 0, 1., 15.)]];
        let rows =
            allocate_kcmb_nodes(raw, vec![100.], vec![10.], vec![1., 1.], vec![1., 1.]).unwrap();
        assert!((rows[0].2 - 0.5).abs() < 1e-12);
        assert!((rows[1].2 - 0.5).abs() < 1e-12);
    }

    #[test]
    fn shared_red_movement_blocks_entire_group() {
        let raw = vec![vec![(0, 0, 1., 5.), (1, 1, 1., 5.)]];
        let rows =
            allocate_kcmb_nodes(raw, vec![3., 0.], vec![40., 40.], vec![1.], vec![1.]).unwrap();
        assert_eq!(rows[0].2, 0.);
        assert_eq!(rows[1].2, 0.);
    }
}
