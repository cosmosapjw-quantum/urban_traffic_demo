//! Native B01 service scheduling and whole-journey ledgers.
//! Road evolution is supplied by the sole road owner between prepare/finish.
//! Each transition is transactional: errors leave the last committed state intact.
use crate::v1_road::{EventRow, V1Road};
use pyo3::exceptions::{PyMemoryError, PyValueError};
use pyo3::prelude::*;
use std::collections::{HashMap, HashSet};
use std::time::Instant;

type Offer = (String, f64, f64);
type Sink = (String, f64, f64);
type Bus = (String, Vec<f64>, f64, f64);
type Person = (usize, usize, usize, f64, f64);
type Source = (String, f64, f64);
type Run = (usize, u8, f64, f64, f64); // stop index, STOP/ROAD/DONE, ready, partial sink, delay
type People = (f64, f64, f64, f64, f64);
type Service = (Vec<Run>, Vec<People>, Vec<bool>, Vec<f64>, Vec<bool>);
type Profile = Vec<(f64, f64, f64)>;
type Law = Vec<(f64, f64)>;
type JourneyLeg = (String, f64, Option<usize>, f64, Profile, u8, Law, Law);
type BusMeta = (usize, f64, f64, f64, f64, Law); // leg, calendar persons, window persons, birth moment, required CDF, egress
type FreightMeta = (usize, f64, f64, Law);
type Access = (usize, f64, f64, f64); // leg, mass, born, delay
type Journey = (
    f64,
    Vec<Access>,
    Vec<Access>,
    Vec<Access>,
    Vec<f64>,
    Vec<f64>,
    Vec<Vec<(f64, f64)>>,
    Vec<f64>,
);

fn bad(message: &str) -> PyErr {
    PyValueError::new_err(message.to_owned())
}
fn nonnegative(values: impl IntoIterator<Item = f64>) -> bool {
    values.into_iter().all(|x| x.is_finite() && x >= 0.0)
}
// Non-overlapping partials, with the final half-even adjustment of math.fsum.
fn fsum(values: impl IntoIterator<Item = f64>) -> f64 {
    let mut partials: Vec<f64> = Vec::new();
    for mut x in values {
        let mut i = 0;
        for j in 0..partials.len() {
            let mut y = partials[j];
            if x.abs() < y.abs() {
                std::mem::swap(&mut x, &mut y);
            }
            let hi = x + y;
            if !hi.is_finite() {
                return hi;
            }
            let lo = y - (hi - x);
            if lo != 0.0 {
                partials[i] = lo;
                i += 1;
            }
            x = hi;
        }
        partials.truncate(i);
        if x != 0.0 {
            partials.push(x);
        }
    }
    let Some(mut hi) = partials.pop() else {
        return 0.0;
    };
    let mut lo = 0.0;
    while let Some(y) = partials.pop() {
        let x = hi;
        hi = x + y;
        lo = y - (hi - x);
        if lo != 0.0 {
            break;
        }
    }
    if let Some(last) = partials.last() {
        if (lo < 0.0 && *last < 0.0) || (lo > 0.0 && *last > 0.0) {
            let y = lo * 2.0;
            let x = hi + y;
            if y == x - hi {
                hi = x;
            }
        }
    }
    hi
}

