from __future__ import annotations


def evaluate_adversarial_seed_gate(seed_reports: list[dict[str, object]]) -> dict[str, object]:
    any_hard_fail = any(bool(r.get("hard_fail", False)) for r in seed_reports)
    return {
        "accepted": not any_hard_fail,
        "triggered_hard_fail": any_hard_fail,
    }
