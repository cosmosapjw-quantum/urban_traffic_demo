//! Persistent exact-identity calendar storage. No transport evolution is implied.
#[cfg(feature="python-extension")]
use pyo3::prelude::*;
use crate::core_error::{CoreError,CoreResult};
use std::collections::{HashMap, HashSet};

const NONE: u64 = u64::MAX;
const MASK: u64 = (1 << 62) - 1;
type Row = (
    String,
    Option<String>,
    Option<String>,
    Vec<u32>,
    (f64, f64, f64),
    f64,
);
// All inputs scale with marginal support. Cartesian OD pairs are generated here.
type HomeFactor = (u32, f64, u32); // activity label, mass, stationary cohort ID gaps
type TargetFactor = (u32, u32, u32, f64, f64, bool, Vec<(u32, f64)>);
// purpose, outward/return profiles, total, support, external, destinations
type ModeFactor = (u32, u32, f64, f64, bool); // mode/class labels, share, occupancy, noncar
type FreightFactor = (String, u32, f64); // exact ID, destination label, cargo kg

fn visit_factorized(
    homes: &[HomeFactor],
    targets: &[TargetFactor],
    modes: &[ModeFactor],
    laws: &HashMap<(u32, u32, u32), u32>,
    freight: &[FreightFactor],
    config: (f64, f64, f64, f64, f64),
    labels: &[u32],
    freight_profile: u32,
    mut emit: impl FnMut(Leg) -> CoreResult<()>,
) -> CoreResult<()> {
    let (population, service_fraction, external_fraction, dwell, freight_payload) = config;
    let mut cohort = 0_u64;
    let mut row = 0_u32;
    for &(home, home_mass, stationary) in homes {
        let ratio = home_mass / population;
        for (purpose, outward_profile, return_profile, total, support, external, destinations) in
            targets
        {
            if *total == 0.0 {
                continue;
            }
            for &(destination, destination_mass) in destinations {
                for &(mode, class, share, occupancy, noncar) in modes {
                    // Keep Python's explicit left-to-right operation order; no fast math.
                    let mass = if *external {
                        home_mass * service_fraction * external_fraction * share
                    } else {
                        total * ratio * destination_mass / support * share
                    };
                    if mass <= 0.0 {
                        continue;
                    }
                    if cohort > MASK || row > u32::MAX - 2 {
                        return Err(CoreError::value("factorized calendar index overflow"));
                    }
                    let amounts = [mass, if noncar { 0.0 } else { mass / occupancy }, 0.0];
                    let law = laws
                        .get(&(home, destination, *purpose))
                        .copied()
                        .unwrap_or(labels[0]);
                    let endpoint = if *external {
                        labels[4]
                    } else if law != labels[0] {
                        labels[3]
                    } else {
                        labels[2]
                    };
                    let outward = Leg {
                        id: (1 << 62) | cohort,
                        cohort,
                        parent: None,
                        metadata: [
                            home,
                            destination,
                            *purpose,
                            mode,
                            class,
                            *outward_profile,
                            law,
                            endpoint,
                        ],
                        amounts,
                        dwell: 0.0,
                        released: 0.0,
                        completed: 0.0,
                    };
                    let back = Leg {
                        id: (2 << 62) | cohort,
                        cohort,
                        parent: Some(row),
                        metadata: [
                            destination,
                            home,
                            labels[1],
                            mode,
                            class,
                            *return_profile,
                            law,
                            endpoint,
                        ],
                        amounts,
                        dwell,
                        released: 0.0,
                        completed: 0.0,
                    };
                    emit(outward)?;
                    emit(back)?;
                    row += 2;
                    cohort += 1;
                }
            }
        }
        cohort = cohort
            .checked_add(stationary as u64)
            .ok_or_else(|| CoreError::value("factorized cohort index overflow"))?;
    }
    for (i, (_, destination, cargo)) in freight.iter().enumerate() {
        if row == u32::MAX {
            return Err(CoreError::value("factorized calendar index overflow"));
        }
        emit(Leg {
            id: (3 << 62) | i as u64,
            cohort: NONE,
            parent: None,
            metadata: [
                labels[0],
                *destination,
                labels[5],
                labels[6],
                labels[7],
                freight_profile,
                labels[0],
                labels[4],
            ],
            amounts: [0.0, cargo / freight_payload, *cargo],
            dwell: 0.0,
            released: 0.0,
            completed: 0.0,
        })?;
        row += 1;
    }
    Ok(())
}
#[derive(Clone)]
pub(crate) struct Leg {
    pub(crate) id: u64,
    pub(crate) cohort: u64,
    pub(crate) parent: Option<u32>,
    pub(crate) metadata: [u32; 8], // origin,destination,purpose,mode,class,profile,law,endpoint kind
    pub(crate) amounts: [f64; 3],
    pub(crate) dwell: f64,
    pub(crate) released: f64,
    pub(crate) completed: f64,
}