#[pyclass]
pub struct NativeServiceCore {
    buses: Vec<Bus>,
    people: Vec<Person>,
    freight: Vec<Source>,
    cars: Vec<Source>,
    people_by_run: Vec<Vec<usize>>,
    last_events: Vec<EventRow>,
    state: Service,
    pending: Option<(f64, Service)>,
}
impl NativeServiceCore {
    fn validate(&self, s: &Service) -> PyResult<()> {
        if s.0.len() != self.buses.len()
            || s.1.len() != self.people.len()
            || s.2.len() != self.freight.len()
            || s.3.len() != self.freight.len()
            || s.4.len() != self.cars.len()
        {
            return Err(bad("native service state lengths differ"));
        }
        for (b, v) in self.buses.iter().zip(&s.0) {
            if v.1 > 2
                || v.0 > b.1.len()
                || (v.1 == 2) != (v.0 == b.1.len())
                || !nonnegative([v.2, v.3, v.4])
                || v.3 > 1.0 + 1e-8
            {
                return Err(bad("invalid native bus state"));
            }
        }
        for (p, v) in self.people.iter().zip(&s.1) {
            // The reference's +1e-10 boarding tolerance can give a small
            // negative waiting moment; preserve it rather than clip the law.
            if !nonnegative([v.0, v.1, v.2, v.4])
                || !v.3.is_finite()
                || (v.0 + v.1 + v.2 - p.4).abs() > 1e-8_f64.max(1e-9 * p.4)
            {
                return Err(bad("native person conservation failure"));
            }
        }
        for (i, b) in self.buses.iter().enumerate() {
            let load = fsum(self.people_by_run[i].iter().map(|k| s.1[*k].1));
            if load > b.2 + 1e-8 {
                return Err(bad("native bus overcapacity"));
            }
        }
        for (f, c) in self.freight.iter().zip(&s.3) {
            if !c.is_finite() || *c < 0.0 || *c > f.2 + 1e-8 {
                return Err(bad("native freight conservation failure"));
            }
        }
        Ok(())
    }
}
#[pymethods]
impl NativeServiceCore {
    #[new]
    fn new(
        buses: Vec<Bus>,
        people: Vec<Person>,
        freight: Vec<Source>,
        cars: Vec<Source>,
    ) -> PyResult<Self> {
        let mut ids = HashSet::new();
        for b in &buses {
            if b.0.is_empty()
                || !ids.insert(b.0.clone())
                || b.1.is_empty()
                || !nonnegative(b.1.iter().copied().chain([b.2, b.3]))
                || b.2 == 0.0
                || b.1.windows(2).any(|x| x[0] > x[1])
            {
                return Err(bad("invalid native bus declaration"));
            }
        }
        for p in &people {
            if p.0 >= buses.len()
                || p.1 >= p.2
                || p.2 > buses[p.0].1.len()
                || !nonnegative([p.3, p.4])
            {
                return Err(bad("invalid native passenger declaration"));
            }
        }
        for sources in [&freight, &cars] {
            let mut ids = HashSet::new();
            if sources.iter().any(|f| {
                f.0.is_empty() || !ids.insert(&f.0) || !nonnegative([f.1, f.2]) || f.2 == 0.0
            }) {
                return Err(bad("invalid native freight/car declaration"));
            }
        }
        let state = (
            vec![(0, 0, 0.0, 0.0, 0.0); buses.len()],
            people.iter().map(|p| (p.4, 0.0, 0.0, 0.0, 0.0)).collect(),
            vec![false; freight.len()],
            vec![0.0; freight.len()],
            vec![false; cars.len()],
        );
        let mut people_by_run = vec![Vec::new(); buses.len()];
        for (k, p) in people.iter().enumerate() {
            people_by_run[p.0].push(k);
        }
        Ok(Self {
            buses,
            people,
            freight,
            cars,
            people_by_run,
            last_events: Vec::new(),
            state,
            pending: None,
        })
    }
    fn snapshot(&self) -> Service {
        self.state.clone()
    }
    fn road_events(&self) -> Vec<EventRow> {
        self.last_events.clone()
    }
    fn restore(&mut self, state: Service) -> PyResult<()> {
        self.validate(&state)?;
        self.state = state;
        self.pending = None;
        self.last_events.clear();
        Ok(())
    }
    fn abort(&mut self) {
        self.pending = None;
    }
    fn prepare(&mut self, t: f64, eligible: Vec<bool>) -> PyResult<Vec<Offer>> {
        if !nonnegative([t]) || eligible.len() != self.people.len() || self.pending.is_some() {
            return Err(bad(
                "invalid native service prepare clock/eligibility/phase",
            ));
        }
        self.validate(&self.state)?;
        let mut s = self.state.clone();
        let mut offers = Vec::new();
        for (i, b) in self.buses.iter().enumerate() {
            let v = s.0[i];
            if v.1 != 0 || t + 1e-10 < v.2.max(b.1[v.0]) {
                continue;
            }
            let load = fsum(self.people_by_run[i].iter().map(|k| s.1[*k].1));
            let keys: Vec<usize> = self.people_by_run[i]
                .iter()
                .copied()
                .filter(|k| {
                    self.people[*k].1 == v.0
                        && eligible[*k]
                        && self.people[*k].3 <= t + 1e-10
                        && s.1[*k].0 > 0.0
                })
                .collect();
            let total = fsum(keys.iter().map(|k| s.1[*k].0));
            if !total.is_finite() {
                return Err(bad("native boarding total overflow"));
            }
            let fraction = if total != 0.0 {
                1.0_f64.min((b.2 - load).max(0.0) / total)
            } else {
                0.0
            };
            for k in keys {
                let x = &mut s.1[k];
                let amount = x.0 * fraction;
                x.0 -= amount;
                x.1 += amount;
                x.3 += amount * (t - self.people[k].3);
            }
            offers.push((format!("bus:{}:{}", b.0, v.0), 1.0, t));
            s.0[i] = (v.0, 1, v.2, v.3, v.4 + (t - b.1[v.0]).max(0.0));
        }
        for (i, f) in self.freight.iter().enumerate() {
            if !s.2[i] && t + 1e-10 >= f.1 {
                offers.push((format!("freight:{}", f.0), f.2, f.2 * t));
                s.2[i] = true;
            }
        }
        for (i, c) in self.cars.iter().enumerate() {
            if !s.4[i] && t + 1e-10 >= c.1 {
                offers.push((format!("car:{}", c.0), c.2, c.2 * t));
                s.4[i] = true;
            }
        }
        self.pending = Some((t, s));
        Ok(offers)
    }
    fn finish(&mut self, end: f64, events: Vec<Sink>) -> PyResult<()> {
        let (t, mut s) = self
            .pending
            .clone()
            .ok_or_else(|| bad("native service finish without prepare"))?;
        if !end.is_finite()
            || end <= t
            || events
                .iter()
                .any(|e| !nonnegative([e.1, e.2]) || e.2 > end + 1e-8)
        {
            return Err(bad("invalid native service sink/clock"));
        }
        let mut sink_mass: HashMap<&str, Vec<f64>> = HashMap::new();
        for e in &events {
            sink_mass.entry(&e.0).or_default().push(e.1);
        }
        for (i, b) in self.buses.iter().enumerate() {
            let v = s.0[i];
            if v.1 != 1 {
                continue;
            }
            let tag = format!("bus:{}:{}", b.0, v.0);
            let mass = v.3 + fsum(sink_mass.get(tag.as_str()).into_iter().flatten().copied());
            if mass < 1.0 - 1e-9 {
                s.0[i].3 = mass;
                continue;
            }
            let stop = v.0 + 1;
            for &k in &self.people_by_run[i] {
                let x = &mut s.1[k];
                if self.people[k].2 == stop {
                    x.2 += x.1;
                    x.4 += x.1 * end;
                    x.1 = 0.0;
                }
            }
            s.0[i] = (
                stop,
                if stop == b.1.len() { 2 } else { 0 },
                end + b.3,
                0.0,
                v.4,
            );
        }
        for (i, f) in self.freight.iter().enumerate() {
            let tag = format!("freight:{}", f.0);
            s.3[i] += fsum(sink_mass.get(tag.as_str()).into_iter().flatten().copied());
        }
        self.validate(&s)?;
        self.state = s;
        self.pending = None;
        Ok(())
    }
}

