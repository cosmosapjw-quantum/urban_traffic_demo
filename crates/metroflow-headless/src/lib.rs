//! Standalone research backend. No PyO3, foreign runtime or subprocess.
pub mod access;
pub mod input;
pub mod kinetics;
pub mod preflight;
pub mod prepare;
pub mod queue;
pub mod receipt;

pub mod active_kinetic;
