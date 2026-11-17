//! Diagnostic record of native storage-guard margins.
//!
//! Recording is off unless `METROFLOW_BUDGET_TRACE=record|observe` is set when
//! the extension is first used; it never changes a guard decision. Only a build
//! with the `budget_trace` cargo feature counts live heap bytes, and only that
//! build honours `observe`, which logs an exceeded guard and continues. Such a
//! build is a diagnostic instrument, never a campaign candidate.
use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::collections::BTreeMap;
use std::sync::atomic::{AtomicU8, Ordering};
use std::sync::Mutex;

#[cfg(feature = "budget_trace")]
mod counting {
    use std::alloc::{GlobalAlloc, Layout, System};
    use std::sync::atomic::{AtomicUsize, Ordering};
    pub(super) static LIVE: AtomicUsize = AtomicUsize::new(0);
    pub(super) static PEAK: AtomicUsize = AtomicUsize::new(0);
    pub(super) struct Counting;
    fn grow(n: usize) {
        let live = LIVE.fetch_add(n, Ordering::Relaxed) + n;
        PEAK.fetch_max(live, Ordering::Relaxed);
    }
    unsafe impl GlobalAlloc for Counting {
        unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
            let p = System.alloc(layout);
            if !p.is_null() {
                grow(layout.size());
            }
            p
        }
        unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
            let p = System.alloc_zeroed(layout);
            if !p.is_null() {
                grow(layout.size());
            }
            p
        }
        unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
            System.dealloc(ptr, layout);
            LIVE.fetch_sub(layout.size(), Ordering::Relaxed);
        }
        unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, new: usize) -> *mut u8 {
            let p = System.realloc(ptr, layout, new);
            if !p.is_null() {
                if new >= layout.size() {
                    grow(new - layout.size());
                } else {
                    LIVE.fetch_sub(layout.size() - new, Ordering::Relaxed);
                }
            }
            p
        }
    }
    #[global_allocator]
    static GLOBAL: Counting = Counting;
}

fn live_bytes() -> Option<usize> {
    #[cfg(feature = "budget_trace")]
    {
        Some(counting::LIVE.load(Ordering::Relaxed))
    }
    #[cfg(not(feature = "budget_trace"))]
    {
        None
    }
}

#[derive(Default, Clone)]
struct Record {
    calls: u64,
    exceeded: u64,
    max_required: usize,
    limit_at_max: usize,
    max_ratio: f64,
    live_at_max: Option<usize>,
    terms_at_max: Vec<(&'static str, usize)>,
}

// 0 = unread, 1 = off, 2 = record, 3 = observe
static MODE: AtomicU8 = AtomicU8::new(0);
static RECORDS: Mutex<BTreeMap<String, Record>> = Mutex::new(BTreeMap::new());

fn mode() -> u8 {
    let m = MODE.load(Ordering::Relaxed);
    if m != 0 {
        return m;
    }
    let m = match std::env::var("METROFLOW_BUDGET_TRACE").as_deref() {
        Ok("record") => 2,
        Ok("observe") if cfg!(feature = "budget_trace") => 3,
        Ok("observe") => 2,
        _ => 1,
    };
    MODE.store(m, Ordering::Relaxed);
    m
}

/// Record one guard evaluation. Returns true only when a diagnostic
/// `budget_trace` build runs in observe mode and the guard was exceeded, in
/// which case the caller continues instead of raising.
pub(crate) fn guard(
    site: &'static str,
    phase: &str,
    required: usize,
    limit: usize,
    terms: &[(&'static str, usize)],
) -> bool {
    let m = mode();
    if m == 1 {
        return false;
    }
    let exceeded = required > limit;
    let ratio = if limit == 0 {
        f64::INFINITY
    } else {
        required as f64 / limit as f64
    };
    let mut records = RECORDS.lock().unwrap_or_else(|e| e.into_inner());
    let r = records.entry(format!("{site}:{phase}")).or_default();
    r.calls += 1;
    r.exceeded += u64::from(exceeded);
    if r.calls == 1 || ratio > r.max_ratio {
        r.max_ratio = ratio;
        r.max_required = required;
        r.limit_at_max = limit;
        r.live_at_max = live_bytes();
        r.terms_at_max = terms.to_vec();
    }
    exceeded && m == 3
}

#[pyfunction]
#[pyo3(signature = (reset=true))]
pub(crate) fn budget_trace_snapshot(py: Python<'_>, reset: bool) -> PyResult<PyObject> {
    let out = PyDict::new(py);
    let m = mode();
    out.set_item(
        "mode",
        match m {
            2 => "record",
            3 => "observe",
            _ => "off",
        },
    )?;
    out.set_item("alloc_counting", cfg!(feature = "budget_trace"))?;
    #[cfg(feature = "budget_trace")]
    {
        out.set_item("live_bytes", counting::LIVE.load(Ordering::Relaxed))?;
        out.set_item("peak_bytes", counting::PEAK.load(Ordering::Relaxed))?;
        if reset {
            counting::PEAK.store(counting::LIVE.load(Ordering::Relaxed), Ordering::Relaxed);
        }
    }
    let sites = PyDict::new(py);
    let mut records = RECORDS.lock().unwrap_or_else(|e| e.into_inner());
    for (key, r) in records.iter() {
        let d = PyDict::new(py);
        d.set_item("calls", r.calls)?;
        d.set_item("exceeded", r.exceeded)?;
        d.set_item("max_required", r.max_required)?;
        d.set_item("limit_at_max", r.limit_at_max)?;
        d.set_item("max_ratio", r.max_ratio)?;
        d.set_item("live_at_max", r.live_at_max)?;
        let terms = PyDict::new(py);
        for (k, v) in &r.terms_at_max {
            terms.set_item(*k, *v)?;
        }
        d.set_item("terms_at_max", terms)?;
        sites.set_item(key, d)?;
    }
    if reset {
        records.clear();
    }
    out.set_item("sites", sites)?;
    Ok(out.into())
}