fn fraction(profile: &Profile, t: f64) -> f64 {
    fsum(
        profile
            .iter()
            .map(|w| w.2 * (t.min(w.1) - 0.0_f64.max(w.0)).max(0.0) / (w.1 - w.0)),
    )
}
fn birth_between(profile: &Profile, lo: f64, hi: f64) -> f64 {
    let mut windows = profile.clone();
    windows.sort_by(|a, b| a.0.total_cmp(&b.0));
    let (mut total, mut moment) = (0.0, 0.0);
    for w in windows {
        let a = lo.max(total);
        let b = hi.min(total + w.2);
        if b > a {
            let x = w.0 + (a - total) * (w.1 - w.0) / w.2;
            let y = w.0 + (b - total) * (w.1 - w.0) / w.2;
            moment += (b - a) * (x + y) / 2.0;
        }
        total += w.2;
    }
    moment / (hi - lo)
}
fn eligible(legs: &[JourneyLeg], s: &Journey, i: usize) -> f64 {
    match legs[i].2 {
        None => 1.0,
        Some(parent) if parent >= legs.len() => 0.0,
        Some(parent) => fsum(
            s.6[parent]
                .iter()
                .filter(|r| r.0 + legs[i].3 <= s.0)
                .map(|r| r.1),
        ),
    }
}
fn valid_law(law: &Law) -> bool {
    !law.is_empty()
        && law.iter().all(|w| nonnegative([w.0, w.1]) && w.1 > 0.0)
        && (fsum(law.iter().map(|w| w.1)) - 1.0).abs() <= 1e-12
}
#[pyclass]
pub struct NativeJourneyCore {
    legs: Vec<JourneyLeg>,
    bus: Vec<BusMeta>,
    freight: Vec<FreightMeta>,
    route_indices: HashMap<String, usize>,
    budget: usize,
    state: Journey,
    pending: Option<Journey>,
    tick_times_s: Vec<f64>,
    peak_records: usize,
}
impl NativeJourneyCore {
    fn validate(&self, s: &Journey) -> PyResult<()> {
        let n = self.legs.len();
        if !nonnegative([s.0])
            || s.4.len() != n
            || s.5.len() != n
            || s.6.len() != n
            || s.7.len() != n
        {
            return Err(bad("native journey snapshot shape/clock differs"));
        }
        for i in 0..n {
            let l = &self.legs[i];
            let tol = 1e-9 * l.1.max(1.0);
            if !nonnegative([s.4[i], s.5[i], s.7[i]])
                || s.5[i] > s.4[i] + tol
                || s.4[i] > l.1 * fraction(&l.4, s.0) + tol
                || s.6[i]
                    .iter()
                    .any(|r| !nonnegative([r.0, r.1]) || r.0 > s.0 || r.1 <= 0.0)
                || (fsum(s.6[i].iter().map(|r| r.1)) * l.1 - s.5[i]).abs() > tol
                || s.4[i] > l.1 * eligible(&self.legs, s, i) + tol
            {
                return Err(bad(
                    "native journey conservation/receipt/eligibility failure",
                ));
            }
        }
        for stage in [&s.1, &s.2, &s.3] {
            if stage.iter().any(|a| {
                a.0 >= n || !nonnegative([a.1, a.2, a.3]) || a.1 <= 0.0 || a.2 > s.0 + 1e-8
            }) {
                return Err(bad("invalid native access stage"));
            }
        }
        let records = s.1.len() + s.2.len() + s.3.len() + s.6.iter().map(Vec::len).sum::<usize>();
        if records > self.budget {
            return Err(PyMemoryError::new_err("joint journey record budget"));
        }
        Ok(())
    }
}