fn sum(values: impl Iterator<Item = f64>) -> f64 {
    let (mut s, mut c) = (0.0_f64, 0.0_f64);
    for x in values {
        let t = s + x;
        if !t.is_finite() {
            return t;
        }
        c += if s.abs() >= x.abs() {
            (s - t) + x
        } else {
            (x - t) + s
        };
        s = t;
    }
    s + c
}

#[cfg_attr(feature="python-extension", pyclass)]
pub struct NativeCalendar {
    byte_budget: usize,
    city_identity: String,
    schedule_identity: String,
    amount_sums: [f64; 3],
    amount_corrections: [f64; 3],
    legs: Vec<Leg>,
    indices: HashMap<u64, u32>,
    texts: Vec<String>,
    text_indices: HashMap<String, u64>,
    labels: Vec<String>,
    label_indices: HashMap<String, u32>,
    profiles: Vec<Vec<(f64, f64, f64)>>,
    profile_indices: HashMap<Vec<(u64, u64, u64)>, u32>,
}

impl NativeCalendar {
    pub(crate) fn owned_legs(&self) -> &[Leg] {
        &self.legs
    }
    pub(crate) fn owned_labels(&self) -> &[String] {
        &self.labels
    }
    pub(crate) fn owned_profiles(&self) -> &[Vec<(f64, f64, f64)>] {
        &self.profiles
    }
    pub(crate) fn owned_binding(&self) -> (&str, &str) {
        (&self.city_identity, &self.schedule_identity)
    }
    pub(crate) fn owned_bytes(&self) -> usize {
        self.estimate(self.legs.len(), 0)
    }
    fn key_existing(&self, text: &str) -> Option<u64> {
        if let Some(s) = text.strip_prefix('c') {
            let (digits, tag) = if let Some(x) = s.strip_suffix(":out") {
                (x, 1)
            } else if let Some(x) = s.strip_suffix(":home") {
                (x, 2)
            } else {
                (s, 0)
            };
            if let Ok(n) = digits.parse::<u64>() {
                if n <= MASK && n.to_string() == digits {
                    return Some((tag << 62) | n);
                }
            }
        }
        self.text_indices.get(text).map(|i| (3 << 62) | i)
    }
    fn key(&mut self, text: &str) -> u64 {
        if let Some(k) = self.key_existing(text) {
            return k;
        }
        let i = self.texts.len() as u64;
        self.texts.push(text.to_owned());
        self.text_indices.insert(text.to_owned(), i);
        (3 << 62) | i
    }
    pub(crate) fn text(&self, k: u64) -> Option<String> {
        if k == NONE {
            return None;
        }
        let n = k & MASK;
        Some(match k >> 62 {
            0 => format!("c{n}"),
            1 => format!("c{n}:out"),
            2 => format!("c{n}:home"),
            _ => self.texts[n as usize].clone(),
        })
    }
    // Persistent-storage accounting, not a hard RSS bound. Python/FFI pages,
    // allocation transients and unrelated process memory require an outer bound.
    fn estimate(&self, n: usize, extra_text_bytes: usize) -> usize {
        n.saturating_mul(std::mem::size_of::<Leg>() + 64)
            .saturating_add(self.texts.iter().map(|s| s.len() * 2 + 128).sum::<usize>())
            .saturating_add(self.labels.iter().map(|s| s.len() * 2 + 128).sum::<usize>())
            .saturating_add(
                self.profiles
                    .iter()
                    .map(|p| p.len() * 64 + 128)
                    .sum::<usize>(),
            )
            .saturating_add(extra_text_bytes)
    }
    fn budget(&self, n: usize, extra: usize) -> CoreResult<()> {
        if self.estimate(n, extra) > self.byte_budget {
            Err(CoreError::resource(
                "native calendar byte budget exceeded; page not committed",
            ))
        } else {
            Ok(())
        }
    }
}

