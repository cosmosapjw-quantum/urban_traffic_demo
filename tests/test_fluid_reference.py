"""Independent continuum oracle tests, separate from integer vehicle claims."""

import importlib
import importlib.util
import pytest


def reference():
    name = "metroflow.pure_traffic.fluid_reference"
    assert importlib.util.find_spec(name) is not None, (
        "continuous Godunov reference is not implemented"
    )
    return importlib.import_module(name)


def test_exact_triangle_shock_and_expansion_cell_averages():
    ref = reference()
    fd = ref.FundamentalDiagram(15.0, 5.0, 0.15)
    assert fd.critical_density == pytest.approx(0.0375)
    assert fd.capacity == pytest.approx(0.5625)
    assert ref.exact_riemann_averages(fd, 0.02, 0.10, (-100.0, -62.5, 0.0), 100.0) == pytest.approx(
        (0.02, 0.10)
    )
    assert ref.exact_riemann_averages(
        fd, 0.12, 0.01, (-1000.0, -500.0, 1500.0, 2000.0), 100.0
    ) == pytest.approx((0.12, 0.0375, 0.01))


@pytest.mark.parametrize("left,right", [(0.02, 0.10), (0.12, 0.01)])
def test_godunov_refinement_reduces_integrated_density_error(left, right):
    ref = reference()
    fd = ref.FundamentalDiagram(15.0, 5.0, 0.15)
    results = [ref.solve_riemann(fd, left, right, 100.0, n_cells=n) for n in (100, 200, 400)]
    errors = [r["l1_profile_error_vehicles"] for r in results]
    assert errors[0] > errors[1] > errors[2] > 0
    for r in results:
        assert abs(r["mass_balance_error_vehicles"]) < 1e-9
        assert all(0 <= k <= 0.15 for k in r["density_veh_m"])


def test_uniform_state_is_stationary_and_cfl_is_fail_closed():
    ref = reference()
    fd = ref.FundamentalDiagram(15.0, 5.0, 0.15)
    result = ref.solve_riemann(fd, 0.04, 0.04, 100.0, n_cells=100)
    assert result["density_veh_m"] == pytest.approx((0.04,) * 100)
    with pytest.raises(ValueError, match="CFL"):
        ref.solve_riemann(fd, 0.02, 0.10, 100.0, cfl=1.01)
    capped = ref.FundamentalDiagram(15.0, 5.0, 0.15, 0.4)
    assert capped.flow(0.04) == pytest.approx(0.4)
    with pytest.raises(ValueError, match="triangular"):
        ref.exact_riemann_averages(capped, 0.02, 0.10, (-1.0, 1.0), 1.0)


def test_profile_norm_does_not_hide_a_subcell_shock():
    ref = reference()
    fd = ref.FundamentalDiagram(15.0, 5.0, 0.15)
    # Exact cell average is .06, but the step and its constant reconstruction differ.
    error = ref.exact_profile_l1(fd, 0.02, 0.10, (-1.0, 1.0), (0.06,), 0.0)
    assert error == pytest.approx(0.08)
