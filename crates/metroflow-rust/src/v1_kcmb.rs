//! Explicit opt-in KCMB six-moment corridor kernel.
//! This is NOT the authoritative V1 packet/route FIFO model.
//! A class has micro-measure moments (m0,m1,j0,j1,z0,z1) with u=v/U ∈ [0,1].
//! Fixed matrix exponential coefficients come from the Python model contract;
//! actual transport is conservative, limited by physical lane-metres and
//! outgoing veh/s capacity, and is computed from PRE-step sending/receiving.
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

const FIELDS: usize = 6;
type KernelResult = (Vec<f64>, Vec<f64>, Vec<f64>, Vec<f64>, Vec<f64>, Vec<f64>);

fn invalid(message: &str) -> PyErr {
    PyValueError::new_err(message.to_owned())
}

#[pyclass]
pub struct NativeKCMBCorridor {
    cells: usize,
    classes: usize,
    dx: f64,
    dt: f64,
    lane_metres: f64,
    cap: f64,
    wave_fraction: f64,
    vmax: Vec<f64>,
    footprint: Vec<f64>,
    transitions: Vec<Vec<f64>>,
    source_p: Vec<f64>,
    source_u: Vec<f64>,
}

impl NativeKCMBCorridor {
    fn validate_state(
        &self,
        state: &[f64],
        pending: &[f64],
        released: &[f64],
        completed: &[f64],
    ) -> PyResult<()> {
        let k = self.classes;
        let n = self.cells;
        if state.len() != n * k * FIELDS
            || pending.len() != k
            || released.len() != k
            || completed.len() != k
        {
            return Err(invalid("KCMB native state shape mismatch"));
        }
        let mut active = vec![0.0; k];
        for i in 0..n {
            let mut used = 0.0;
            for a in 0..k {
                let off = (i * k + a) * FIELDS;
                let m0 = state[off];
                let m1 = state[off + 1];
                let mass = m0 + m1;
                let tol = 1e-10 * mass.max(1.0);
                for (m, j, z) in [
                    (m0, state[off + 2], state[off + 4]),
                    (m1, state[off + 3], state[off + 5]),
                ] {
                    if !m.is_finite()
                        || !j.is_finite()
                        || !z.is_finite()
                        || m < -tol
                        || j < -tol
                        || z < -tol
                        || j > m + tol
                        || z > j + tol
                        || j * j > m * z + tol * mass.max(1.0)
                    {
                        return Err(invalid("KCMB nonrealizable velocity moments"));
                    }
                }
                used += mass * self.footprint[a];
                active[a] += mass;
            }
            if used > self.lane_metres * (1.0 + 1e-9) {
                return Err(invalid("KCMB lane storage overfill"));
            }
        }
        for a in 0..k {
            let row = [pending[a], released[a], completed[a]];
            if row.iter().any(|x| !x.is_finite() || *x < -1e-11) {
                return Err(invalid("KCMB nonfinite/negative inventory"));
            }
            let residual = released[a] - (active[a] + pending[a] + completed[a]);
            if residual.abs() > 1e-9 * released[a].max(1.0) {
                return Err(invalid("KCMB per-class conservation residual"));
            }
        }
        Ok(())
    }

    fn send_bound(&self, x: &[f64], index: usize, a: usize) -> f64 {
        let m = x[index] + x[index + 1];
        let j = x[index + 2] + x[index + 3];
        m.min((self.dt / self.dx) * self.vmax[a] * j).max(0.0)
    }
}

