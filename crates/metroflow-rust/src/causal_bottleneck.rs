//! A separate finite-storage, delayed FIFO cumulative-count closure.
//! It is not the V03 kinetic solver and earns no original acceptance credit.
use crate::core_error::{CoreError, CoreResult};
use serde::{Deserialize, Serialize};
fn bad(s: &str) -> CoreError {
    CoreError::value(s)
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
pub struct Supply {
    pub storage_veh: f64,
    pub receiving_veh: f64,
    pub sending_veh: f64,
}
#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize)]
pub struct Counts {
    pub requested: f64,
    pub admitted: f64,
    pub departed: f64,
    pub pending: f64,
    pub on_link: f64,
    pub residence_veh_s: f64,
}
pub struct LinkQueue {
    dt: f64,
    lag: usize,
    history: Vec<f64>,
    tick: usize,
    state: Counts,
}
impl LinkQueue {
    pub fn new(dt: f64, lag: usize) -> CoreResult<Self> {
        if !dt.is_finite() || dt <= 0. || lag == 0 || lag > 1_000_000 {
            return Err(bad("invalid causal link step/lag"));
        }
        Ok(Self {
            dt,
            lag,
            history: vec![0.; lag],
            tick: 0,
            state: Counts::default(),
        })
    }
    pub fn counts(&self) -> Counts {
        self.state
    }
    /// Previous-clock receiving capacity: same-tick departures cannot
    /// instantaneously free upstream space. Delay >= one complete tick.
    /// One preallocated ring lookup and update; no per-event allocation.
    pub fn step(&mut self, requested: f64, s: Supply) -> CoreResult<Counts> {
        let c = self.state;
        if [requested, s.storage_veh, s.receiving_veh, s.sending_veh]
            .iter()
            .any(|x| !x.is_finite() || *x < 0.)
            || requested < c.requested
            || s.storage_veh < c.on_link
        {
            return Err(bad("invalid supply, request or storage contraction"));
        }
        let ready = self.history[self.tick % self.lag];
        let d = ready.min(c.departed + s.sending_veh);
        let a = requested
            .min(c.admitted + s.receiving_veh)
            .min(c.departed + s.storage_veh);
        if d < c.departed
            || a < c.admitted
            || d > a
            || a - d > s.storage_veh + 1e-10 * s.storage_veh.max(1.)
        {
            return Err(bad("causal link conservation"));
        }
        let residence = c.residence_veh_s + self.dt * (c.requested - c.departed);
        if !residence.is_finite() {
            return Err(bad("residence overflow"));
        }
        let next = Counts {
            requested,
            admitted: a,
            departed: d,
            pending: requested - a,
            on_link: a - d,
            residence_veh_s: residence,
        };
        let next_tick = self
            .tick
            .checked_add(1)
            .ok_or_else(|| bad("link tick overflow"))?;
        self.history[self.tick % self.lag] = a;
        self.tick = next_tick;
        self.state = next;
        Ok(next)
    }
}

#[derive(Clone, Debug, Serialize)]
struct Sample {
    time_s: f64,
    baseline: Counts,
    relief: Counts,
}
/// Original calendar intentions projected to a SINGLE representative link
/// incident on the busiest outward-car origin. No assignment or calibration.
/// The counterfactual doubles link capacity/storage, not an actual bypass.
pub fn project_manifest(
    m: serde_json::Value,
    dt: f64,
    scale: f64,
) -> CoreResult<serde_json::Value> {
    use serde_json::json;
    let budget = m["byte_budget"]
        .as_u64()
        .ok_or_else(|| bad("manifest budget"))? as usize;
    if budget > 6 * 1024usize.pow(3)
        || budget == 0
        || !scale.is_finite()
        || scale <= 0.
        || scale > 1.
        || !dt.is_finite()
        || dt <= 0.
        || 86400. / dt > 100000.
        || (86400. / dt).fract() != 0.
    {
        return Err(bad("projection domain"));
    }
    let cal: crate::v1_calendar::FactorizedDeclaration =
        serde_json::from_value(m["calendar"].clone()).map_err(|_| bad("calendar declaration"))?;
    let cal = cal.compile(budget)?;
    let labels = cal.owned_labels();
    let profiles = cal.owned_profiles();
    let mut by_origin = std::collections::BTreeMap::<u32, f64>::new();
    for l in cal.owned_legs() {
        if l.parent.is_none()
            && labels[l.metadata[3] as usize] == "\"car\""
            && labels[l.metadata[7] as usize] == "\"interzonal\""
        {
            *by_origin.entry(l.metadata[0]).or_default() += l.amounts[1];
        }
    }
    let (&origin, &total) = by_origin
        .iter()
        .max_by(|a, b| a.1.total_cmp(b.1).then_with(|| b.0.cmp(a.0)))
        .ok_or_else(|| bad("no outward car origin"))?;
    let mut amounts = vec![0.; profiles.len()];
    for l in cal.owned_legs() {
        if l.parent.is_none()
            && l.metadata[0] == origin
            && labels[l.metadata[3] as usize] == "\"car\""
            && labels[l.metadata[7] as usize] == "\"interzonal\""
        {
            amounts[l.metadata[5] as usize] += l.amounts[1];
        }
    }
    let s = &m["static"];
    let act = s["activities"]
        .as_array()
        .and_then(|v| {
            v.iter()
                .find(|r| r[0].as_str() == Some(labels[origin as usize].as_str()))
        })
        .ok_or_else(|| bad("origin activity"))?;
    let node = act[2].as_str().ok_or_else(|| bad("origin node"))?;
    let arc = s["route_arcs"]
        .as_array()
        .and_then(|v| {
            v.iter()
                .filter(|a| a[1].as_str() == Some(node))
                .min_by(|a, b| a[0].as_str().cmp(&b[0].as_str()))
        })
        .ok_or_else(|| bad("no outward link"))?;
    let link = arc[0].as_str().ok_or_else(|| bad("link"))?;
    let idx = s["link_ids"]
        .as_array()
        .and_then(|v| v.iter().position(|v| v.as_str() == Some(link)))
        .ok_or_else(|| bad("link registry"))?;
    let g: Vec<f64> =
        serde_json::from_value(s["groups"][idx].clone()).map_err(|_| bad("link coefficients"))?;
    let k = s["class_names"]
        .as_array()
        .and_then(|v| v.iter().position(|v| v.as_str() == Some("car")))
        .ok_or_else(|| bad("car class"))?;
    let cls: Vec<f64> =
        serde_json::from_value(s["classes"][k].clone()).map_err(|_| bad("class coefficients"))?;
    if g.len() != 6
        || cls.len() != 13
        || g.iter().any(|v| !v.is_finite() || *v <= 0.)
        || cls[12] <= 0.
        || cls[0] <= 0.
    {
        return Err(bad("invalid link domain"));
    }
    let lag = (g[0] / g[1].min(cls[0]) / dt).ceil().max(1.) as usize;
    let storage = g[4] / cls[12];
    let mut base = LinkQueue::new(dt, lag)?;
    let mut relief = LinkQueue::new(dt, lag)?;
    let steps = (86400. / dt) as usize;
    let mut samples = vec![];
    let mut max_pending: f64 = 0.;
    let mut max_relief_pending: f64 = 0.;
    let t = std::time::Instant::now();
    for i in 1..=steps {
        let now = i as f64 * dt;
        let mid = now - dt / 2.;
        let u = crate::v1_journey::fsum(profiles.iter().zip(&amounts).map(|(p, &m)| {
            m * crate::v1_journey::fsum(
                p.iter()
                    .map(|&(a, b, w)| w * (now.min(b) - a).max(0.) / (b - a)),
            )
        }));
        // Existing frozen closures and traffic signals sampled at midpoint;
        // this is the projected discrete model, not the native finite-response law.
        let factor = s["windows"]
            .as_array()
            .ok_or_else(|| bad("closure registry"))?
            .iter()
            .filter(|w| {
                w[0].as_u64() == Some(idx as u64)
                    && w[1].as_f64().is_some_and(|a| a <= mid)
                    && w[2].as_f64().is_some_and(|b| mid < b)
            })
            .try_fold(1., |x, w| {
                Ok::<_, CoreError>(x * w[3].as_f64().ok_or_else(|| bad("closure factor"))?)
            })?;
        let green = if s["signals"][idx].is_null() {
            1.
        } else {
            let v: Vec<f64> =
                serde_json::from_value(s["signals"][idx].clone()).map_err(|_| bad("signal"))?;
            if v.len() != 3 || v[0] <= 0. {
                return Err(bad("signal"));
            }
            if (mid - v[2]).rem_euclid(v[0]) < v[1] {
                1.
            } else {
                0.
            }
        };
        let a = base.step(
            u.max(base.counts().requested),
            Supply {
                storage_veh: storage,
                receiving_veh: g[2] * factor * scale * dt,
                sending_veh: g[3] * factor * green * scale * dt,
            },
        )?;
        let b = relief.step(
            u.max(relief.counts().requested),
            Supply {
                storage_veh: 2. * storage,
                receiving_veh: 2. * g[2] * factor * scale * dt,
                sending_veh: 2. * g[3] * factor * green * scale * dt,
            },
        )?;
        if a.departed > b.departed + 1e-9
            || a.admitted > b.admitted + 1e-9
            || b.residence_veh_s > a.residence_veh_s + 1e-8
        {
            return Err(bad("capacity comparison violated"));
        }
        max_pending = max_pending.max(a.pending);
        max_relief_pending = max_relief_pending.max(b.pending);
        if i % (3600. / dt).round().max(1.) as usize == 0 || i == steps {
            samples.push(Sample {
                time_s: now,
                baseline: a,
                relief: b,
            })
        }
    }
    Ok(
        json!({"schema":"metroflow_causal_link_projection_v1","scope":"fixed outward car intent of busiest origin projected to one representative frozen link; doubled supply/storage intervention; not network assignment, endogenous demand, or V03 acceptance","origin":labels[origin as usize],"link":link,"intended_outward_car_veh":total,"calendar_legs":cal.owned_legs().len(),"dt_s":dt,"capacity_scale":scale,"lag_steps":lag,"storage_veh":storage,"steps":steps,"ring_payload_bytes":2*lag*std::mem::size_of::<f64>(),"simulation_wall_s":t.elapsed().as_secs_f64(),"baseline":base.counts(),"relief":relief.counts(),"max_pending_veh":max_pending,"max_relief_pending_veh":max_relief_pending,"samples":samples}),
    )
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exact_delay_and_old_clock_spillback() {
        let mut q = LinkQueue::new(1., 2).unwrap();
        let s = Supply {
            storage_veh: 2.,
            receiving_veh: 10.,
            sending_veh: 10.,
        };
        let a = q.step(6., s).unwrap();
        assert_eq!((a.admitted, a.departed), (2., 0.));
        let b = q.step(6., s).unwrap();
        assert_eq!((b.admitted, b.departed), (2., 0.));
        let c = q.step(6., s).unwrap();
        assert_eq!((c.admitted, c.departed), (2., 2.));
        let d = q.step(6., s).unwrap();
        assert_eq!((d.admitted, d.departed), (4., 2.));
    }
    #[test]
    fn finite_capacity_monotonic_for_exhaustive_short_signal_sequences() {
        for mask in 0..256usize {
            let mut a = LinkQueue::new(1., 3).unwrap();
            let mut b = LinkQueue::new(1., 3).unwrap();
            for i in 0..8 {
                let green = ((mask >> i) & 1) as f64;
                let x = a
                    .step(
                        (i + 1) as f64 * 2.,
                        Supply {
                            storage_veh: 3.,
                            receiving_veh: 2.,
                            sending_veh: green,
                        },
                    )
                    .unwrap();
                let y = b
                    .step(
                        (i + 1) as f64 * 2.,
                        Supply {
                            storage_veh: 5.,
                            receiving_veh: 3.,
                            sending_veh: 2. * green,
                        },
                    )
                    .unwrap();
                assert!(
                    y.admitted >= x.admitted
                        && y.departed >= x.departed
                        && y.residence_veh_s <= x.residence_veh_s
                );
                assert_eq!(x.requested, x.pending + x.on_link + x.departed);
                assert_eq!(y.requested, y.pending + y.on_link + y.departed);
            }
        }
    }
}
