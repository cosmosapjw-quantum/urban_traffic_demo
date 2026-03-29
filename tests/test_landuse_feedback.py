import pytest

from metroflow.landuse.evolution import (
    apply_landuse_delta,
    apply_lagged_landuse_feedback,
    reduce_zonal_costs_to_lagged_accessibility,
)


def test_lagged_feedback_shape():
    delta = apply_lagged_landuse_feedback((1.0, 2.0), (10.0, 20.0), (30.0, 40.0))
    assert len(delta.housing_delta) == 2
    assert len(delta.jobs_delta) == 2


def test_lagged_feedback_rejects_shape_mismatch():
    with pytest.raises(ValueError, match="must align"):
        apply_lagged_landuse_feedback((1.0,), (10.0, 20.0), (30.0, 40.0))


def test_apply_landuse_delta_keeps_capacities_non_negative():
    delta = apply_lagged_landuse_feedback((2.0, 4.0), (10.0, 20.0), (30.0, 40.0), gain=0.5)
    next_housing, next_jobs = apply_landuse_delta((10.0, 20.0), (30.0, 40.0), delta)

    assert next_housing == (11.0, 22.0)
    assert next_jobs == (31.0, 42.0)


def test_reduce_zonal_costs_to_lagged_accessibility_uses_inverse_mean_cost():
    reduced = reduce_zonal_costs_to_lagged_accessibility(((2.0, 4.0), (3.0, 9.0)))

    assert reduced == (1.0 / 3.0, 1.0 / 6.0)


def test_reduce_zonal_costs_to_lagged_accessibility_rejects_malformed_matrix():
    with pytest.raises(ValueError, match="zonal_costs rows must match"):
        reduce_zonal_costs_to_lagged_accessibility(((1.0,), (2.0, 3.0)))
