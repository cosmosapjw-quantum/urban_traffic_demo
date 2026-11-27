//! Marked two-route FIFO diverge. Research shadow, not the kinetic V03 engine.
//! All queues are preallocated. One shared mixed head is served proportionally;
//! downstream storage is evaluated from the old clock, not same-step outflow.
use crate::core_error::{CoreError, CoreResult};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, VecDeque};
fn bad(s: &str) -> CoreError {
    CoreError::value(s)
}
#[derive(Clone, Copy, Default, Debug, Serialize, Deserialize)]
pub struct Mark {
    pub mass: [f64; 2],
    pub birth: [f64; 2],
}
impl Mark {
    fn total(self) -> f64 {
        self.mass[0] + self.mass[1]
    }
    fn space(self, w: [f64; 2]) -> f64 {
        self.mass[0] * w[0] + self.mass[1] * w[1]
    }
    fn add(&mut self, b: Self) {
        for i in 0..2 {
            self.mass[i] += b.mass[i];
            self.birth[i] += b.birth[i];
        }
    }
    fn sub(&mut self, b: Self) {
        for i in 0..2 {
            self.mass[i] -= b.mass[i];
            self.birth[i] -= b.birth[i];
        }
    }
    fn scaled(self, a: f64) -> Self {
        Self {
            mass: self.mass.map(|v| v * a),
            birth: self.birth.map(|v| v * a),
        }
    }
    fn valid(self) -> bool {
        self.mass
            .iter()
            .chain(self.birth.iter())
            .all(|x| x.is_finite() && *x >= 0.)
    }
    fn only(self, k: usize) -> Self {
        let mut s = Self::default();
        s.mass[k] = self.mass[k];
        s.birth[k] = self.birth[k];
        s
    }
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
pub struct Link {
    pub storage_m: f64,
    pub lag: usize,
    pub send_veh: f64,
    pub receive_veh: f64,
}
#[derive(Clone, Copy)]
struct Batch {
    mark: Mark,
    entry: usize,
}
struct Queue {
    rows: VecDeque<Batch>,
    stock: Mark,
    limit: usize,
    peak: usize,
}
impl Queue {
    fn new(limit: usize) -> CoreResult<Self> {
        let mut rows = VecDeque::new();
        rows.try_reserve_exact(limit)
            .map_err(|_| CoreError::resource("marked queue allocation"))?;
        Ok(Self {
            rows,
            stock: Mark::default(),
            limit,
            peak: 0,
        })
    }
    fn push(&mut self, mark: Mark, entry: usize) -> CoreResult<()> {
        if mark.total() == 0. {
            return Ok(());
        }
        if !mark.valid() {
            return Err(bad("invalid marked batch"));
        }
        if self.rows.len() == self.limit {
            return Err(CoreError::resource("marked FIFO fragment bound"));
        }
        self.rows.push_back(Batch { mark, entry });
        self.stock.add(mark);
        self.peak = self.peak.max(self.rows.len());
        Ok(())
    }
    fn take(&mut self, a: f64) -> Mark {
        let h = self.rows.front_mut().expect("nonempty FIFO");
        let out = if a == 1. {
            self.rows.pop_front().unwrap().mark
        } else {
            let m = h.mark.scaled(a);
            h.mark.sub(m);
            m
        };
        self.stock.sub(out);
        // Roundoff in accumulated stock is removed only for an empty queue.
        if self.rows.is_empty() {
            self.stock = Mark::default();
        }
        out
    }
    fn recompute(&self) -> Mark {
        let mut m = Mark::default();
        for x in &self.rows {
            m.add(x.mark)
        }
        m
    }
}
fn ratio(cap: f64, demand: f64) -> f64 {
    if demand > 0. {
        cap.max(0.) / demand
    } else {
        f64::INFINITY
    }
}
/// Unique maximal common head fraction satisfying the simultaneous constraints.
fn head_fraction(m: Mark, w: [f64; 2], send: f64, receiving: [f64; 2], space: [f64; 2]) -> f64 {
    let mut a = 1f64.min(ratio(send, m.total()));
    for r in 0..2 {
        a = a
            .min(ratio(receiving[r], m.mass[r]))
            .min(ratio(space[r], w[r] * m.mass[r]));
    }
    a.max(0.)
}
#[derive(Debug, Clone, Serialize)]
pub struct Metrics {
    pub time_s: f64,
    pub requested: Mark,
    pub exited: Mark,
    pub pending: Mark,
    pub on_link: Mark,
    pub residence_veh_s: [f64; 2],
    pub completed_elapsed_veh_s: [f64; 2],
    pub max_mass_residual: f64,
    pub max_birth_residual: f64,
    pub age_identity_residual: [f64; 2],
    pub peak_pending_veh: f64,
    pub blocked_mixed_ticks: usize,
    pub peak_queue_rows: [usize; 4],
    pub reserved_queue_payload_bytes: usize,
}
pub struct Diverge {
    dt: f64,
    horizon: usize,
    tick: usize,
    links: [Link; 3],
    w: [f64; 2],
    pending: Queue,
    trunk: Queue,
    branch: [Queue; 2],
    req: Mark,
    exit: Mark,
    age: [f64; 2],
    elapsed: [f64; 2],
    max_mass: f64,
    max_birth: f64,
    peak_pending: f64,
    blocked: usize,
}
impl Diverge {
    pub fn new(dt: f64, horizon: usize, links: [Link; 3], w: [f64; 2]) -> CoreResult<Self> {
        if !dt.is_finite()
            || dt <= 0.
            || horizon == 0
            || horizon > 100000
            || w.iter().any(|x| !x.is_finite() || *x <= 0.)
            || links.iter().any(|l| {
                l.lag == 0
                    || [l.storage_m, l.send_veh, l.receive_veh]
                        .iter()
                        .any(|x| !x.is_finite() || *x <= 0.)
            })
        {
            return Err(bad("invalid marked model domain"));
        }
        Ok(Self {
            dt,
            horizon,
            tick: 0,
            links,
            w,
            pending: Queue::new(horizon + 1)?,
            trunk: Queue::new(2 * horizon + 1)?,
            branch: [Queue::new(3 * horizon + 1)?, Queue::new(3 * horizon + 1)?],
            req: Mark::default(),
            exit: Mark::default(),
            age: [0.; 2],
            elapsed: [0.; 2],
            max_mass: 0.,
            max_birth: 0.,
            peak_pending: 0.,
            blocked: 0,
        })
    }
    /// Requests are nonnegative masses born at the right endpoint. Controls
    /// are capacity factors per link (closure/signal); storage stays fixed.
    pub fn step(
        &mut self,
        request: [f64; 2],
        receive_factor: [f64; 3],
        send_factor: [f64; 3],
    ) -> CoreResult<()> {
        if self.tick == self.horizon
            || request
                .iter()
                .chain(receive_factor.iter())
                .chain(send_factor.iter())
                .any(|x| !x.is_finite() || *x < 0.)
        {
            return Err(bad("marked tick domain"));
        }
        let now = self.tick + 1;
        let time = now as f64 * self.dt;
        if !time.is_finite() || request.iter().any(|m| !(m * time).is_finite()) {
            return Err(bad("marked clock/birth overflow"));
        }
        for r in 0..2 {
            self.age[r] += self.dt * (self.req.mass[r] - self.exit.mass[r]);
        }
        let old_space = [
            (self.links[0].storage_m - self.trunk.stock.space(self.w)).max(0.),
            (self.links[1].storage_m - self.branch[0].stock.space(self.w)).max(0.),
            (self.links[2].storage_m - self.branch[1].stock.space(self.w)).max(0.),
        ];
        let mut receive =
            std::array::from_fn::<_, 3, _>(|i| self.links[i].receive_veh * receive_factor[i]);
        let mut space = old_space;
        let mut send = std::array::from_fn::<_, 3, _>(|i| self.links[i].send_veh * send_factor[i]);
        if receive.iter().chain(send.iter()).any(|v| !v.is_finite()) {
            return Err(bad("marked supply overflow"));
        }
        // Downstream sink first, but receiving space above is frozen.
        for r in 0..2 {
            while let Some(h) = self.branch[r].rows.front().copied() {
                if now - h.entry < self.links[r + 1].lag {
                    break;
                }
                let a = 1f64.min(ratio(send[r + 1], h.mark.total()));
                if a <= 0. {
                    break;
                }
                let m = self.branch[r].take(a);
                self.exit.add(m);
                self.elapsed[r] += time * m.mass[r] - m.birth[r];
                send[r + 1] = (send[r + 1] - m.total()).max(0.);
                if a < 1. {
                    break;
                }
            }
        }
        // Strict FIFO at shared diverge: both marks in a head move with
        // the same fraction; a constrained turn may hold the other turn.
        let mut held = false;
        while let Some(h) = self.trunk.rows.front().copied() {
            if now - h.entry < self.links[0].lag {
                break;
            }
            let a = head_fraction(
                h.mark,
                self.w,
                send[0],
                [receive[1], receive[2]],
                [space[1], space[2]],
            );
            if a < 1.
                && h.mark.mass[0] > 0.
                && h.mark.mass[1] > 0.
                && send[0] > 0.
                && (ratio(receive[1], h.mark.mass[0])
                    .min(ratio(space[1], self.w[0] * h.mark.mass[0]))
                    .min(ratio(receive[2], h.mark.mass[1]))
                    .min(ratio(space[2], self.w[1] * h.mark.mass[1])))
                    < 1f64.min(ratio(send[0], h.mark.total()))
            {
                held = true
            }
            if a <= 0. {
                break;
            }
            let m = self.trunk.take(a);
            send[0] = (send[0] - m.total()).max(0.);
            for r in 0..2 {
                self.branch[r].push(m.only(r), now)?;
                receive[r + 1] = (receive[r + 1] - m.mass[r]).max(0.);
                space[r + 1] = (space[r + 1] - m.mass[r] * self.w[r]).max(0.);
            }
            if a < 1. {
                break;
            }
        }
        self.blocked += usize::from(held);
        let request = Mark {
            mass: request,
            birth: request.map(|m| m * time),
        };
        self.req.add(request);
        self.pending.push(request, now)?;
        while let Some(h) = self.pending.rows.front().copied() {
            let a = 1f64
                .min(ratio(receive[0], h.mark.total()))
                .min(ratio(space[0], h.mark.space(self.w)));
            if a <= 0. {
                break;
            }
            let m = self.pending.take(a);
            self.trunk.push(m, now)?;
            receive[0] = (receive[0] - m.total()).max(0.);
            space[0] = (space[0] - m.space(self.w)).max(0.);
            if a < 1. {
                break;
            }
        }
        if !self.req.valid()
            || !self.exit.valid()
            || self
                .age
                .iter()
                .chain(self.elapsed.iter())
                .any(|v| !v.is_finite())
        {
            return Err(bad("marked ledger overflow"));
        }
        self.tick = now;
        self.peak_pending = self.peak_pending.max(self.pending.stock.total());
        let mut on = self.trunk.stock;
        for b in &self.branch {
            on.add(b.stock)
        }
        for r in 0..2 {
            let mass =
                (self.req.mass[r] - self.exit.mass[r] - self.pending.stock.mass[r] - on.mass[r])
                    .abs();
            let birth = (self.req.birth[r]
                - self.exit.birth[r]
                - self.pending.stock.birth[r]
                - on.birth[r])
                .abs();
            self.max_mass = self.max_mass.max(mass);
            self.max_birth = self.max_birth.max(birth);
            if mass > 1e-8 * self.req.mass[r].max(1.) || birth > 1e-8 * self.req.birth[r].max(1.) {
                return Err(bad("marked mass/birth balance"));
            }
        }
        for (q, l) in [&self.trunk, &self.branch[0], &self.branch[1]]
            .into_iter()
            .zip(self.links)
        {
            if q.stock.space(self.w) > l.storage_m + 1e-8 * l.storage_m.max(1.) {
                return Err(bad("marked storage overflow"));
            }
        }
        Ok(())
    }
    pub fn metrics(&self) -> CoreResult<Metrics> {
        let t = self.tick as f64 * self.dt;
        let pending = self.pending.recompute();
        let mut on = self.trunk.recompute();
        for q in &self.branch {
            on.add(q.recompute())
        }
        let mut res = [0.; 2];
        for r in 0..2 {
            if (self.req.mass[r] - self.exit.mass[r] - pending.mass[r] - on.mass[r]).abs()
                > 1e-8 * self.req.mass[r].max(1.)
                || (self.req.birth[r] - self.exit.birth[r] - pending.birth[r] - on.birth[r]).abs()
                    > 1e-8 * self.req.birth[r].max(1.)
            {
                return Err(bad("marked independent queue census"));
            }
            res[r] = self.age[r]
                - (self.elapsed[r] + t * (pending.mass[r] + on.mass[r])
                    - pending.birth[r]
                    - on.birth[r]);
            if res[r].abs() > 1e-8 * self.age[r].abs().max(1.) {
                return Err(bad("marked residence identity"));
            }
        }
        Ok(Metrics {
            time_s: t,
            requested: self.req,
            exited: self.exit,
            pending,
            on_link: on,
            residence_veh_s: self.age,
            completed_elapsed_veh_s: self.elapsed,
            max_mass_residual: self.max_mass,
            max_birth_residual: self.max_birth,
            age_identity_residual: res,
            peak_pending_veh: self.peak_pending,
            blocked_mixed_ticks: self.blocked,
            peak_queue_rows: [
                self.pending.peak,
                self.trunk.peak,
                self.branch[0].peak,
                self.branch[1].peak,
            ],
            reserved_queue_payload_bytes: [
                &self.pending,
                &self.trunk,
                &self.branch[0],
                &self.branch[1],
            ]
            .iter()
            .map(|q| q.rows.capacity() * std::mem::size_of::<Batch>())
            .sum(),
        })
    }
}
pub fn project_manifest(
    m: serde_json::Value,
    dt: f64,
    end: f64,
    scale: f64,
) -> CoreResult<serde_json::Value> {
    use serde_json::json;
    if m["schema"] != "metroflow_native_declaration_v1"
        || !dt.is_finite()
        || dt <= 0.
        || !end.is_finite()
        || end <= 0.
        || end > 86400.
        || (end / dt).fract() != 0.
        || end / dt > 100000.
        || !scale.is_finite()
        || scale <= 0.
        || scale > 1.
    {
        return Err(bad("projection domain"));
    }
    let budget = m["byte_budget"]
        .as_u64()
        .ok_or_else(|| bad("manifest budget"))? as usize;
    if budget == 0 || budget > 6 * 1024usize.pow(3) {
        return Err(bad("manifest budget"));
    }
    let cal: crate::v1_calendar::FactorizedDeclaration =
        serde_json::from_value(m["calendar"].clone()).map_err(|_| bad("calendar"))?;
    let cal = cal.compile(budget)?;
    let labels = cal.owned_labels();
    let profiles = cal.owned_profiles();
    let is_car = |l: &crate::v1_calendar::Leg| {
        l.parent.is_none()
            && labels[l.metadata[3] as usize] == "\"car\""
            && labels[l.metadata[7] as usize] == "\"interzonal\""
    };
    let mut by = BTreeMap::<u32, f64>::new();
    for l in cal.owned_legs() {
        if is_car(l) {
            *by.entry(l.metadata[0]).or_default() += l.amounts[1];
        }
    }
    let (&origin, &total) = by
        .iter()
        .max_by(|a, b| a.1.total_cmp(b.1).then_with(|| b.0.cmp(a.0)))
        .ok_or_else(|| bad("no car origin"))?;
    let mut amounts = vec![0.; profiles.len()];
    for l in cal.owned_legs() {
        if is_car(l) && l.metadata[0] == origin {
            amounts[l.metadata[5] as usize] += l.amounts[1];
        }
    }
    let s = &m["static"];
    let mut turns = BTreeMap::<&str, Vec<&str>>::new();
    for t in s["allowed_turns"]
        .as_array()
        .ok_or_else(|| bad("turn registry"))?
    {
        let a = t[0].as_str().ok_or_else(|| bad("turn"))?;
        let b = t[1].as_str().ok_or_else(|| bad("turn"))?;
        turns.entry(a).or_default().push(b);
    }
    for v in turns.values_mut() {
        v.sort_unstable();
        v.dedup();
    }
    let (&trunk, branches) = turns
        .iter()
        .find(|(a, v)| v.iter().filter(|b| *b != *a).count() >= 2)
        .ok_or_else(|| bad("no diverge"))?;
    let mut choices = branches.iter().copied().filter(|b| *b != trunk);
    let ids = [trunk, choices.next().unwrap(), choices.next().unwrap()];
    let mut indices = [0; 3];
    let mut links = [Link {
        storage_m: 1.,
        lag: 1,
        send_veh: 1.,
        receive_veh: 1.,
    }; 3];
    let car = s["class_names"]
        .as_array()
        .and_then(|a| a.iter().position(|x| x == "car"))
        .ok_or_else(|| bad("car class"))?;
    let speed = s["classes"][car][0].as_f64().ok_or_else(|| bad("speed"))?;
    let footprint = s["classes"][car][12]
        .as_f64()
        .ok_or_else(|| bad("footprint"))?;
    for i in 0..3 {
        let j = s["link_ids"]
            .as_array()
            .and_then(|v| v.iter().position(|x| x == ids[i]))
            .ok_or_else(|| bad("link id"))?;
        indices[i] = j;
        let g: Vec<f64> =
            serde_json::from_value(s["groups"][j].clone()).map_err(|_| bad("group"))?;
        if g.len() != 6 || g.iter().any(|v| !v.is_finite() || *v <= 0.) {
            return Err(bad("group domain"));
        }
        links[i] = Link {
            storage_m: g[4],
            lag: (g[0] / g[1].min(speed) / dt).ceil().max(1.) as usize,
            receive_veh: g[2] * dt,
            send_veh: g[3] * dt,
        };
    }
    // Deliberately projected origin demand, not actual OD assignment. One
    // branch receives a declared capacity restriction; only that branch is relieved.
    let mut base_links = links;
    base_links[1].receive_veh *= scale;
    base_links[1].send_veh *= scale;
    let mut relief_links = base_links;
    relief_links[1].receive_veh *= 2.;
    relief_links[1].send_veh *= 2.;
    let steps = (end / dt) as usize;
    let mut a = Diverge::new(dt, steps, base_links, [footprint; 2])?;
    let mut b = Diverge::new(dt, steps, relief_links, [footprint; 2])?;
    let mut last = 0.;
    let t = std::time::Instant::now();
    for k in 1..=steps {
        let now = k as f64 * dt;
        let u = crate::v1_journey::fsum(profiles.iter().zip(&amounts).map(|(p, &m)| {
            m * crate::v1_journey::fsum(
                p.iter()
                    .map(|&(x, y, w)| w * (now.min(y) - x).max(0.) / (y - x)),
            )
        }));
        let delta = (u - last).max(0.);
        last = last.max(u);
        let req = [0.75 * delta, 0.25 * delta];
        let mid = now - dt / 2.;
        let mut recv = [1.; 3];
        let mut send = [1.; 3];
        for i in 0..3 {
            let j = indices[i];
            for row in s["windows"].as_array().ok_or_else(|| bad("windows"))? {
                if row[0].as_u64() == Some(j as u64)
                    && row[1].as_f64().is_some_and(|x| x <= mid)
                    && row[2].as_f64().is_some_and(|x| mid < x)
                {
                    recv[i] *= row[3].as_f64().ok_or_else(|| bad("window factor"))?;
                }
            }
            send[i] = recv[i];
            if let Some(sig) = s["signals"][j].as_array() {
                let cycle = sig[0].as_f64().ok_or_else(|| bad("signal"))?;
                let green = sig[1].as_f64().ok_or_else(|| bad("signal"))?;
                let offset = sig[2].as_f64().ok_or_else(|| bad("signal"))?;
                if cycle <= 0. {
                    return Err(bad("signal cycle"));
                }
                if (mid - offset).rem_euclid(cycle) >= green {
                    send[i] = 0.;
                }
            }
        }
        a.step(req, recv, send)?;
        b.step(req, recv, send)?;
    }
    Ok(
        json!({"schema":"metroflow_marked_diverge_v1","scope":"actual frozen legal turns and car link coefficients; busiest outward car origin intent projected 75/25 onto two hypothetical branches; common FIFO head and discrete right-endpoint births; no native kinetic equivalence, no actual OD assignment or induced demand","city_identity":s["city_identity"],"schedule_identity":s["schedule_identity"],"origin":labels[origin as usize],"intended_car_veh":total,"links":ids,"dt_s":dt,"end_s":end,"steps":steps,"branch0_scale":scale,"baseline_links":base_links,"relief_links":relief_links,"baseline":a.metrics()?,"relief":b.metrics()?,"simulation_wall_s":t.elapsed().as_secs_f64()}),
    )
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn mixed_head_spillback_and_marked_residence() {
        let mut a = Diverge::new(
            1.,
            16,
            [Link {
                storage_m: 100.,
                lag: 1,
                send_veh: 10.,
                receive_veh: 10.,
            }; 3],
            [5., 10.],
        )
        .unwrap();
        a.step([1., 1.], [1.; 3], [1.; 3]).unwrap();
        a.step([0.; 2], [1., 0.025, 1.], [1.; 3]).unwrap();
        assert_eq!(a.trunk.stock.mass, [0.75, 0.75]);
        assert_eq!(a.branch[0].stock.mass, [0.25, 0.]);
        assert_eq!(a.branch[1].stock.mass, [0., 0.25]);
        for _ in 0..8 {
            a.step([0.; 2], [1.; 3], [1.; 3]).unwrap()
        }
        let m = a.metrics().unwrap();
        assert_eq!(m.exited.mass, [1., 1.]);
        assert_eq!(m.exited.birth, [1., 1.]);
        assert_eq!(m.age_identity_residual, [0.; 2]);
        assert_eq!(m.residence_veh_s, [2.75, 2.75]);
    }
    #[test]
    fn shared_head_fraction_uses_footprint_and_common_cut() {
        let m = Mark {
            mass: [2., 1.],
            birth: [10., 6.],
        };
        assert_eq!(
            head_fraction(m, [5., 10.], 100., [100.; 2], [100., 2.5]),
            0.25
        );
        let q = m.scaled(0.25);
        assert_eq!(q.mass, [0.5, 0.25]);
        assert_eq!(q.birth, [2.5, 1.5]);
        assert_eq!(head_fraction(m, [5., 10.], 100., [0., 100.], [100.; 2]), 0.);
    }
    #[test]
    fn exhaustive_short_binary_capacity_sequences() {
        for mask in 0..256usize {
            let mut q = Diverge::new(
                1.,
                24,
                [Link {
                    storage_m: 25.,
                    lag: 2,
                    send_veh: 2.,
                    receive_veh: 2.,
                }; 3],
                [5., 10.],
            )
            .unwrap();
            for k in 0..24 {
                let req = if k < 8 { [0.5, 0.25] } else { [0.; 2] };
                let f = if k < 8 { ((mask >> k) & 1) as f64 } else { 1. };
                q.step(req, [1., f, 1.], [1.; 3]).unwrap();
            }
            let m = q.metrics().unwrap();
            assert_eq!(m.requested.mass, [4., 2.]);
            assert!(m.max_mass_residual < 1e-10 && m.max_birth_residual < 1e-9);
        }
    }
}