#[pymethods]
impl NativeKCMBCorridor {
    #[new]
    #[allow(clippy::too_many_arguments)]
    fn new(
        cells: usize,
        classes: usize,
        dx: f64,
        dt: f64,
        lane_metres: f64,
        capacity: f64,
        wave_speed: f64,
        vmax: Vec<f64>,
        footprint: Vec<f64>,
        transitions: Vec<Vec<f64>>,
        source_p: Vec<f64>,
        source_u: Vec<f64>,
    ) -> PyResult<Self> {
        if cells == 0
            || classes == 0
            || classes > 8
            || cells
                .checked_mul(classes)
                .and_then(|v| v.checked_mul(FIELDS))
                .is_none()
            || cells * classes * FIELDS + 3 * classes > 2_000_000
            || [dx, dt, lane_metres, capacity, wave_speed]
                .iter()
                .any(|v| !v.is_finite() || *v <= 0.0)
            || vmax.len() != classes
            || footprint.len() != classes
            || transitions.len() != classes
            || source_p.len() != classes
            || source_u.len() != classes
        {
            return Err(invalid("invalid KCMB native geometry/shape"));
        }
        if vmax.iter().any(|v| !v.is_finite() || *v <= 0.0)
            || footprint.iter().any(|v| !v.is_finite() || *v <= 0.0)
            || source_p
                .iter()
                .chain(source_u.iter())
                .any(|v| !v.is_finite() || !(0.0..=1.0).contains(v))
            || transitions.iter().any(|matrix| {
                matrix.len() != FIELDS * FIELDS || matrix.iter().any(|v| !v.is_finite() || *v < 0.0)
            })
            || dt * vmax.iter().copied().fold(wave_speed, f64::max) > dx
        {
            return Err(invalid("invalid KCMB native physical parameters or CFL"));
        }
        let wave_fraction = (wave_speed * dt / dx).min(1.0);
        Ok(Self {
            cells,
            classes,
            dx,
            dt,
            lane_metres,
            cap: capacity * dt,
            wave_fraction,
            vmax,
            footprint,
            transitions,
            source_p,
            source_u,
        })
    }

    fn state_scalar_capacity(&self) -> usize {
        self.cells * self.classes * FIELDS + 3 * self.classes
    }

