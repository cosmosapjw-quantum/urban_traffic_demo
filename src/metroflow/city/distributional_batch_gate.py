from __future__ import annotations


def evaluate_distributional_batch_gate(
    *,
    metrics: dict[str, float],
    thresholds: dict[str, float],
) -> dict[str, object]:
    hard_fail_rate = float(metrics.get("hard_fail_rate", 0.0))
    ring_rate = float(metrics.get("ring_radial_connectivity_pass_rate", 1.0))
    hard_fail_limit = float(thresholds.get("hard_fail_rate_max", 0.02))
    ring_min = float(thresholds.get("ring_radial_connectivity_min", 0.95))

    reasons: list[str] = []
    if hard_fail_rate > hard_fail_limit:
        reasons.append("SC-001_HARD_FAIL_RATE_EXCEEDED")
    if ring_rate < ring_min:
        reasons.append("SC-006_RING_RADIAL_CONNECTIVITY_BELOW_MIN")

    return {
        "accepted": not reasons,
        "reason_codes": reasons,
        "metrics": {
            "hard_fail_rate": hard_fail_rate,
            "ring_radial_connectivity_pass_rate": ring_rate,
        },
        "thresholds": {
            "hard_fail_rate_max": hard_fail_limit,
            "ring_radial_connectivity_min": ring_min,
        },
    }


def evaluate_incident_stress_seed(
    *,
    mandatory_od_connectivity_rate: float,
    accessibility_retention_ratio: float,
    repair_iteration_count: int,
    max_iterations: int,
) -> dict[str, object]:
    if repair_iteration_count > max_iterations:
        return {
            "pass_or_fail": "fail",
            "reason_code": "SC-011_REPAIR_ITERATION_LIMIT",
            "repair_iteration_count": repair_iteration_count,
        }
    if mandatory_od_connectivity_rate < 0.95:
        return {
            "pass_or_fail": "fail",
            "reason_code": "SC-011_CONNECTIVITY_BELOW_MIN",
            "repair_iteration_count": repair_iteration_count,
        }
    if accessibility_retention_ratio < 0.85:
        return {
            "pass_or_fail": "fail",
            "reason_code": "SC-011_ACCESSIBILITY_BELOW_MIN",
            "repair_iteration_count": repair_iteration_count,
        }
    return {
        "pass_or_fail": "pass",
        "reason_code": "OK",
        "repair_iteration_count": repair_iteration_count,
    }
