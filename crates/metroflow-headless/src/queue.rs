//! Same fixed-route whole-head closure as historical C++ research solver.
use crate::input::{Input, Result, FOOTPRINT};
use rayon::prelude::*;
use serde::Serialize;
use std::{
    cmp::Ordering,
    collections::{BinaryHeap, VecDeque},
};
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
#[repr(u8)]
enum Phase {
    #[default]
    Release,
    Enter,
    Complete,
    Service,
    Wake,
}
#[derive(Clone, Copy, Debug, Default)]
struct Event {
    t: f64,
    mass: f64,
    q: f64,
    began: f64,
    key: u64,
    group: u32,
    edge: u16,
    phase: Phase,
    returning: bool,
}
impl PartialEq for Event {
    fn eq(&self, o: &Self) -> bool {
        self.t.to_bits() == o.t.to_bits() && self.key == o.key
    }
}
impl Eq for Event {}
impl PartialOrd for Event {
    fn partial_cmp(&self, o: &Self) -> Option<Ordering> {
        Some(self.cmp(o))
    }
}
impl Ord for Event {
    fn cmp(&self, o: &Self) -> Ordering {
        o.t.total_cmp(&self.t).then(o.key.cmp(&self.key))
    }
}
#[derive(Clone, Copy, Default, Debug)]
struct Sum {
    sum: f64,
    correction: f64,
}
impl Sum {
    fn add(&mut self, x: f64) {
        let t = self.sum + x;
        self.correction += if self.sum.abs() >= x.abs() {
            (self.sum - t) + x
        } else {
            (x - t) + self.sum
        };
        self.sum = t
    }
    fn get(self) -> f64 {
        self.sum + self.correction
    }
}
#[derive(Clone, Copy, Default)]
struct Ledger {
    released: Sum,
    admitted: Sum,
    exited: Sum,
    completed: Sum,
    trip: Sum,
}
#[derive(Clone, Copy)]
struct Request {
    source: Option<u32>,
    batch: Event,
    requested: f64,
}
#[derive(Default)]
struct Link {
    stock: Sum,
    peak: f64,
    remaining: Sum,
    received: Sum,
    peak_receive: f64,
    epoch: Option<u64>,
    wait: Sum,
    blocked: Sum,
    free_at: f64,
    finish: f64,
    fifo: VecDeque<Event>,
    requests: VecDeque<Request>,
    scheduled: bool,
    wake: bool,
}
#[derive(Clone, Copy, Serialize, Debug)]
pub struct Config {
    pub mesh_s: f64,
    pub horizon_s: f64,
    pub seed: u64,
    pub shock_link: Option<u32>,
    pub shock_factor: f64,
}
#[derive(Serialize, Debug, PartialEq)]
pub struct Class {
    pub expected: f64,
    pub released: f64,
    pub admitted: f64,
    pub exited: f64,
    pub completed: f64,
    pub active: f64,
    pub road: f64,
    pub error: f64,
    pub trip_seconds: f64,
}
#[derive(Serialize, Debug, PartialEq)]
pub struct Snapshot {
    pub time_s: f64,
    pub classes: [Class; 3],
    pub max_storage_ratio: f64,
    pub max_receiving_ratio: f64,
    pub storage_blocks: u64,
    pub rate_blocks: u64,
    pub queued_requests: u64,
    pub max_meter_error: f64,
    pub outstanding_blocked_veh_s: f64,
}
#[derive(Serialize, Debug, PartialEq)]
pub struct Run {
    pub initial_batches: u64,
    pub event_count: u64,
    pub transfers: u64,
    pub event_bytes: usize,
    pub wait_veh_s: f64,
    pub blocked_veh_s: f64,
    pub worst_link: usize,
    pub snapshots: Vec<Snapshot>,
}
fn mix(mut x: u64) -> u64 {
    x = x.wrapping_add(0x9e3779b97f4a7c15);
    x = (x ^ (x >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
    x = (x ^ (x >> 27)).wrapping_mul(0x94d049bb133111eb);
    x ^ (x >> 31)
}
pub fn rank_phase(g: u32, j: u32, n: u32, seed: u64) -> f64 {
    if seed == 0 || j == n - 1 - j {
        return (j as f64 + 0.5) / n as f64;
    }
    let k = j.min(n - 1 - j);
    let z = mix(seed ^ mix(g as u64) ^ mix(k as u64 + 0x58e4e3));
    let u = ((z >> 12) as f64 + 0.5) / 4503599627370496.;
    let q = (k as f64 + u) / n as f64;
    if j == k {
        q
    } else {
        1. - q
    }
}
fn tick(t: f64) -> f64 {
    10. * (t / 10. - 1e-12).ceil()
}
#[derive(Clone, Copy)]
struct Prepared {
    bins: u32,
    offset: u64,
}
struct Engine<'a> {
    input: &'a Input,
    cfg: Config,
    links: Vec<Link>,
    prepared: Vec<Prepared>,
    heap: BinaryHeap<Event>,
    key: u64,
    book: [Ledger; 3],
    expected: [Sum; 3],
    out_completed: Sum,
    return_released: Sum,
    events: u64,
    transfers: u64,
    storage_blocks: u64,
    rate_blocks: u64,
    queued_requests: u64,
}
impl<'a> Engine<'a> {
    fn cls(&self, b: Event) -> usize {
        self.input.groups[b.group as usize].class as usize
    }
    fn length(&self, b: Event) -> f64 {
        b.mass * FOOTPRINT[self.cls(b)]
    }
    fn route(&self, b: Event) -> usize {
        let g = self.input.groups[b.group as usize];
        if b.returning {
            g.backward.expect("paired return") as usize
        } else {
            g.forward as usize
        }
    }
    fn next_key(&mut self) -> u64 {
        let k = self.key;
        self.key = self.key.checked_add(1).expect("event ordinal overflow");
        k
    }
    fn push(&mut self, mut b: Event, t: f64, phase: Phase) -> Result<()> {
        if !t.is_finite() || t < b.t {
            return Err("noncausal event".into());
        }
        b.t = t;
        b.phase = phase;
        b.key = self.next_key();
        self.heap.push(b);
        Ok(())
    }
    fn signal(&mut self, i: usize, t: f64, p: Phase) {
        let key = self.next_key();
        self.heap.push(Event {
            t,
            key,
            group: i as u32,
            phase: p,
            ..Event::default()
        });
    }
    fn wake(&mut self, i: usize, t: f64) {
        let l = &mut self.links[i];
        if !l.requests.is_empty() && !l.wake {
            l.wake = true;
            self.signal(i, t, Phase::Wake)
        }
    }
    fn first(&self, i: usize, j: u32) -> Event {
        let g = self.input.groups[i];
        let w = self.input.windows[g.purpose as usize];
        let p = self.prepared[i];
        let q = rank_phase(g.phase_group, j, p.bins, self.cfg.seed);
        Event {
            t: w[0] + q * (w[1] - w[0]),
            mass: g.mass / p.bins as f64,
            q,
            began: 0.,
            key: p.offset + j as u64,
            group: i as u32,
            edge: 0,
            phase: Phase::Release,
            returning: false,
        }
    }
    fn schedule(&mut self, i: usize, t: f64) {
        let l = &self.links[i];
        if l.scheduled || l.fifo.is_empty() {
            return;
        }
        let b = *l.fifo.front().unwrap();
        let ready = b.t + self.input.passage[self.route(b)][b.edge as usize];
        let cap = self.input.roads[i].exit
            * if self.cfg.shock_link == Some(i as u32) {
                self.cfg.shock_factor
            } else {
                1.
            };
        let l = &mut self.links[i];
        let begin = ready.max(l.free_at);
        l.wait.add(b.mass * (begin - ready));
        l.finish = begin + b.mass / cap;
        l.scheduled = true;
        let end = t.max(tick(l.finish));
        self.signal(i, end, Phase::Service);
    }
    fn admit(&mut self, i: usize, mut b: Event, t: f64) -> Result<()> {
        let length = self.length(b);
        let c = self.cls(b);
        let r = self.input.roads[i];
        let l = &mut self.links[i];
        b.t = t;
        l.fifo.push_back(b);
        l.stock.add(length);
        l.remaining.add(-b.mass);
        l.received.add(b.mass);
        l.peak = l.peak.max(l.stock.get());
        l.peak_receive = l.peak_receive.max(l.received.get() / (10. * r.entry));
        if l.stock.get() > r.storage + 1e-9
            || l.remaining.get() < -1e-9
            || l.received.get() > 10. * r.entry + 1e-9
        {
            return Err("receiving/storage overflow".into());
        }
        if b.edge == 0 {
            self.book[c].admitted.add(b.mass)
        }
        self.schedule(i, t);
        Ok(())
    }
    fn depart(&mut self, i: usize, t: f64, blocked: bool) -> Result<Event> {
        let l = &self.links[i];
        if !l.scheduled || l.fifo.is_empty() {
            return Err("invalid head departure".into());
        }
        let b = *l.fifo.front().unwrap();
        let length = self.length(b);
        let l = &mut self.links[i];
        l.fifo.pop_front();
        l.stock.add(-length);
        if l.fifo.is_empty() {
            if l.stock.get().abs() > 1e-7 {
                return Err("empty stock residual".into());
            }
            l.stock = Sum::default()
        }
        if l.stock.get() < -1e-9 {
            return Err("negative stock".into());
        }
        l.free_at = if blocked { l.finish.max(t) } else { l.finish };
        l.scheduled = false;
        self.wake(i, t);
        self.schedule(i, t);
        Ok(b)
    }
    fn request(&mut self, i: usize, r: Request, t: f64) {
        let b = r
            .source
            .map_or(r.batch, |s| *self.links[s as usize].fifo.front().unwrap());
        let length = self.length(b);
        let l = &mut self.links[i];
        if !l.requests.is_empty() || l.stock.get() + length > self.input.roads[i].storage + 1e-10 {
            self.queued_requests += 1
        }
        l.requests.push_back(r);
        self.wake(i, t);
    }
    fn process(&mut self, e: Event) -> Result<()> {
        self.events += 1;
        let i = e.group as usize;
        match e.phase {
            Phase::Wake => {
                let epoch = (e.t / 10.).round() as u64;
                let r = self.input.roads[i];
                let l = &mut self.links[i];
                l.wake = false;
                if (e.t - 10. * epoch as f64).abs() > 1e-8 || l.epoch.is_some_and(|x| x > epoch) {
                    return Err("receiving clock".into());
                }
                if l.epoch != Some(epoch) {
                    l.epoch = Some(epoch);
                    l.remaining = Sum {
                        sum: 10. * r.entry,
                        correction: 0.,
                    };
                    l.received = Sum::default()
                }
                while let Some(req) = self.links[i].requests.front().copied() {
                    let mut b = req
                        .source
                        .map_or(req.batch, |s| *self.links[s as usize].fifo.front().unwrap());
                    let l = &mut self.links[i];
                    let length =
                        b.mass * FOOTPRINT[self.input.groups[b.group as usize].class as usize];
                    if l.stock.get() + length > r.storage + 1e-10 {
                        self.storage_blocks += 1;
                        break;
                    }
                    if b.mass > l.remaining.get() + 1e-12 {
                        self.rate_blocks += 1;
                        self.wake(i, 10. * (epoch + 1) as f64);
                        break;
                    }
                    l.requests.pop_front();
                    l.blocked.add(b.mass * (e.t - req.requested));
                    if let Some(s) = req.source {
                        b = self.depart(s as usize, e.t, e.t > req.requested)?;
                        b.edge += 1;
                        self.transfers += 1;
                    }
                    self.admit(i, b, e.t)?;
                }
            }
            Phase::Service => {
                let l = &self.links[i];
                if !l.scheduled || l.fifo.is_empty() {
                    return Err("stale service".into());
                }
                let b = *l.fifo.front().unwrap();
                let p = &self.input.paths[self.route(b)];
                if b.edge as usize + 1 == p.len() {
                    let b = self.depart(i, e.t, false)?;
                    let c = self.cls(b);
                    self.book[c].exited.add(b.mass);
                    let g = self.input.groups[b.group as usize];
                    let d = if b.returning { g.origin } else { g.destination };
                    self.push(b, e.t + d, Phase::Complete)?;
                } else {
                    let dest = p[b.edge as usize + 1] as usize;
                    self.request(
                        dest,
                        Request {
                            source: Some(i as u32),
                            batch: Event::default(),
                            requested: e.t,
                        },
                        e.t,
                    );
                }
            }
            Phase::Release => {
                let g = self.input.groups[i];
                if !e.returning {
                    let p = self.prepared[i];
                    let j = (e.key - p.offset) as u32;
                    if j + 1 < p.bins {
                        self.heap.push(self.first(i, j + 1))
                    }
                } else {
                    self.return_released.add(e.mass);
                }
                self.book[g.class as usize].released.add(e.mass);
                let mut b = e;
                b.began = e.t;
                b.edge = 0;
                let d = if b.returning { g.destination } else { g.origin };
                self.push(b, 10. + tick(e.t + d), Phase::Enter)?;
            }
            Phase::Enter => {
                let r = self.route(e);
                self.request(
                    self.input.paths[r][0] as usize,
                    Request {
                        source: None,
                        batch: e,
                        requested: e.t,
                    },
                    e.t,
                );
            }
            Phase::Complete => {
                let g = self.input.groups[i];
                let l = &mut self.book[g.class as usize];
                l.completed.add(e.mass);
                l.trip.add(e.mass * (e.t - e.began));
                if !e.returning && g.backward.is_some() {
                    self.out_completed.add(e.mass);
                    let mut b = e;
                    b.returning = true;
                    let w = self.input.windows[g.purpose as usize];
                    self.push(
                        b,
                        (w[2] + b.q * (w[3] - w[2])).max(e.t + self.input.dwell),
                        Phase::Release,
                    )?;
                }
            }
        }
        Ok(())
    }
    fn snapshot(&self, t: f64) -> Result<Snapshot> {
        let mut road = [Sum::default(); 3];
        let mut active = [Sum::default(); 3];
        let mut max_storage: f64 = 0.;
        let mut max_receive: f64 = 0.;
        let mut meter: f64 = 0.;
        let mut outstanding = Sum::default();
        for (i, l) in self.links.iter().enumerate() {
            let mut occ = Sum::default();
            for &b in &l.fifo {
                let c = self.cls(b);
                road[c].add(b.mass);
                active[c].add(b.mass);
                occ.add(self.length(b))
            }
            meter = meter.max((occ.get() - l.stock.get()).abs());
            max_storage = max_storage.max(l.peak / self.input.roads[i].storage);
            max_receive = max_receive.max(l.peak_receive);
            for r in &l.requests {
                let b = r
                    .source
                    .map_or(r.batch, |s| *self.links[s as usize].fifo.front().unwrap());
                if r.source.is_none() {
                    active[self.cls(b)].add(b.mass)
                }
                outstanding.add(b.mass * (t - r.requested));
            }
        }
        // No heap clone or O(N log N) snapshot pop: aggregate independently over
        // live heap slots. Compensated reductions retain the same tolerance.
        for &b in &self.heap {
            if matches!(b.phase, Phase::Enter | Phase::Complete) {
                active[self.cls(b)].add(b.mass)
            }
        }
        let classes = std::array::from_fn(|i| {
            let l = self.book[i];
            let err = (l.released.get() - l.completed.get() - active[i].get())
                .abs()
                .max((l.admitted.get() - l.exited.get() - road[i].get()).abs());
            Class {
                expected: self.expected[i].get(),
                released: l.released.get(),
                admitted: l.admitted.get(),
                exited: l.exited.get(),
                completed: l.completed.get(),
                active: active[i].get(),
                road: road[i].get(),
                error: err,
                trip_seconds: l.trip.get(),
            }
        });
        if classes
            .iter()
            .any(|c| c.error > 1e-8 * c.released.max(1.) || c.released > c.expected + 1e-8)
            || meter > 1e-6
            || max_storage > 1. + 1e-9
            || max_receive > 1. + 1e-9
            || self.return_released.get() > self.out_completed.get() + 1e-8
        {
            return Err("class/return/storage ledger violated".into());
        }
        Ok(Snapshot {
            time_s: t,
            classes,
            max_storage_ratio: max_storage,
            max_receiving_ratio: max_receive,
            storage_blocks: self.storage_blocks,
            rate_blocks: self.rate_blocks,
            queued_requests: self.queued_requests,
            max_meter_error: meter,
            outstanding_blocked_veh_s: outstanding.get(),
        })
    }
}
pub fn run(input: &Input, cfg: Config) -> Result<Run> {
    if !(cfg.mesh_s.is_finite()
        && cfg.mesh_s > 0.
        && cfg.horizon_s > 0.
        && cfg.horizon_s <= 86400.
        && cfg.shock_factor.is_finite()
        && cfg.shock_factor > 0.)
        || cfg
            .shock_link
            .is_some_and(|x| x as usize >= input.roads.len())
    {
        return Err("invalid run config".into());
    }
    let bins = crate::preflight::ranks(
        input,
        cfg.mesh_s,
        std::env::var_os("METROFLOW_AVX_PREFLIGHT").is_some(),
    )?;
    let mut key = 0u64;
    let mut prepared = Vec::with_capacity(bins.len());
    let mut expected = [Sum::default(); 3];
    for (g, b) in input.groups.iter().zip(bins) {
        prepared.push(Prepared {
            bins: b,
            offset: key,
        });
        key = key.checked_add(b as u64).ok_or("key overflow")?;
        expected[g.class as usize].add(g.mass * if g.backward.is_some() { 2. } else { 1. });
    }
    let initial_batches = key;
    let mut e = Engine {
        input,
        cfg,
        links: (0..input.roads.len()).map(|_| Link::default()).collect(),
        prepared,
        heap: BinaryHeap::new(),
        key,
        book: [Ledger::default(); 3],
        expected,
        out_completed: Sum::default(),
        return_released: Sum::default(),
        events: 0,
        transfers: 0,
        storage_blocks: 0,
        rate_blocks: 0,
        queued_requests: 0,
    };
    // Heapify once in linear time, with original stable event ordinals.
    let first: Vec<Event> = (0..input.groups.len())
        .into_par_iter()
        .map(|i| e.first(i, 0))
        .collect();
    e.heap = BinaryHeap::from(first);
    let mut horizons: Vec<_> = [25720., 28800., 43200., 64800.]
        .into_iter()
        .filter(|&t| t < cfg.horizon_s)
        .collect();
    horizons.push(cfg.horizon_s);
    let mut snapshots = Vec::new();
    for t in horizons {
        while e.heap.peek().is_some_and(|b| b.t <= t) {
            let b = e.heap.pop().unwrap();
            e.process(b)?
        }
        snapshots.push(e.snapshot(t)?);
    }
    let mut wait = Sum::default();
    let mut blocked = Sum::default();
    let mut worst = 0;
    for (i, l) in e.links.iter().enumerate() {
        wait.add(l.wait.get());
        blocked.add(l.blocked.get());
        if l.blocked.get() > e.links[worst].blocked.get() {
            worst = i
        }
    }
    Ok(Run {
        initial_batches,
        event_count: e.events,
        transfers: e.transfers,
        event_bytes: std::mem::size_of::<Event>(),
        wait_veh_s: wait.get(),
        blocked_veh_s: blocked.get(),
        worst_link: worst,
        snapshots,
    })
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn mixed_constraints_and_replay() {
        for (storage, entry) in [(12., 1.), (100., 0.1)] {
            let n=format!("1 1 2 1 0\n1 {entry} 1 {storage}\n1 0\n0 0 0 0\n0 -1 0 1 0 0 2 0\n0 -1 0 1 0 0 0 1");
            let x = Input::parse(&n, "1\n1 1").unwrap();
            let c = Config {
                mesh_s: 600.,
                horizon_s: 120.,
                seed: 7,
                shock_link: None,
                shock_factor: 1.,
            };
            let r = run(&x, c).unwrap();
            assert_eq!(r, run(&x, c).unwrap());
            let s = &r.snapshots[0];
            assert_eq!(s.classes[0].completed, 1.);
            assert_eq!(s.classes[2].completed, 1.);
            assert_eq!(s.classes[0].error, 0.);
            if storage == 12. {
                assert_eq!(s.max_storage_ratio, 1.);
                assert!(s.storage_blocks > 0);
                assert_eq!(s.rate_blocks, 0)
            } else {
                assert_eq!(s.storage_blocks, 0);
                assert!(s.rate_blocks > 0);
                assert_eq!(s.max_receiving_ratio, 1.)
            }
        }
    }
    #[test]
    fn mirrored_ranks() {
        for n in 1..=128 {
            for j in 0..n {
                let q = rank_phase(17, j, n, 7);
                assert!((q + rank_phase(17, n - 1 - j, n, 7) - 1.).abs() < 5e-16);
                assert!(q >= j as f64 / n as f64 && q <= (j + 1) as f64 / n as f64);
            }
        }
    }
}