/// Coupled numerical loop: one mutable owner of road, services and journey.
/// The three owners commit one complete interval together. A failure rolls all
/// three back to the previous complete interval, not to the start of the call.
#[pyfunction]
pub fn advance_native_joint(
    py: Python<'_>,
    mut road: PyRefMut<'_, V1Road>,
    mut service: PyRefMut<'_, NativeServiceCore>,
    mut journey: PyRefMut<'_, NativeJourneyCore>,
    tags: Vec<String>,
    count: usize,
    step_s: f64,
) -> PyResult<usize> {
    if !step_s.is_finite()
        || step_s <= 0.0
        || service.pending.is_some()
        || journey.pending.is_some()
    {
        return Err(bad("invalid native coupled step or pending transition"));
    }
    let tag_indices: HashMap<String, usize> = tags
        .iter()
        .enumerate()
        .map(|(i, t)| (t.clone(), i))
        .collect();
    if tag_indices.len() != tags.len() || road.owned_time() != journey.state.0 {
        return Err(bad("native coupled route labels or clocks differ"));
    }
    let road = &mut *road;
    let service = &mut *service;
    let journey = &mut *journey;
    py.allow_threads(move || {
        // Per-call observations, bounded by this requested interval count.
        // They are diagnostics, not part of a physical checkpoint.
        journey.tick_times_s = Vec::new();
        journey.peak_records = 0;
        journey.tick_times_s.try_reserve(count).map_err(|_| {
            PyMemoryError::new_err("native tick metric allocation exceeds available memory")
        })?;
        for _ in 0..count {
            let started = Instant::now();
            let road_before = road.checkpoint();
            let service_before = service.state.clone();
            let journey_before = journey.state.clone();
            let result = (|| -> PyResult<()> {
                let t = road.owned_time();
                let (mut offers, eligible) = journey.prepare()?;
                offers.extend(service.prepare(t, eligible)?);
                let mut physical = Vec::with_capacity(offers.len());
                for (tag, mass, birth) in offers {
                    let index = *tag_indices
                        .get(&tag)
                        .ok_or_else(|| bad("native joint offer has no physical route"))?;
                    physical.push((index, mass, birth, None, None));
                }
                let events = road.owned_step(step_s, physical)?;
                let mut sinks = Vec::new();
                for e in &events {
                    if e.2.is_none() {
                        let tag = tags
                            .get(e.0)
                            .ok_or_else(|| bad("native road event route index differs"))?;
                        sinks.push((tag.clone(), e.3, e.5));
                    }
                }
                let end = road.owned_time();
                service.finish(end, sinks.clone())?;
                journey.finish(
                    end,
                    sinks,
                    service_before.1.clone(),
                    service.state.1.clone(),
                    service_before.2.clone(),
                    service.state.2.clone(),
                    service_before.3.clone(),
                    service.state.3.clone(),
                )?;
                service.last_events = events;
                Ok(())
            })();
            if let Err(error) = result {
                road.rollback(road_before);
                service.state = service_before;
                service.pending = None;
                journey.state = journey_before;
                journey.pending = None;
                return Err(error);
            }
            let s = &journey.state;
            let records = road.owned_record_count()
                + s.1.len()
                + s.2.len()
                + s.3.len()
                + s.6.iter().map(Vec::len).sum::<usize>();
            journey.peak_records = journey.peak_records.max(records);
            journey.tick_times_s.push(started.elapsed().as_secs_f64());
        }
        Ok(count)
    })
}
#[pymethods]
impl NativeJourneyCore {
    #[new]
    fn new(
        legs: Vec<JourneyLeg>,
        bus: Vec<BusMeta>,
        freight: Vec<FreightMeta>,
        record_budget: usize,
    ) -> PyResult<Self> {
        if record_budget == 0 {
            return Err(bad("positive native journey record budget required"));
        }
        let mut ids = HashSet::new();
        for l in &legs {
            if l.0.is_empty()
                || !ids.insert(&l.0)
                || !nonnegative([l.1, l.3])
                || l.5 > 2
                || l.2.is_some_and(|i| i > legs.len())
                || l.4.is_empty()
                || l.4.iter().any(|w| {
                    !nonnegative([w.0, w.1, w.2]) || w.0 >= w.1 || w.1 > 86400.0 || w.2 == 0.0
                })
                || (fsum(l.4.iter().map(|w| w.2)) - 1.0).abs() > 1e-12
                || (l.5 != 0 && (!valid_law(&l.6) || !valid_law(&l.7)))
            {
                return Err(bad("invalid native journey leg"));
            }
            let mut windows = l.4.clone();
            windows.sort_by(|a, b| a.0.total_cmp(&b.0));
            if windows.windows(2).any(|w| w[0].1 > w[1].0) {
                return Err(bad("overlapping native departure windows"));
            }
        }
        for b in &bus {
            if b.0 >= legs.len()
                || !nonnegative([b.1, b.2, b.3, b.4])
                || b.1 == 0.0
                || b.2 == 0.0
                || b.4 > 1.0 + 1e-12
                || !valid_law(&b.5)
            {
                return Err(bad("invalid native bus journey mapping"));
            }
        }
        for f in &freight {
            if f.0 >= legs.len() || !nonnegative([f.1, f.2]) || f.1 == 0.0 || !valid_law(&f.3) {
                return Err(bad("invalid native freight journey mapping"));
            }
        }
        let n = legs.len();
        let route_indices = legs
            .iter()
            .enumerate()
            .filter(|(_, l)| l.5 == 1)
            .map(|(i, l)| (l.0.clone(), i))
            .collect();
        Ok(Self {
            legs,
            bus,
            freight,
            route_indices,
            budget: record_budget,
            state: (
                0.0,
                vec![],
                vec![],
                vec![],
                vec![0.0; n],
                vec![0.0; n],
                vec![vec![]; n],
                vec![0.0; n],
            ),
            pending: None,
            tick_times_s: Vec::new(),
            peak_records: 0,
        })
    }
    fn snapshot(&self) -> Journey {
        self.state.clone()
    }
    fn advance_metrics(&self) -> (Vec<f64>, usize) {
        (self.tick_times_s.clone(), self.peak_records)
    }
    fn restore(&mut self, state: Journey) -> PyResult<()> {
        self.validate(&state)?;
        self.state = state;
        self.pending = None;
        Ok(())
    }
    fn abort(&mut self) {
        self.pending = None;
    }
    fn prepare(&mut self) -> PyResult<(Vec<Offer>, Vec<bool>)> {
        if self.pending.is_some() {
            return Err(bad("native journey already prepared"));
        }
        let t = self.state.0;
        let mut s = self.state.clone();
        for (i, l) in self.legs.iter().enumerate() {
            if l.5 == 0 || l.1 == 0.0 {
                continue;
            }
            let lo = s.4[i] / l.1;
            let hi = fraction(&l.4, t).min(eligible(&self.legs, &self.state, i));
            if hi <= lo {
                continue;
            }
            let mass = l.1 * (hi - lo);
            let born = birth_between(&l.4, lo, hi);
            s.4[i] += mass;
            s.7[i] += mass * born;
            let hold = if l.2.is_some() { t - born } else { 0.0 };
            let target = if l.5 == 2 { &mut s.3 } else { &mut s.1 };
            target.extend(l.6.iter().map(|w| (i, mass * w.1, born, w.0 + hold)));
        }
        let mut offers = Vec::new();
        s.1.retain(|a| {
            if a.2 + a.3 <= t + 1e-10 {
                offers.push((self.legs[a.0].0.clone(), a.1, a.1 * a.2));
                false
            } else {
                true
            }
        });
        let allow = self
            .bus
            .iter()
            .map(|b| {
                self.legs[b.0].2.is_none() || eligible(&self.legs, &self.state, b.0) + 1e-10 >= b.4
            })
            .collect();
        self.pending = Some(s);
        Ok((offers, allow))
    }
    fn finish(
        &mut self,
        end: f64,
        events: Vec<Sink>,
        before_people: Vec<People>,
        after_people: Vec<People>,
        before_freight: Vec<bool>,
        after_freight: Vec<bool>,
        before_completed: Vec<f64>,
        after_completed: Vec<f64>,
    ) -> PyResult<()> {
        let mut s = self
            .pending
            .clone()
            .ok_or_else(|| bad("native journey finish without prepare"))?;
        let t = s.0;
        if !end.is_finite()
            || end <= t
            || before_people.len() != self.bus.len()
            || after_people.len() != self.bus.len()
            || before_freight.len() != self.freight.len()
            || after_freight.len() != self.freight.len()
            || before_completed.len() != self.freight.len()
            || after_completed.len() != self.freight.len()
        {
            return Err(bad("invalid native journey service shape/clock"));
        }
        for e in events {
            if !nonnegative([e.1, e.2]) || e.2 > end + 1e-8 {
                return Err(bad("invalid native journey road sink"));
            }
            if let Some(&i) = self.route_indices.get(&e.0) {
                s.2.extend(self.legs[i].7.iter().map(|w| (i, e.1 * w.1, e.2, w.0)));
            }
        }
        for (k, b) in self.bus.iter().enumerate() {
            let before = before_people[k];
            let after = after_people[k];
            if !nonnegative([before.0, before.1, before.2, after.0, after.1, after.2]) {
                return Err(bad("invalid native journey passenger update"));
            }
            let boarded = (after.1 + after.2) - (before.1 + before.2);
            let arrived = after.2 - before.2;
            let factor = self.legs[b.0].1 / b.1;
            if boarded < 0.0 || arrived < 0.0 {
                return Err(bad("native passenger totals decreased"));
            }
            s.4[b.0] += boarded * factor;
            s.7[b.0] += boarded * factor * b.3 / b.2;
            if arrived != 0.0 {
                s.2.extend(b.5.iter().map(|w| (b.0, arrived * factor * w.1, end, w.0)));
            }
        }
        for (k, f) in self.freight.iter().enumerate() {
            if before_freight[k] && !after_freight[k] {
                return Err(bad("native freight release reversed"));
            }
            if after_freight[k] && !before_freight[k] {
                s.4[f.0] += f.1;
                s.7[f.0] += f.2;
            }
            let arrival = after_completed[k] - before_completed[k];
            if !nonnegative([arrival]) {
                return Err(bad("native freight arrival decreased"));
            }
            if arrival != 0.0 {
                s.2.extend(f.3.iter().map(|w| (f.0, arrival * w.1, end, w.0)));
            }
        }
        for stage in [&mut s.2, &mut s.3] {
            stage.retain(|a| {
                if a.2 + a.3 <= end + 1e-10 {
                    s.5[a.0] += a.1;
                    s.6[a.0].push((t.max(a.2 + a.3), a.1 / self.legs[a.0].1));
                    false
                } else {
                    true
                }
            });
        }
        s.0 = end;
        self.validate(&s)?;
        self.state = s;
        self.pending = None;
        Ok(())
    }
}
