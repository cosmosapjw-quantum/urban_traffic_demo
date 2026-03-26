from metroflow.demand.accessibility import compute_accessibility_placeholder


def test_accessibility_placeholder():
    snap = compute_accessibility_placeholder()
    assert snap.computed_at_step == 0