crate::optional_binding::optional_pymethods!(NativeCalendar,
    [
    #[new]
    #[pyo3(signature = (byte_budget, city_identity=String::new(), schedule_identity=String::new()))]
    ] {
    fn new(byte_budget: usize, city_identity: String, schedule_identity: String) -> CoreResult<Self> {
        if byte_budget == 0 {
            return Err(CoreError::value("positive byte budget required"));
        }
        Ok(Self {
            byte_budget,
            city_identity,
            schedule_identity,
            amount_sums: [0.0; 3],
            amount_corrections: [0.0; 3],
            legs: Vec::new(),
            indices: HashMap::new(),
            texts: Vec::new(),
            text_indices: HashMap::new(),
            labels: Vec::new(),
            label_indices: HashMap::new(),
            profiles: Vec::new(),
            profile_indices: HashMap::new(),
        })
    }
    }
    [

    ] {

    fn binding(&self) -> (String, String) {
        (self.city_identity.clone(), self.schedule_identity.clone())
    }
    }
    [

    ] {

    fn intern_label(&mut self, text: String) -> CoreResult<u32> {
        if let Some(i) = self.label_indices.get(&text) {
            return Ok(*i);
        }
        self.budget(self.legs.len(), text.len() * 2 + 128)?;
        let i = u32::try_from(self.labels.len())
            .map_err(|_| CoreError::value("label index overflow"))?;
        self.labels.push(text.clone());
        self.label_indices.insert(text, i);
        Ok(i)
    }
    }
    [

    ] {

    fn label(&self, index: usize) -> CoreResult<String> {
        self.labels
            .get(index)
            .cloned()
            .ok_or_else(|| CoreError::index("label index"))
    }
    }
    [

    ] {

    fn intern_profile(&mut self, windows: Vec<(f64, f64, f64)>) -> CoreResult<u32> {
        let total = sum(windows.iter().map(|w| w.2));
        if windows.is_empty()
            || windows.iter().any(|&(a, b, p)| {
                !a.is_finite()
                    || !b.is_finite()
                    || !p.is_finite()
                    || a < 0.0
                    || b > 86400.0
                    || a >= b
                    || p <= 0.0
            })
            || !total.is_finite()
            || (total - 1.0).abs() > 1e-12
        {
            return Err(CoreError::value(
                "finite normalized departure profile required",
            ));
        }
        let mut ordered = windows.clone();
        ordered.sort_by(|a, b| a.0.total_cmp(&b.0));
        if ordered.windows(2).any(|w| w[0].1 > w[1].0) {
            return Err(CoreError::value("overlapping departure windows"));
        }
        let key: Vec<_> = windows
            .iter()
            .map(|w| (w.0.to_bits(), w.1.to_bits(), w.2.to_bits()))
            .collect();
        if let Some(i) = self.profile_indices.get(&key) {
            return Ok(*i);
        }
        self.budget(self.legs.len(), windows.len() * 64 + 128)?;
        let i = self.profiles.len() as u32;
        self.profiles.push(windows);
        self.profile_indices.insert(key, i);
        Ok(i)
    }
    }
    [

    ] {

    fn profile(&self, index: usize) -> CoreResult<Vec<(f64, f64, f64)>> {
        self.profiles
            .get(index)
            .cloned()
            .ok_or_else(|| CoreError::index("profile index"))
    }
    }
    [

    ] {

    fn append(&mut self, rows: Vec<Row>) -> CoreResult<usize> {
        let next = self
            .legs
            .len()
            .checked_add(rows.len())
            .ok_or_else(|| CoreError::value("calendar index overflow"))?;
        if next >= u32::MAX as usize {
            return Err(CoreError::value("calendar index overflow"));
        }
        // Validate the whole page, including dependencies, before any leg/ID mutation.
        let mut seen = HashSet::new();
        let mut earlier: HashMap<&str, usize> = HashMap::new();
        let mut extra = 0;
        let mut sums = self.amount_sums;
        let mut corrections = self.amount_corrections;
        for (j, (id, cohort, parent, meta, amounts, dwell)) in rows.iter().enumerate() {
            if id.is_empty()
                || !seen.insert(id)
                || self
                    .key_existing(id)
                    .is_some_and(|k| self.indices.contains_key(&k))
            {
                return Err(CoreError::value("unique nonempty leg IDs required"));
            }
            if meta.len() != 8
                || meta[5] as usize >= self.profiles.len()
                || meta
                    .iter()
                    .enumerate()
                    .any(|(k, &v)| k != 5 && v as usize >= self.labels.len())
            {
                return Err(CoreError::value(
                    "registered metadata/profile required",
                ));
            }
            if [amounts.0, amounts.1, amounts.2, *dwell]
                .iter()
                .any(|v| !v.is_finite() || *v < 0.0)
            {
                return Err(CoreError::value(
                    "finite nonnegative amounts/dwell required",
                ));
            }
            for (i, x) in [amounts.0, amounts.1, amounts.2].into_iter().enumerate() {
                let t = sums[i] + x;
                if !t.is_finite() {
                    return Err(CoreError::value("calendar amount total overflow"));
                }
                corrections[i] += if sums[i].abs() >= x.abs() {
                    (sums[i] - t) + x
                } else {
                    (x - t) + sums[i]
                };
                sums[i] = t;
                if !(sums[i] + corrections[i]).is_finite() {
                    return Err(CoreError::value("calendar amount total overflow"));
                }
            }
            if let Some(p) = parent {
                let valid = if let Some(&i) = earlier.get(p.as_str()) {
                    let r = &rows[i];
                    r.2.is_none() && r.1 == *cohort && r.4 == *amounts
                } else if let Some(i) = self.key_existing(p).and_then(|k| self.indices.get(&k)) {
                    let r = &self.legs[*i as usize];
                    r.parent.is_none()
                        && self.text(r.cohort) == *cohort
                        && r.amounts == [amounts.0, amounts.1, amounts.2]
                } else {
                    false
                };
                if !valid {
                    return Err(CoreError::value(
                        "dependent return requires earlier outward with same cohort and amounts",
                    ));
                }
            }
            for s in [Some(id), cohort.as_ref()].into_iter().flatten() {
                if self.key_existing(s).is_none() {
                    extra += s.len() * 2 + 128;
                }
            }
            earlier.insert(id.as_str(), j);
        }
        self.budget(next, extra)?;
        self.legs
            .try_reserve_exact(rows.len())
            .map_err(|_| CoreError::resource("calendar allocation failed"))?;
        self.indices
            .try_reserve(rows.len())
            .map_err(|_| CoreError::resource("calendar index allocation failed"))?;
        for (id, cohort, parent, meta, amounts, dwell) in rows {
            let id = self.key(&id);
            let cohort = cohort.as_deref().map(|s| self.key(s)).unwrap_or(NONE);
            let parent = parent
                .as_deref()
                .map(|p| self.indices[&self.key_existing(p).unwrap()]);
            let i = self.legs.len() as u32;
            self.indices.insert(id, i);
            self.legs.push(Leg {
                id,
                cohort,
                parent,
                metadata: meta.try_into().unwrap(),
                amounts: [amounts.0, amounts.1, amounts.2],
                dwell,
                released: 0.0,
                completed: 0.0,
            });
        }
        self.amount_sums = sums;
        self.amount_corrections = corrections;
        Ok(self.legs.len())
    }
    }
    [

    ] {

    /// Generate the exact Cartesian calendar without per-leg Python objects.
    /// Only an empty registry is accepted. Preflight visits the same scalar
    /// expressions and checks all totals/budgets before committing any leg.
    #[cfg(feature="python-extension")]
    fn build_factorized(
        &mut self,
        py: Python<'_>,
        homes: Vec<HomeFactor>,
        targets: Vec<TargetFactor>,
        modes: Vec<ModeFactor>,
        laws: Vec<(u32, u32, u32, u32)>,
        freight: Vec<FreightFactor>,
        config: (f64, f64, f64, f64, f64),
        labels: Vec<u32>,
        freight_profile: u32,
    ) -> CoreResult<usize> {
        py.allow_threads(|| self.build_factorized_owned(homes, targets, modes, laws, freight, config, labels, freight_profile))
    }
    }
    [

    ] {

    fn __len__(&self) -> usize {
        self.legs.len()
    }
    }
    [

    ] {

    fn leg(&self, index: usize) -> CoreResult<Row> {
        let r = self
            .legs
            .get(index)
            .ok_or_else(|| CoreError::index("leg index"))?;
        Ok((
            self.text(r.id).unwrap(),
            self.text(r.cohort),
            r.parent.and_then(|i| self.text(self.legs[i as usize].id)),
            r.metadata.to_vec(),
            (r.amounts[0], r.amounts[1], r.amounts[2]),
            r.dwell,
        ))
    }
    }
    [

    ] {

    fn totals(&self) -> (f64, f64, f64) {
        (
            self.amount_sums[0] + self.amount_corrections[0],
            self.amount_sums[1] + self.amount_corrections[1],
            self.amount_sums[2] + self.amount_corrections[2],
        )
    }
    }
    [

    ] {

    fn requested_totals(&self, start_s: f64, end_s: f64) -> CoreResult<(f64, f64, f64)> {
        if !start_s.is_finite() || !end_s.is_finite() || end_s < start_s {
            return Err(CoreError::value("finite ordered interval required"));
        }
        let fractions: Vec<_> = self
            .profiles
            .iter()
            .map(|p| {
                sum(p
                    .iter()
                    .map(|&(a, b, w)| w * (end_s.min(b) - start_s.max(a)).max(0.0) / (b - a)))
            })
            .collect();
        Ok((
            sum(self
                .legs
                .iter()
                .map(|r| r.amounts[0] * fractions[r.metadata[5] as usize])),
            sum(self
                .legs
                .iter()
                .map(|r| r.amounts[1] * fractions[r.metadata[5] as usize])),
            sum(self
                .legs
                .iter()
                .map(|r| r.amounts[2] * fractions[r.metadata[5] as usize])),
        ))
    }
    }
    [

    ] {

    fn initial_ledger_totals(&self) -> (f64, f64) {
        (
            sum(self.legs.iter().map(|r| r.released)),
            sum(self.legs.iter().map(|r| r.completed)),
        )
    }
    }
    [

    ] {

    fn storage_report(&self) -> (usize, usize, usize, usize, usize) {
        (
            self.legs.len(),
            self.profiles.len(),
            self.labels.len(),
            self.estimate(self.legs.len(), 0),
            self.byte_budget,
        )
    }
    }
);