    fn step(
        &self,
        moments: Vec<f64>,
        pending: Vec<f64>,
        released: Vec<f64>,
        completed: Vec<f64>,
        offered: Vec<f64>,
        green: f64,
    ) -> PyResult<KernelResult> {
        self.validate_state(&moments, &pending, &released, &completed)?;
        let n = self.cells;
        let k = self.classes;
        if offered.len() != k
            || offered.iter().any(|v| !v.is_finite() || *v < 0.0)
            || !green.is_finite()
            || !(0.0..=1.0).contains(&green)
        {
            return Err(invalid("invalid KCMB boundary demand/gate"));
        }
        let mut kinetic = vec![0.0; moments.len()];
        let mut masses = vec![0.0; n * k];
        let mut sends = vec![0.0; n * k];
        let mut free = vec![0.0; n];

        // Frozen kinetic generator: moments remain class/driver conditioned.
        for i in 0..n {
            let mut occupied = 0.0;
            for a in 0..k {
                let offset = (i * k + a) * FIELDS;
                let matrix = &self.transitions[a];
                for r in 0..FIELDS {
                    let mut value = 0.0;
                    for j in 0..FIELDS {
                        value += matrix[r * FIELDS + j] * moments[offset + j];
                    }
                    kinetic[offset + r] = value;
                }
                let m = kinetic[offset] + kinetic[offset + 1];
                masses[i * k + a] = m;
                occupied += m * self.footprint[a];
                sends[i * k + a] = self.send_bound(&kinetic, offset, a);
            }
            let mut sum = 0.0;
            for a in 0..k {
                sum += sends[i * k + a];
            }
            if sum > self.cap {
                let scale = self.cap / sum;
                for a in 0..k {
                    sends[i * k + a] *= scale;
                }
            }
            free[i] = (self.lane_metres - occupied).max(0.0) * self.wave_fraction;
        }

        let mut moved = vec![0.0; n * k];
        for i in 0..(n - 1) {
            let mut quantity = 0.0;
            let mut metres = 0.0;
            for a in 0..k {
                let v = sends[i * k + a];
                quantity += v;
                metres += v * self.footprint[a];
            }
            let fraction = 1.0_f64
                .min(if quantity > 0.0 {
                    self.cap / quantity
                } else {
                    1.0
                })
                .min(if metres > 0.0 {
                    free[i + 1] / metres
                } else {
                    1.0
                });
            for a in 0..k {
                moved[i * k + a] = sends[i * k + a] * fraction;
            }
        }
        let mut out = vec![0.0; k];
        for a in 0..k {
            out[a] = sends[(n - 1) * k + a] * green;
            moved[(n - 1) * k + a] = out[a];
        }

        // Boundary source: independent pending stock, no mass deletion.
        let mut arrivals = vec![0.0; k];
        let mut quantity = 0.0;
        let mut metres = 0.0;
        for a in 0..k {
            arrivals[a] = pending[a] + offered[a];
            quantity += arrivals[a];
            metres += arrivals[a] * self.footprint[a];
        }
        let input_fraction = 1.0_f64
            .min(if quantity > 0.0 {
                self.cap / quantity
            } else {
                1.0
            })
            .min(if metres > 0.0 { free[0] / metres } else { 1.0 });
        let mut accepted = vec![0.0; k];
        for a in 0..k {
            accepted[a] = arrivals[a] * input_fraction;
        }

        let mut next = vec![0.0; kinetic.len()];
        for i in 0..n {
            for a in 0..k {
                let index = i * k + a;
                let offset = index * FIELDS;
                let m = masses[index];
                let stay = if m > 0.0 { 1.0 - moved[index] / m } else { 1.0 };
                for r in 0..FIELDS {
                    next[offset + r] = kinetic[offset + r] * stay;
                }
                if i > 0 {
                    let upstream = (i - 1) * k + a;
                    let frac = if masses[upstream] > 0.0 {
                        moved[upstream] / masses[upstream]
                    } else {
                        0.0
                    };
                    for r in 0..FIELDS {
                        next[offset + r] += kinetic[upstream * FIELDS + r] * frac;
                    }
                } else {
                    let value = accepted[a];
                    let p = self.source_p[a];
                    let u = self.source_u[a];
                    next[offset] += value * (1.0 - p);
                    next[offset + 1] += value * p;
                    next[offset + 2] += value * (1.0 - p) * u;
                    next[offset + 3] += value * p * u;
                    next[offset + 4] += value * (1.0 - p) * u * u;
                    next[offset + 5] += value * p * u * u;
                }
            }
        }

        let mut new_pending = vec![0.0; k];
        let mut new_released = vec![0.0; k];
        let mut new_completed = vec![0.0; k];
        for a in 0..k {
            new_pending[a] = (arrivals[a] - accepted[a]).max(0.0);
            new_released[a] = released[a] + offered[a];
            new_completed[a] = completed[a] + out[a];
        }
        self.validate_state(&next, &new_pending, &new_released, &new_completed)?;
        Ok((
            next,
            new_pending,
            new_released,
            new_completed,
            accepted,
            out,
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn shape_and_storage_guards_and_zero_step() {
        let identity = (0..FIELDS * FIELDS)
            .map(|i| if i / FIELDS == i % FIELDS { 1. } else { 0. })
            .collect::<Vec<_>>();
        let core = NativeKCMBCorridor::new(
            2,
            1,
            10.,
            0.5,
            10.,
            0.5,
            5.,
            vec![10.],
            vec![5.],
            vec![identity],
            vec![1.],
            vec![0.],
        )
        .unwrap();
        let s = vec![0.; 2 * FIELDS];
        let (ns, pending, released, completed, accepted, outgoing) = core
            .step(s, vec![0.], vec![0.], vec![0.], vec![0.], 1.)
            .unwrap();
        assert_eq!(core.state_scalar_capacity(), 2 * FIELDS + 3);
        assert_eq!(ns, vec![0.; 2 * FIELDS]);
        assert_eq!(pending, vec![0.]);
        assert_eq!(released, vec![0.]);
        assert_eq!(completed, vec![0.]);
        assert_eq!(accepted, vec![0.]);
        assert_eq!(outgoing, vec![0.]);
    }
}
