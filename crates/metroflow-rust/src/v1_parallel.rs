//! Explicit, private native workers and deterministic indexed maps.
//!
//! A caller outside a `ParallelPolicy` pool is always serial, including legacy
//! engines that happen to be called from Rayon's unrelated global pool. Each
//! private worker is marked by its own start handler: `install` does not inherit
//! the calling thread's TLS. Reductions and commits stay with the caller.
use rayon::prelude::*;
use rayon::{ThreadPool, ThreadPoolBuilder};
use std::cell::Cell;

thread_local! {
    static ENABLED: Cell<bool> = const { Cell::new(false) };
}

struct EnableGuard(bool);
impl Drop for EnableGuard {
    fn drop(&mut self) {
        ENABLED.with(|enabled| enabled.set(self.0));
    }
}

pub(crate) struct ParallelPolicy {
    threads: usize,
    pool: Option<ThreadPool>,
}

impl ParallelPolicy {
    pub(crate) fn new(threads: usize) -> Result<Self, String> {
        if !(1..=256).contains(&threads) {
            return Err("native_threads must be in 1..=256".to_owned());
        }
        let pool = if threads == 1 {
            None
        } else {
            Some(
                ThreadPoolBuilder::new()
                    .num_threads(threads)
                    .thread_name(|i| format!("metroflow-v1-{i}"))
                    .start_handler(|_| ENABLED.with(|enabled| enabled.set(true)))
                    .build()
                    .map_err(|error| format!("cannot create native worker pool: {error}"))?,
            )
        };
        Ok(Self { threads, pool })
    }

    pub(crate) fn threads(&self) -> usize {
        self.threads
    }

    pub(crate) fn run<F, R>(&self, f: F) -> R
    where
        F: FnOnce() -> R + Send,
        R: Send,
    {
        match &self.pool {
            Some(pool) => pool.install(f),
            None => {
                // Keep a nested explicit single-worker policy serial too.
                let previous = ENABLED.with(|enabled| enabled.replace(false));
                let _guard = EnableGuard(previous);
                f()
            }
        }
    }
}

/// An indexed map with an unchanged serial commit order. In particular, return
/// `Vec<Result<...>>` and inspect it serially when several items can fail; using
/// a parallel short-circuit collector would choose errors nondeterministically.
pub(crate) fn ordered_map<T, F>(len: usize, minimum_parallel_len: usize, f: F) -> Vec<T>
where
    T: Send,
    F: Fn(usize) -> T + Sync + Send,
{
    if len >= minimum_parallel_len && ENABLED.with(Cell::get) {
        (0..len).into_par_iter().map(f).collect()
    } else {
        (0..len).map(f).collect()
    }
}
