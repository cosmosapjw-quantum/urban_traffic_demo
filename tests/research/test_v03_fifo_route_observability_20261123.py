"""Exact finite checks for the causal FIFO observability construction."""
from fractions import Fraction as F
from itertools import product
from math import ceil
import pytest

from metroflow.v1.fifo_route_observability import (
    ArrivalBand, PassageProbe, FIFOArrivalEnvelope, RouteEdge,
    FiniteResponseField, compose_route, route_certificate,
)


def probe(x, lo, hi, *, context="road", stamp=10, delivered=10):
    return PassageProbe(context, F(x), F(lo), F(hi), F(stamp), F(delivered))


def envelope(probes, gamma=2, tau=1, context="road"):
    return FIFOArrivalEnvelope(probes, context=context, decision_s=10,
                               entry_horizon_s=100, tau_min_s=tau, gamma=gamma)


def field():
    return FiniteResponseField(((0, 2), (20, 3), (40, 2), (100, 2)), 2)


def measured_envelope(length):
    physics = field()
    probes = []
    for entry in (0, 5, 10, 15):
        band = physics.exit_band(entry, length, F(1, 10**10))
        stamp = F(ceil(band.upper))
        delivery = stamp + 1
        if delivery <= 20:
            probes.append(PassageProbe("length:"+str(length), F(entry),
                                      band.lower, band.upper, stamp, delivery))
    _, vmax = physics.speed_bounds
    return FIFOArrivalEnvelope(probes, context="length:"+str(length),
                               decision_s=20, entry_horizon_s=60,
                               tau_min_s=F(length)/vmax, gamma=physics.gamma)


def test_directed_envelope_formula_and_pointwise_constraints():
    model = envelope((probe(2, 5, 6), probe(4, 7, 8)), tau=2)
    assert model.at(3) == ArrivalBand(F(5), F(8))
    assert model.at(10) == ArrivalBand(F(12), F(20))
    clocks = [F(k, 4) for k in range(81)]
    bands = [model.at(t) for t in clocks]
    for t, band in zip(clocks, bands):
        assert t+2 <= band.lower <= band.upper
    for a, b in zip(bands, bands[1:]):
        assert 0 <= b.lower-a.lower <= F(1, 2)
        assert 0 <= b.upper-a.upper <= F(1, 2)


def test_sharpness_against_all_admissible_integer_grid_maps():
    model = envelope((probe(1, 2, 3), probe(2, 3, 5)))
    candidates = []
    for ys in product(range(1, 8), repeat=4):
        if not all(y >= t+1 for t, y in enumerate(ys)):
            continue
        if not all(0 <= b-a <= 2 for a, b in zip(ys, ys[1:])):
            continue
        if 2 <= ys[1] <= 3 and 3 <= ys[2] <= 5:
            candidates.append(ys)
    # y1=2 gives 2*(2+3)=10; y1=3 gives 3*(2+3+3)=24.
    assert len(candidates) == 34
    for t in range(4):
        band = model.at(t)
        assert band.lower == min(row[t] for row in candidates)
        assert band.upper == max(row[t] for row in candidates)


def test_causal_scope_and_population_means_rejected():
    with pytest.raises(ValueError, match="not delivered"):
        envelope((probe(0, 1, 1, delivered=11),))
    with pytest.raises(ValueError, match="context"):
        envelope((probe(0, 1, 1, context="other"),))
    with pytest.raises(ValueError, match="matched boundary"):
        PassageProbe("road", 0, 1, 1, 2, 2, kind="completed conditional mean")
    with pytest.raises(ValueError, match="causal"):
        probe(4, 3, 3)
    with pytest.raises(ValueError, match="minimum physical"):
        envelope((probe(0, 1, 1),), tau=2)


def test_conflicting_intervals_and_bad_gamma_rejected():
    with pytest.raises(ValueError, match="no admissible"):
        envelope((probe(0, 8, 9), probe(1, 2, 3)))
    with pytest.raises(ValueError, match="no admissible"):
        envelope((probe(0, 1, 1), probe(2, 6, 6)))
    with pytest.raises(ValueError, match="gamma"):
        envelope((), gamma=F(1, 2))
    with pytest.raises(ValueError, match="domain"):
        envelope(()).at(101)


