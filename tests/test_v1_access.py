import pytest
from metroflow.terrain_city.area_access import AreaAccess, Portal


def profile():
    return AreaAccess(((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0))).evaluate(
        (Portal("west", (0.0, 50.0)), Portal("east", (100.0, 50.0))),
        speed_mps=5.0,
        depth=3,
        keep_samples=True,
    )


def test_compiled_law_preserves_portal_mass_mean_and_bounds_fragment_compression():
    from metroflow.v1.access import compile_access

    p = profile()
    law = compile_access(p, bin_s=2.0, max_atoms=100)
    assert sum(a.weight for a in law.atoms) == pytest.approx(1.0)
    assert law.mean_s == pytest.approx(p["mean_s"], abs=1e-12)
    assert dict(law.portal_weights()) == pytest.approx(p["portal_fraction"], abs=1e-12)
    assert len(law.atoms) < len(p["quadrature"])
    assert 0 <= law.mean_absolute_compression_s < 2.0
    assert 0 <= law.variance_loss_s2 < 4.0
    assert law.quadrature_mean_bound_s == p["error_bound_s"]


def test_same_measure_fragment_and_order_not_new_population():
    from metroflow.v1.access import compile_access

    p = profile()
    split = dict(p)
    split["quadrature"] = [
        dict(q, weight=q["weight"] / 3) for q in reversed(p["quadrature"]) for _ in range(3)
    ]
    a = compile_access(p, 2.0, 100)
    b = compile_access(split, 2.0, 100)
    assert a.mean_s == pytest.approx(b.mean_s, abs=1e-12)
    assert len(a.atoms) == len(b.atoms)
    for x, y in zip(a.atoms, b.atoms):
        assert x.portal == y.portal and x.delay_s == pytest.approx(y.delay_s, abs=1e-12)
        assert x.weight == pytest.approx(y.weight, abs=1e-12)


def test_conditional_gate_does_not_renormalize_away_population():
    from metroflow.v1.access import compile_access

    law = compile_access(profile(), 2.0, 100)
    mass, delays = law.condition("west")
    assert mass == pytest.approx(0.5)
    assert sum(w for _, w in delays) == pytest.approx(1.0)
    assert mass * sum(w * t for t, w in delays) == pytest.approx(
        sum(a.weight * a.delay_s for a in law.atoms if a.portal == "west")
    )
    with pytest.raises(ValueError):
        law.condition("unknown")


def test_external_cost_is_not_silently_counted_as_physical_access():
    from metroflow.v1.access import compile_access

    p = profile()
    with pytest.raises(ValueError, match="external"):
        compile_access(p, external_costs={"west": 20.0})


def test_budget_and_malformed_probability_fail_without_dropping_mass():
    from metroflow.v1.access import compile_access

    p = profile()
    with pytest.raises(ValueError):
        compile_access(p, bin_s=0.01, max_atoms=1)
    with pytest.raises(ValueError):
        compile_access(p, bin_s=0.0)
    q = dict(p)
    q["quadrature"] = [dict(p["quadrature"][0], weight=-1)]
    with pytest.raises(ValueError):
        compile_access(q)
    q = dict(p)
    q["quadrature"] = [dict(r, weight=2 * r["weight"]) for r in p["quadrature"]]
    with pytest.raises(ValueError):
        compile_access(q)


def test_nonzero_spread_not_replaced_by_one_centroid_delay():
    from metroflow.v1.access import compile_access

    law = compile_access(profile(), 1.0, 100)
    assert len({a.delay_s for a in law.atoms}) > 1
    assert law.compressed_variance_s2 > 0
    assert law.original_variance_s2 == pytest.approx(
        law.compressed_variance_s2 + law.variance_loss_s2
    )
