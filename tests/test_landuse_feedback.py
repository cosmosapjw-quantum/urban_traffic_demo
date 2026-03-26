from metroflow.landuse.evolution import apply_lagged_landuse_feedback


def test_lagged_feedback_shape():
    delta = apply_lagged_landuse_feedback((1.0, 2.0), (10.0, 20.0), (30.0, 40.0))
    assert len(delta.housing_delta) == 2
    assert len(delta.jobs_delta) == 2
