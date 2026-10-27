"""P01: observed quotient must commute with actual finite-response transport."""
import pytest
from metroflow.v1.timing_oracles import timing_fixture
from metroflow.v1.transport import FiniteResponseMotion


@pytest.mark.parametrize('window', [0.0, 1.0])
def test_inactive_link_shortcut_matches_original_complete_state(monkeypatch, window):
    model = timing_fixture(0.1, mass=2.0, window=window)
    initial = model.initial()
    accelerated = model.advance(initial, 35.0)
    monkeypatch.setattr(FiniteResponseMotion, 'empty_stationary', False)
    reference = model.advance(initial, 35.0)
    assert accelerated == reference
    assert model.report(accelerated) == model.report(reference)
    assert accelerated.road.completed == pytest.approx(2.0)
    assert accelerated.peak_records < model.record_budget
