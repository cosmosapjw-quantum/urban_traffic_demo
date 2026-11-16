//! Persistent exact-identity calendar storage. No transport evolution is implied.
use pyo3::exceptions::{PyIndexError, PyMemoryError, PyValueError};
use pyo3::prelude::*;
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
#[derive(Clone)]
struct Leg {
    id: u64,
    cohort: u64,
    parent: Option<u32>,
    metadata: [u32; 8], // origin,destination,purpose,mode,class,profile,law,endpoint kind
    amounts: [f64; 3],
    dwell: f64,
    released: f64,
    completed: f64,
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

#[pyclass]
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
    fn text(&self, k: u64) -> Option<String> {
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
    fn budget(&self, n: usize, extra: usize) -> PyResult<()> {
        if self.estimate(n, extra) > self.byte_budget {
            Err(PyMemoryError::new_err(
                "native calendar byte budget exceeded; page not committed",
            ))
        } else {
            Ok(())
        }
    }
}

#[pymethods]
impl NativeCalendar {
    #[new]
    #[pyo3(signature = (byte_budget, city_identity=String::new(), schedule_identity=String::new()))]
    fn new(byte_budget: usize, city_identity: String, schedule_identity: String) -> PyResult<Self> {
        if byte_budget == 0 {
            return Err(PyValueError::new_err("positive byte budget required"));
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
    fn binding(&self) -> (String, String) {
        (self.city_identity.clone(), self.schedule_identity.clone())
    }
    fn intern_label(&mut self, text: String) -> PyResult<u32> {
        if let Some(i) = self.label_indices.get(&text) {
            return Ok(*i);
        }
        self.budget(self.legs.len(), text.len() * 2 + 128)?;
        let i = u32::try_from(self.labels.len())
            .map_err(|_| PyValueError::new_err("label index overflow"))?;
        self.labels.push(text.clone());
        self.label_indices.insert(text, i);
        Ok(i)
    }
    fn label(&self, index: usize) -> PyResult<String> {
        self.labels
            .get(index)
            .cloned()
            .ok_or_else(|| PyIndexError::new_err("label index"))
    }
    fn intern_profile(&mut self, windows: Vec<(f64, f64, f64)>) -> PyResult<u32> {
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
            return Err(PyValueError::new_err(
                "finite normalized departure profile required",
            ));
        }
        let mut ordered = windows.clone();
        ordered.sort_by(|a, b| a.0.total_cmp(&b.0));
        if ordered.windows(2).any(|w| w[0].1 > w[1].0) {
            return Err(PyValueError::new_err("overlapping departure windows"));
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
    fn profile(&self, index: usize) -> PyResult<Vec<(f64, f64, f64)>> {
        self.profiles
            .get(index)
            .cloned()
            .ok_or_else(|| PyIndexError::new_err("profile index"))
    }
    fn append(&mut self, rows: Vec<Row>) -> PyResult<usize> {
        let next = self
            .legs
            .len()
            .checked_add(rows.len())
            .ok_or_else(|| PyValueError::new_err("calendar index overflow"))?;
        if next >= u32::MAX as usize {
            return Err(PyValueError::new_err("calendar index overflow"));
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
                return Err(PyValueError::new_err("unique nonempty leg IDs required"));
            }
            if meta.len() != 8
                || meta[5] as usize >= self.profiles.len()
                || meta
                    .iter()
                    .enumerate()
                    .any(|(k, &v)| k != 5 && v as usize >= self.labels.len())
            {
                return Err(PyValueError::new_err(
                    "registered metadata/profile required",
                ));
            }
            if [amounts.0, amounts.1, amounts.2, *dwell]
                .iter()
                .any(|v| !v.is_finite() || *v < 0.0)
            {
                return Err(PyValueError::new_err(
                    "finite nonnegative amounts/dwell required",
                ));
            }
            for (i, x) in [amounts.0, amounts.1, amounts.2].into_iter().enumerate() {
                let t = sums[i] + x;
                if !t.is_finite() {
                    return Err(PyValueError::new_err("calendar amount total overflow"));
                }
                corrections[i] += if sums[i].abs() >= x.abs() {
                    (sums[i] - t) + x
                } else {
                    (x - t) + sums[i]
                };
                sums[i] = t;
                if !(sums[i] + corrections[i]).is_finite() {
                    return Err(PyValueError::new_err("calendar amount total overflow"));
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
                    return Err(PyValueError::new_err(
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
            .map_err(|_| PyMemoryError::new_err("calendar allocation failed"))?;
        self.indices
            .try_reserve(rows.len())
            .map_err(|_| PyMemoryError::new_err("calendar index allocation failed"))?;
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
    fn __len__(&self) -> usize {
        self.legs.len()
    }
    fn leg(&self, index: usize) -> PyResult<Row> {
        let r = self
            .legs
            .get(index)
            .ok_or_else(|| PyIndexError::new_err("leg index"))?;
        Ok((
            self.text(r.id).unwrap(),
            self.text(r.cohort),
            r.parent.and_then(|i| self.text(self.legs[i as usize].id)),
            r.metadata.to_vec(),
            (r.amounts[0], r.amounts[1], r.amounts[2]),
            r.dwell,
        ))
    }
    fn totals(&self) -> (f64, f64, f64) {
        (
            self.amount_sums[0] + self.amount_corrections[0],
            self.amount_sums[1] + self.amount_corrections[1],
            self.amount_sums[2] + self.amount_corrections[2],
        )
    }
    fn requested_totals(&self, start_s: f64, end_s: f64) -> PyResult<(f64, f64, f64)> {
        if !start_s.is_finite() || !end_s.is_finite() || end_s < start_s {
            return Err(PyValueError::new_err("finite ordered interval required"));
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
    fn initial_ledger_totals(&self) -> (f64, f64) {
        (
            sum(self.legs.iter().map(|r| r.released)),
            sum(self.legs.iter().map(|r| r.completed)),
        )
    }
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
