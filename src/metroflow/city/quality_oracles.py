from __future__ import annotations


def evaluate_hard_fail_oracle(metrics: dict[str, float]) -> dict[str, object]:
    reasons: list[str] = []
    if float(metrics.get("orientation_collapse_index", 0.0)) > 0.95:
        reasons.append("ORIENTATION_COLLAPSE")
    if float(metrics.get("ring_radial_connectivity_pass_rate", 1.0)) < 0.50:
        reasons.append("CONNECTIVITY_COLLAPSE")
    if float(metrics.get("downtown_core_density_ratio", 1.0)) < 0.8:
        reasons.append("DOWNTOWN_COLLAPSE")
    return {
        "hard_fail": bool(reasons),
        "hard_fail_reasons": reasons,
    }
