"""Independent continuum oracle tests, separate from integer vehicle claims."""
import importlib
import importlib.util
import math
import pytest


def reference():
    name='metroflow.pure_traffic.fluid_reference'
    assert importlib.util.find_spec(name) is not None, 'continuous Godunov reference is not implemented'
    return importlib.import_module(name)


def test_exact_triangle_shock_and_expansion_cell_averages():
    ref=reference()
    fd=ref.FundamentalDiagram(15.,5.,.15)
    assert fd.critical_density == pytest.approx(.0375)
    assert fd.capacity == pytest.approx(.5625)
    assert ref.exact_riemann_averages(fd,.02,.10,(-100.,-62.5,0.),100.) == pytest.approx((.02,.10))
    assert ref.exact_riemann_averages(fd,.12,.01,(-1000.,-500.,1500.,2000.),100.) == pytest.approx((.12,.0375,.01))


@pytest.mark.parametrize('left,right',[(.02,.10),(.12,.01)])
def test_godunov_refinement_reduces_integrated_density_error(left,right):
    ref=reference(); fd=ref.FundamentalDiagram(15.,5.,.15)
    results=[ref.solve_riemann(fd,left,right,100.,n_cells=n) for n in (100,200,400)]
    errors=[r['l1_profile_error_vehicles'] for r in results]
    assert errors[0] > errors[1] > errors[2] > 0
    for r in results:
        assert abs(r['mass_balance_error_vehicles']) < 1e-9
        assert all(0 <= k <= .15 for k in r['density_veh_m'])


def test_uniform_state_is_stationary_and_cfl_is_fail_closed():
    ref=reference(); fd=ref.FundamentalDiagram(15.,5.,.15)
    result=ref.solve_riemann(fd,.04,.04,100.,n_cells=100)
    assert result['density_veh_m'] == pytest.approx((.04,)*100)
    with pytest.raises(ValueError,match='CFL'):
        ref.solve_riemann(fd,.02,.10,100.,cfl=1.01)
    capped=ref.FundamentalDiagram(15.,5.,.15,.4)
    assert capped.flow(.04) == pytest.approx(.4)
    with pytest.raises(ValueError,match='triangular'):
        ref.exact_riemann_averages(capped,.02,.10,(-1.,1.),1.)


def test_profile_norm_does_not_hide_a_subcell_shock():
    ref=reference(); fd=ref.FundamentalDiagram(15.,5.,.15)
    # Exact cell average is .06, but the step and its constant reconstruction differ.
    error=ref.exact_profile_l1(fd,.02,.10,(-1.,1.),(.06,),0.)
    assert error == pytest.approx(.08)
