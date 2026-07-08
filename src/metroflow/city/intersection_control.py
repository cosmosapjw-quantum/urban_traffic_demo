from __future__ import annotations

from collections import Counter


_REQUIRED = ("signalized", "unsignalized_priority", "roundabout_compatible")


def assign_intersection_controls(intersections: list[dict[str, object]]) -> dict[str, object]:
    assignments: list[str] = []
    violations = 0
    for node in intersections:
        major_degree = int(node.get("major_degree", 0))
        has_roundabout = bool(node.get("has_roundabout_geometry", False))
        if has_roundabout:
            control = "roundabout_compatible"
        elif major_degree >= 4:
            control = "signalized"
        elif major_degree >= 2:
            control = "unsignalized_priority"
        else:
            control = "unsignalized_priority"
            violations += 1
        assignments.append(control)

    coverage = Counter(assignments)
    missing = [name for name in _REQUIRED if coverage.get(name, 0) == 0]
    return {
        "intersection_control_coverage_by_type": {
            "signalized": int(coverage.get("signalized", 0)),
            "unsignalized_priority": int(coverage.get("unsignalized_priority", 0)),
            "roundabout_compatible": int(coverage.get("roundabout_compatible", 0)),
        },
        "intersection_control_rule_violations": int(violations),
        "required_control_types_missing": missing,
    }