impl NativeCalendar {
    fn build_factorized_owned(
        &mut self,
        homes: Vec<HomeFactor>,
        targets: Vec<TargetFactor>,
        modes: Vec<ModeFactor>,
        laws: Vec<(u32, u32, u32, u32)>,
        freight: Vec<FreightFactor>,
        config: (f64, f64, f64, f64, f64),
        labels: Vec<u32>,
        freight_profile: u32,
    ) -> CoreResult<usize> {
        if !self.legs.is_empty() || !self.texts.is_empty() {
            return Err(CoreError::value(
                "direct generation requires an empty calendar",
            ));
        }
        let label_ok = |i: u32| (i as usize) < self.labels.len();
        let profile_ok = |i: u32| (i as usize) < self.profiles.len();
        let positive = |x: f64| x.is_finite() && x > 0.0;
        let nonnegative = |x: f64| x.is_finite() && x >= 0.0;
        if labels.len() != 8
            || labels.iter().any(|&i| !label_ok(i))
            || !profile_ok(freight_profile)
            || !positive(config.0)
            || !positive(config.4)
            || !nonnegative(config.1)
            || config.1 > 1.0
            || !nonnegative(config.2)
            || config.2 > 1.0
            || !nonnegative(config.3)
            || homes.is_empty()
            || modes.is_empty()
            || homes.iter().any(|&(label, mass, stationary)| {
                !label_ok(label) || !nonnegative(mass) || stationary > 3
            })
            || modes
                .iter()
                .any(|&(mode, class, share, occupancy, noncar)| {
                    !label_ok(mode)
                        || !label_ok(class)
                        || !positive(share)
                        || !positive(occupancy)
                        || (!noncar && occupancy < 1.0)
                })
        {
            return Err(CoreError::value("invalid registered factorized input"));
        }
        for (purpose, outward, back, total, support, external, destinations) in &targets {
            if !label_ok(*purpose)
                || !profile_ok(*outward)
                || !profile_ok(*back)
                || !nonnegative(*total)
                || !nonnegative(*support)
                || (*total > 0.0 && !positive(*support))
                || (*external && (destinations.len() != 1 || destinations[0].0 != labels[0]))
                || destinations
                    .iter()
                    .any(|&(label, mass)| !label_ok(label) || !nonnegative(mass))
            {
                return Err(CoreError::value(
                    "invalid factorized destination/profile",
                ));
            }
        }
        let mut law_map = HashMap::new();
        for &(home, destination, purpose, law) in &laws {
            if [home, destination, purpose, law]
                .iter()
                .any(|&i| !label_ok(i))
                || law_map.insert((home, destination, purpose), law).is_some()
            {
                return Err(CoreError::value(
                    "invalid or duplicate factorized intrazonal law",
                ));
            }
        }
        let mut freight_ids = HashSet::new();
        for (id, destination, cargo) in &freight {
            if !id.starts_with("freight:")
                || !freight_ids.insert(id)
                || !label_ok(*destination)
                || !nonnegative(*cargo)
            {
                return Err(CoreError::value(
                    "invalid or duplicate factorized freight",
                ));
            }
        }
        let extra = freight.iter().try_fold(0_usize, |n, (id, _, _)| {
            n.checked_add(id.len().saturating_mul(2).saturating_add(128))
                .ok_or_else(|| CoreError::resource("factorized storage overflow"))
        })?;
        let base_bytes = self.estimate(0, extra);
        let per_leg = std::mem::size_of::<Leg>() + 64;
        let mut count = 0_usize;
        let mut sums = [0.0_f64; 3];
        let mut corrections = [0.0_f64; 3];
        visit_factorized(
            &homes,
            &targets,
            &modes,
            &law_map,
            &freight,
            config,
            &labels,
            freight_profile,
            |leg| {
                count = count
                    .checked_add(1)
                    .ok_or_else(|| CoreError::resource("factorized storage overflow"))?;
                if count >= u32::MAX as usize
                    || base_bytes.saturating_add(count.saturating_mul(per_leg))
                        > self.byte_budget
                {
                    return Err(CoreError::resource(
                        "native calendar byte budget exceeded; no generated leg committed",
                    ));
                }
                for (i, x) in leg.amounts.into_iter().enumerate() {
                    let next = sums[i] + x;
                    if !nonnegative(x) || !next.is_finite() {
                        return Err(CoreError::value(
                            "factorized calendar amount overflow",
                        ));
                    }
                    corrections[i] += if sums[i].abs() >= x.abs() {
                        (sums[i] - next) + x
                    } else {
                        (x - next) + sums[i]
                    };
                    sums[i] = next;
                    if !(sums[i] + corrections[i]).is_finite() {
                        return Err(CoreError::value(
                            "factorized calendar amount overflow",
                        ));
                    }
                }
                Ok(())
            },
        )?;
        self.budget(count, extra)?;
        self.legs
            .try_reserve_exact(count)
            .map_err(|_| CoreError::resource("calendar allocation failed"))?;
        self.indices
            .try_reserve(count)
            .map_err(|_| CoreError::resource("calendar index allocation failed"))?;
        self.texts
            .try_reserve_exact(freight.len())
            .map_err(|_| CoreError::resource("calendar text allocation failed"))?;
        self.text_indices
            .try_reserve(freight.len())
            .map_err(|_| CoreError::resource("calendar text index allocation failed"))?;
        // The first traversal checked every operation used below. This
        // traversal allocates no per-leg strings or temporary row arrays.
        visit_factorized(
            &homes,
            &targets,
            &modes,
            &law_map,
            &freight,
            config,
            &labels,
            freight_profile,
            |leg| {
                self.indices.insert(leg.id, self.legs.len() as u32);
                self.legs.push(leg);
                Ok(())
            },
        )?;
        for (i, (id, _, _)) in freight.into_iter().enumerate() {
            self.texts.push(id.clone());
            self.text_indices.insert(id, i as u64);
        }
        self.amount_sums = sums;
        self.amount_corrections = corrections;
        Ok(count)
    }
}

