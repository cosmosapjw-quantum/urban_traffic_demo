#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Gate {
    Pass,
    Fail,
    Unknown,
}
fn eligible(gates: &[Gate]) -> bool {
    !gates.is_empty() && gates.iter().all(|g| *g == Gate::Pass)
}
fn main() {}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn noncompensatory() {
        assert!(!eligible(&[Gate::Pass, Gate::Fail]));
        assert!(!eligible(&[Gate::Pass, Gate::Unknown]));
        assert!(!eligible(&[]));
        assert!(eligible(&[Gate::Pass, Gate::Pass]));
    }
}