def test_fifo_without_expansion_certificate_keeps_future_unknown():
    model = envelope((probe(2, 5, 6), probe(4, 7, 8)), gamma=None, tau=2)
    assert model.at(3) == ArrivalBand(F(5), F(8))
    assert model.at(10) == ArrivalBand(F(12), None)
    assert envelope((), gamma=2).at(10) == ArrivalBand(F(11), None)
    with pytest.raises(ValueError, match="no admissible"):
        envelope((probe(0, 8, 9), probe(1, 2, 3)), gamma=None)


def test_finite_response_invariant_bounds_and_exact_integral():
    physics = field()
    assert physics.speed_bounds == (F(19, 10), F(31, 10))
    assert physics.gamma == F(31, 19)
    assert physics.distance(0, 20) == 50
    assert physics.distance(20, 40) == 50
    band = physics.exit_band(0, 50)
    assert band.lower <= 20 <= band.upper
    assert band.width <= F(1, 10**9)
    with pytest.raises(ValueError, match="positive invariant"):
        FiniteResponseField(((0, 2), (1, F(1, 10))), 2)
    with pytest.raises(ValueError, match="unresolved"):
        physics.exit_band(99, 20)


def test_past_only_measured_probes_bound_withheld_physical_passages():
    physics = field()
    checked = 0
    for length in (5, 10, 20, 30):
        model = measured_envelope(length)
        assert model.probes and all(p.delivered_s <= 20 for p in model.probes)
        for entry in (F(20)+F(k, 2) for k in range(31)):
            actual = physics.exit_band(entry, length, F(1, 10**10))
            predicted = model.at(entry)
            assert predicted.lower <= actual.lower <= actual.upper <= predicted.upper
            assert physics.distance(entry, actual.lower) <= length
            assert physics.distance(entry, actual.upper) >= length
            checked += 1
    assert checked == 124


def test_route_certificate_and_legal_cycle_match_path_enumeration():
    short, long, cycle = measured_envelope(10), measured_envelope(20), measured_envelope(5)
    graph = (RouteEdge("direct", "O", "D", short),
             RouteEdge("detour_1", "O", "X", long),
             RouteEdge("detour_2", "X", "D", long),
             RouteEdge("return", "X", "O", cycle))
    result = route_certificate(graph, "O", "D", 20)
    direct = compose_route((short,), 20)
    detour = compose_route((long, long), 20)
    assert result.selected_edges == ("direct",)
    assert result.lower_optimum_s == min(direct.lower, detour.lower)
    assert result.upper_selected_s == min(direct.upper, detour.upper)
    assert direct.upper < detour.lower
    actual = field().exit_band(20, 10, F(1, 10**10))
    assert actual.upper-result.lower_optimum_s <= result.regret_bound_s


def test_unknown_route_upper_is_not_physical_unreachability():
    no_rate = envelope((probe(2, 4, 5),), gamma=None)
    result = route_certificate((RouteEdge("one", "O", "D", no_rate),), "O", "D", 10)
    assert result.lower_optimum_s == 11
    assert result.upper_selected_s is None and result.regret_bound_s is None


def test_route_rejects_future_information_same_location_and_duplicate_arcs():
    model = envelope((probe(0, 1, 1),))
    edge = RouteEdge("one", "O", "D", model)
    with pytest.raises(ValueError, match="future information"):
        route_certificate((edge,), "O", "D", 9)
    with pytest.raises(ValueError, match="same-location"):
        route_certificate((edge,), "O", "O", 10)
    with pytest.raises(ValueError, match="unique"):
        route_certificate((edge, edge), "O", "D", 10)
    with pytest.raises(ValueError, match="after departure"):
        compose_route((model,), 9)


def test_frozen_additive_link_cost_is_not_dynamic_route_time():
    first = lambda t: F(t)+1
    second = lambda t: F(1)+100*F(t) if t <= 1 else F(t)+100
    frozen_sum = (first(0)-0)+(second(0)-0)
    actual_route_time = second(first(0))-0
    assert frozen_sum == 2
    assert actual_route_time == 101
    assert all(second(F(i, 10)) <= second(F(i+1, 10)) for i in range(20))