/// Language-neutral marginal declaration, not a Python TripLeg export.
#[cfg(feature = "native-cli")]
#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct FactorizedDeclaration {
    pub city_identity: String,
    pub schedule_identity: String,
    pub labels: Vec<String>,
    pub profiles: Vec<Vec<(f64,f64,f64)>>,
    pub homes: Vec<HomeFactor>,
    pub targets: Vec<TargetFactor>,
    pub modes: Vec<ModeFactor>,
    pub laws: Vec<(u32,u32,u32,u32)>,
    pub freight: Vec<FreightFactor>,
    pub config: (f64,f64,f64,f64,f64),
    pub constants: Vec<u32>,
    pub freight_profile: u32,
}
#[cfg(feature = "native-cli")]
impl FactorizedDeclaration {
    pub(crate) fn compile(self, budget:usize)->CoreResult<NativeCalendar>{
        let mut calendar=NativeCalendar::new(budget,self.city_identity,self.schedule_identity)?;
        for (i,label) in self.labels.into_iter().enumerate(){
            if calendar.intern_label(label)? as usize!=i{return Err(CoreError::value("duplicate declaration label"))}
        }
        for (i,profile) in self.profiles.into_iter().enumerate(){
            if calendar.intern_profile(profile)? as usize!=i{return Err(CoreError::value("duplicate declaration profile"))}
        }
        calendar.build_factorized_owned(self.homes,self.targets,self.modes,self.laws,self.freight,self.config,self.constants,self.freight_profile)?;
        Ok(calendar)
    }
}
