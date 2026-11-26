//! Original C01 medium/slow orchestration on native T04. Medium decisions are
//! proposals; the Python reference never rewrites an occupied packet. No
//! route-total observation is reinterpreted as a link-entry observation.
use crate::{
    causal::{Channel, InfoState, Information, Observation, Prior, Report},
    causal_routing::{
        Boundary, Decision, Link, Preference, Routing, RoutingWire, State as RouteState,
    },
    core_error::{CoreError, CoreResult},
    frozen_city::hash,
    lagged_growth::{Accessibility, Block, Entry, Growth, GrowthState, Site},
};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
fn bad(s: impl Into<String>) -> CoreError {
    CoreError::value(s)
}
fn digest<T: Serialize>(x: &T) -> CoreResult<String> {
    serde_json::to_vec(x)
        .map(|b| hash(&b))
        .map_err(|e| bad(e.to_string()))
}
fn aligned(x: f64, step: f64) -> bool {
    x.is_finite() && x >= 0. && (x / step - (x / step).round()).abs() < 1e-8
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct GrowthConfig {
    pub blocks: Vec<Block>,
    pub entries: Vec<Entry>,
    pub sites: Vec<Site>,
    pub construction_budget_m: f64,
    pub max_access_s: f64,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Config {
    pub medium_s: f64,
    pub slow_s: f64,
    pub record_budget: usize,
    pub origin: String,
    pub destination: String,
    pub observer_xy: [f64; 2],
    pub preference: Preference,
    pub priors: Vec<Prior>,
    pub channels: Vec<Channel>,
    pub k: usize,
    pub expansion_budget: usize,
    pub frontier_budget: usize,
    pub cache_limit: usize,
    #[serde(default)]
    pub growth: Option<GrowthConfig>,
}
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct Inputs {
    #[serde(default)]
    pub reports: Vec<Report>,
    #[serde(default)]
    pub growth: Option<Publication>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Publication {
    pub snapshot: Accessibility,
    pub increment: u64,
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Snapshot {
    pub stamp_s: f64,
    pub completed_veh: f64,
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct PhaseEvent {
    pub time_s: f64,
    pub phase: String,
    pub input_stamp_s: f64,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Wire {
    pub model_id: String,
    pub city_identity: String,
    pub demand_identity: String,
    pub traffic_identity: String,
    pub time_s: f64,
    pub info_time_s: f64,
    pub information_reports: Vec<Report>,
    routing: RoutingWire,
    pub accessibility: Snapshot,
    pub slow_input: Snapshot,
    pub journal: Vec<PhaseEvent>,
    pub completed_costs: Vec<Observation>,
    pub decisions: Vec<Decision>,
    pub next_medium_s: f64,
    pub next_slow_s: f64,
    pub observation_cursor_s: f64,
    pub growth_state: Option<GrowthState>,
    pub growth_snapshot: Option<Accessibility>,
    pub growth_increment: u64,
}
pub(crate) struct World {
    pub wire: Wire,
    information: InfoState,
    routing: RouteState,
}
pub(crate) struct Runtime {
    pub id: String,
    city: String,
    schedule: String,
    traffic: String,
    step: f64,
    cfg: Config,
    information: Information,
    routing: Routing,
    growth: Option<Growth>,
}
impl Runtime {
    pub fn new(
        city: &str,
        schedule: &str,
        traffic: &str,
        step: f64,
        links: Vec<Link>,
        turns: Vec<(String, String)>,
        cfg: Config,
    ) -> CoreResult<Self> {
        if city.is_empty()
            || schedule.is_empty()
            || traffic.is_empty()
            || !step.is_finite()
            || step <= 0.
            || cfg.medium_s <= 0.
            || cfg.slow_s <= 0.
            || !aligned(cfg.medium_s, step)
            || !aligned(cfg.slow_s, step)
            || cfg.record_budget == 0
            || cfg.record_budget > 20000
            || cfg.origin.is_empty()
            || cfg.destination.is_empty()
            || cfg.observer_xy.iter().any(|x| !x.is_finite())
            || cfg.cache_limit == 0
            || cfg.cache_limit > 32
            || cfg.frontier_budget == 0
            || cfg.frontier_budget > 20000
            || cfg.expansion_budget > 20000
        {
            return Err(bad("invalid native phase configuration"));
        }
        // JSON phase receipts carry finite observation costs. Infinity in the
        // internal destination potential is preserved separately by u64 bits.
        if cfg.priors.iter().any(|p| !p.seconds.is_finite())
            || cfg.channels.iter().any(|c| !c.radius_m.is_finite())
        {
            return Err(bad(
                "native phase wire requires finite declared costs/radii",
            ));
        }
        let graph_budget = links
            .len()
            .checked_add(turns.len())
            .ok_or_else(|| bad("graph budget"))?;
        if graph_budget > 100000 || cfg.priors.len() > 20000 || cfg.channels.len() > 128 {
            return Err(CoreError::resource("phase declaration domain"));
        }
        let information =
            Information::new(cfg.priors.clone(), cfg.channels.clone(), cfg.record_budget)?;
        let routing = Routing::new(
            links,
            turns,
            city,
            cfg.k,
            cfg.expansion_budget,
            cfg.frontier_budget,
            graph_budget,
            cfg.cache_limit,
        )?;
        let growth = cfg
            .growth
            .as_ref()
            .map(|g| {
                Growth::new(
                    city,
                    g.blocks.clone(),
                    g.entries.clone(),
                    g.sites.clone(),
                    g.construction_budget_m,
                    cfg.slow_s,
                    g.max_access_s,
                )
            })
            .transpose()?;
        let id = digest(&(
            "C01_native_phase_v1",
            city,
            schedule,
            traffic,
            step,
            &cfg,
            &information.id,
            &routing.graph_id,
            growth.as_ref().map(|g| &g.id),
        ))?;
        Ok(Self {
            id,
            city: city.into(),
            schedule: schedule.into(),
            traffic: traffic.into(),
            step,
            cfg,
            information,
            routing,
            growth,
        })
    }
    pub fn initial(&self) -> CoreResult<World> {
        let information = self.information.initial();
        let routing = self.routing.initial();
        let snap = Snapshot {
            stamp_s: 0.,
            completed_veh: 0.,
        };
        let wire = Wire {
            model_id: self.id.clone(),
            city_identity: self.city.clone(),
            demand_identity: self.schedule.clone(),
            traffic_identity: self.traffic.clone(),
            time_s: 0.,
            info_time_s: 0.,
            information_reports: vec![],
            routing: self.routing.export_state(&routing)?,
            accessibility: snap.clone(),
            slow_input: snap,
            journal: vec![],
            completed_costs: vec![],
            decisions: vec![],
            next_medium_s: self.cfg.medium_s,
            next_slow_s: self.cfg.slow_s,
            observation_cursor_s: 0.,
            growth_state: self.growth.as_ref().map(Growth::initial),
            growth_snapshot: None,
            growth_increment: 0,
        };
        Ok(World {
            wire,
            information,
            routing,
        })
    }
    fn check_wire(&self, w: &Wire, physical_time: f64) -> CoreResult<()> {
        if w.model_id != self.id
            || w.city_identity != self.city
            || w.demand_identity != self.schedule
            || w.traffic_identity != self.traffic
            || w.time_s != physical_time
            || !aligned(w.time_s, self.step)
            || !aligned(w.info_time_s, self.step)
            || w.info_time_s > w.time_s
            || !aligned(w.next_medium_s, self.step)
            || w.next_medium_s <= w.time_s
            || w.next_medium_s - w.time_s > self.cfg.medium_s
            || !aligned(w.next_slow_s, self.step)
            || w.next_slow_s <= w.time_s
            || w.next_slow_s - w.time_s > self.cfg.slow_s
            || w.observation_cursor_s != w.accessibility.stamp_s
            || w.observation_cursor_s > w.time_s
            || w.info_time_s != w.observation_cursor_s
            || w.slow_input.stamp_s > w.accessibility.stamp_s
            || [w.accessibility.completed_veh, w.slow_input.completed_veh]
                .iter()
                .any(|x| !x.is_finite() || *x < 0.)
            || w.slow_input.completed_veh > w.accessibility.completed_veh
            || w.journal.windows(2).any(|s| s[0].time_s > s[1].time_s)
            || w.journal.iter().any(|e| {
                !matches!(e.phase.as_str(), "medium" | "slow")
                    || e.time_s > w.time_s
                    || e.input_stamp_s >= e.time_s
            })
            || w.decisions.len() != w.journal.iter().filter(|x| x.phase == "medium").count()
            || w.completed_costs.iter().any(|o| {
                o.validate().is_err()
                    || o.stamp_s > w.observation_cursor_s
                    || !o.seconds.is_finite()
            })
        {
            return Err(bad("invalid native world identity/clock/history"));
        }
        self.count(w)?;
        match (&self.growth, &w.growth_state) {
            (Some(g), Some(s)) => {
                g.check(s)?;
                if s.epoch_s > w.time_s {
                    return Err(bad("growth future clock"));
                }
            }
            (None, None) if w.growth_snapshot.is_none() && w.growth_increment == 0 => {}
            _ => return Err(bad("world growth binding")),
        }
        Ok(())
    }
    fn count(&self, w: &Wire) -> CoreResult<()> {
        let n = w
            .journal
            .len()
            .saturating_add(w.completed_costs.len())
            .saturating_add(w.decisions.len());
        if n > self.cfg.record_budget || w.information_reports.len() > self.cfg.record_budget {
            return Err(CoreError::resource("C01 world observation/journal budget"));
        }
        Ok(())
    }
    pub fn restore(&self, w: Wire, physical_time: f64) -> CoreResult<World> {
        self.check_wire(&w, physical_time)?;
        if w.information_reports
            .iter()
            .any(|r| !r.observation.seconds.is_finite())
        {
            return Err(bad("nonfinite report wire"));
        }
        let information = self.information.advance(
            &self.information.initial(),
            w.info_time_s,
            &w.information_reports,
        )?;
        if information.reports() != w.information_reports.as_slice() {
            return Err(bad("information wire canonical order"));
        }
        let routing = self.routing.import_state(&w.routing)?;
        Ok(World {
            wire: w,
            information,
            routing,
        })
    }
    pub fn publish(&self, w: &mut World, p: Publication) -> CoreResult<()> {
        let g = self.growth.as_ref().ok_or_else(|| bad("no growth owner"))?;
        let s = w
            .wire
            .growth_state
            .as_ref()
            .ok_or_else(|| bad("no growth state"))?;
        if w.wire.growth_increment != 0
            || p.snapshot.city_identity != g.materialized_identity(s)?
            || !p.snapshot.stamp_s.is_finite()
            || p.snapshot.stamp_s < 0.
            || p.snapshot.stamp_s > w.wire.time_s
            || p.snapshot
                .costs
                .iter()
                .any(|(_, x)| !x.is_finite() || *x < 0.)
        {
            return Err(bad("invalid frozen growth publication"));
        }
        w.wire.growth_snapshot = Some(p.snapshot);
        w.wire.growth_increment = p.increment;
        Ok(())
    }
    pub fn validate_input(&self, w: &World, end: f64, inputs: &Inputs) -> CoreResult<()> {
        if !aligned(end, self.step)
            || end < w.wire.time_s
            || inputs.reports.len() > self.cfg.record_budget
            || inputs.reports.iter().any(|r| {
                r.observation.validate().is_err()
                    || !r.observation.seconds.is_finite()
                    || r.observation.stamp_s > end
            })
        {
            return Err(bad("future/invalid phase reports or horizon"));
        }
        Ok(())
    }
    pub fn boundary(&self, w: &World, end: f64) -> f64 {
        end.min(w.wire.next_medium_s)
            .min(w.wire.next_slow_s)
            .min(w.wire.time_s + 900.)
    }
    pub fn medium(&self, w: &World, t: f64) -> bool {
        t == w.wire.next_medium_s
    }
    pub fn transition(
        &self,
        w: &mut World,
        t: f64,
        completed_veh: f64,
        mut observed: Vec<Observation>,
        pending: &mut Vec<Report>,
    ) -> CoreResult<()> {
        if !aligned(t, self.step)
            || t <= w.wire.time_s
            || t > self.boundary(w, t)
            || !completed_veh.is_finite()
            || completed_veh < w.wire.accessibility.completed_veh
        {
            return Err(bad("invalid phase sample clock/ledger"));
        }
        let previous = w.wire.accessibility.clone();
        if t == w.wire.next_medium_s {
            if observed.iter().any(|o| {
                o.validate().is_err()
                    || o.stamp_s != t
                    || o.key.kind != "route"
                    || o.end_s <= w.wire.observation_cursor_s
                    || o.version != self.traffic
                    || !o.seconds.is_finite()
            }) {
                return Err(bad("invalid completed medium sample"));
            }
            let added = observed
                .len()
                .saturating_add(2)
                .saturating_add(usize::from(t == w.wire.next_slow_s));
            if w.wire
                .journal
                .len()
                .saturating_add(w.wire.completed_costs.len())
                .saturating_add(w.wire.decisions.len())
                .saturating_add(added)
                > self.cfg.record_budget
            {
                return Err(CoreError::resource("C01 world observation/journal budget"));
            }
            let (incoming, later): (Vec<_>, Vec<_>) = std::mem::take(pending)
                .into_iter()
                .partition(|r| r.observation.stamp_s <= t);
            let info = self.information.advance(&w.information, t, &incoming)?;
            let delivered = self
                .information
                .observe(&info, self.cfg.observer_xy, "origin")?;
            let (route, decision) = self.routing.decide(
                &w.routing,
                &delivered,
                &Boundary {
                    time_s: t,
                    node: self.cfg.origin.clone(),
                    incoming: None,
                },
                &self.cfg.preference,
                &self.cfg.destination,
                None,
                &[],
            )?;
            *pending = later;
            w.information = info;
            w.routing = route;
            w.wire.accessibility = Snapshot {
                stamp_s: t,
                completed_veh,
            };
            w.wire.info_time_s = t;
            w.wire.observation_cursor_s = t;
            w.wire.next_medium_s += self.cfg.medium_s;
            observed.sort_by(|a, b| a.key.cmp(&b.key));
            w.wire.completed_costs.extend(observed);
            w.wire.decisions.push(decision);
            w.wire.journal.push(PhaseEvent {
                time_s: t,
                phase: "medium".into(),
                input_stamp_s: previous.stamp_s,
            });
        } else if !observed.is_empty() {
            return Err(bad("observations outside medium boundary"));
        }
        if t == w.wire.next_slow_s {
            if let Some(g) = &self.growth {
                let input = w
                    .wire
                    .growth_snapshot
                    .as_ref()
                    .ok_or_else(|| bad("completed spatial growth input required"))?;
                let state = w
                    .wire
                    .growth_state
                    .as_ref()
                    .ok_or_else(|| bad("growth state absent"))?;
                w.wire.growth_state =
                    Some(g.advance(state, input, t, w.wire.growth_increment, &[])?);
                w.wire.growth_increment = 0;
            }
            w.wire.slow_input = previous.clone();
            w.wire.next_slow_s += self.cfg.slow_s;
            w.wire.journal.push(PhaseEvent {
                time_s: t,
                phase: "slow".into(),
                input_stamp_s: previous.stamp_s,
            });
        }
        w.wire.time_s = t;
        self.count(&w.wire)?;
        Ok(())
    }
    pub fn finalize(&self, mut w: World, pending: &[Report]) -> CoreResult<Wire> {
        if !pending.is_empty() {
            return Err(bad("reports require eligible medium boundary"));
        }
        w.wire.information_reports = w.information.reports().to_vec();
        w.wire.routing = self.routing.export_state(&w.routing)?;
        self.check_wire(&w.wire, w.wire.time_s)?;
        Ok(w.wire)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use crate::causal::Key;
    fn cfg() -> Config {
        Config {
            medium_s: 5.,
            slow_s: 10.,
            record_budget: 50,
            origin: "a".into(),
            destination: "b".into(),
            observer_xy: [0., 0.],
            preference: Preference {
                class: "car".into(),
                purpose: "work".into(),
                time_weight: 1.,
                distance_s_per_m: 0.,
                money_s_per_unit: 0.,
                logit_scale_s: 30.,
                path_size_beta: 1.,
            },
            priors: vec![Prior {
                key: Key {
                    kind: "link".into(),
                    id: "ab".into(),
                    class: "car".into(),
                },
                seconds: 10.,
                version: "prior".into(),
                measure: "link mean".into(),
            }],
            channels: vec![],
            k: 1,
            expansion_budget: 100,
            frontier_budget: 100,
            cache_limit: 2,
            growth: None,
        }
    }
    fn model(c: Config) -> Runtime {
        Runtime::new(
            "city",
            "schedule",
            "traffic",
            1.,
            vec![Link {
                id: "ab".into(),
                tail: "a".into(),
                head: "b".into(),
                length_m: 100.,
                toll_units: 0.,
            }],
            vec![],
            c,
        )
        .unwrap()
    }
    #[test]
    fn coincident_clocks_and_wire_replay() {
        let m = model(cfg());
        let mut s = m.initial().unwrap();
        let mut p = vec![];
        m.transition(&mut s, 5., 0., vec![], &mut p).unwrap();
        m.transition(&mut s, 10., 1., vec![], &mut p).unwrap();
        let w = m.finalize(s, &p).unwrap();
        assert_eq!(w.accessibility.stamp_s, 10.);
        assert_eq!(w.slow_input.stamp_s, 5.);
        assert_eq!(
            w.journal
                .iter()
                .filter(|e| e.time_s == 10.)
                .map(|e| e.phase.as_str())
                .collect::<Vec<_>>(),
            ["medium", "slow"]
        );
        let bytes = serde_json::to_vec(&w).unwrap();
        let r: Wire = serde_json::from_slice(&bytes).unwrap();
        let mut resumed = m.restore(r, 10.).unwrap();
        m.transition(&mut resumed, 15., 1., vec![], &mut p).unwrap();
        let resumed = m.finalize(resumed, &p).unwrap();
        let mut s = m.initial().unwrap();
        for t in [5., 10., 15.] {
            m.transition(&mut s, t, if t >= 10. { 1. } else { 0. }, vec![], &mut p)
                .unwrap()
        }
        assert_eq!(
            serde_json::to_vec(&resumed).unwrap(),
            serde_json::to_vec(&m.finalize(s, &p).unwrap()).unwrap()
        );
    }
    #[test]
    fn budget_and_foreign_clock_refused() {
        let mut c = cfg();
        c.record_budget = 1;
        let m = model(c);
        let mut s = m.initial().unwrap();
        assert!(m.transition(&mut s, 5., 0., vec![], &mut vec![]).is_err());
        assert_eq!(s.wire.time_s, 0.);
        let m = model(cfg());
        let w = m.finalize(m.initial().unwrap(), &[]).unwrap();
        assert!(m.restore(w, 1.).is_err());
    }
}
