//! Define one method body with optional Python frontend attributes.
//! PyO3 consumes its helper attributes before Rust expands nested cfg_attr;
//! a feature-selected macro emits the actual attributes only at the FFI seam.
#[cfg(feature="python-extension")]
macro_rules! optional_pymethods {
    ($ty:ty, $([$($py:tt)*] {$($method:tt)*})*) => {
        #[pyo3::pymethods]
        impl $ty { $($($py)* $($method)*)* }
    };
}
#[cfg(not(feature="python-extension"))]
macro_rules! optional_pymethods {
    ($ty:ty, $([$($py:tt)*] {$($method:tt)*})*) => {
        impl $ty { $($($method)*)* }
    };
}
pub(crate) use optional_pymethods;
