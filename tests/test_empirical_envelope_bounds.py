"""The empirical envelope must be able to fail.

`[0.8 * ref_min, 1.2 * ref_max]` is derived without reference to each metric's
theoretical range, so a bound can land outside the values the metric can even
take. Such a bound is vacuous: no generated map can ever violate it, and the
gate silently stops discriminating on that metric.

Repairs here may only ever make a bound STRICTER. Loosening a bound would be
threshold tuning, which the PRD forbids.
"""

from __future__ import annotations

import math


def test_orientation_entropy_upper_bound_is_attainable() -> None:
    """36 orientation bins cap entropy at log(36); 1.2 * ref_max exceeds it."""

    from metroflow.city.plausibility_audit import build_empirical_metric_envelopes

    envelope = build_empirical_metric_envelopes()["orientation_entropy"]

    maximum_entropy = math.log(36.0)
    assert envelope.reference_max * 1.2 > maximum_entropy, (
        "precondition: the unclamped bound is what makes this metric vacuous"
    )
    assert envelope.upper <= maximum_entropy + 1e-12


def test_every_envelope_bound_lies_inside_its_theoretical_range() -> None:
    from metroflow.city.plausibility_audit import build_empirical_metric_envelopes

    theoretical = {
        "orientation_order": (0.0, 1.0),
        "orientation_entropy": (0.0, math.log(36.0)),
        "median_segment_length_m": (0.0, math.inf),
        "circuity": (1.0, math.inf),
        "mean_node_degree": (0.0, math.inf),
        "dead_end_share": (0.0, 1.0),
        "four_way_share": (0.0, 1.0),
    }

    envelopes = build_empirical_metric_envelopes()
    assert set(envelopes) == set(theoretical)
    for metric, (low, high) in theoretical.items():
        envelope = envelopes[metric]
        assert low - 1e-12 <= envelope.lower <= high + 1e-12, metric
        assert low - 1e-12 <= envelope.upper <= high + 1e-12, metric


def test_repair_only_tightens_never_loosens() -> None:
    """Every bound must stay at least as strict as the raw 20-percent rule."""

    from metroflow.city.plausibility_audit import build_empirical_metric_envelopes

    for metric, envelope in build_empirical_metric_envelopes().items():
        assert envelope.lower >= envelope.reference_min * 0.8 - 1e-12, metric
        assert envelope.upper <= envelope.reference_max * 1.2 + 1e-12, metric


def test_envelope_reports_whether_a_bound_can_discriminate() -> None:
    """A bound covering its whole theoretical range cannot fail; say so."""

    from metroflow.city.plausibility_audit import build_empirical_metric_envelopes

    envelopes = build_empirical_metric_envelopes()

    # orientation_order spans [0.0016, 1.0] of a theoretical [0, 1].
    assert envelopes["orientation_order"].is_vacuous is True
    # dead_end_share spans [0.0216, 0.3456] of a theoretical [0, 1].
    assert envelopes["dead_end_share"].is_vacuous is False
