"""Quantile bounds retain the true rank without retaining timing samples."""
from functools import lru_cache

import pytest

from metroflow.active_suffix.routing import Arc, candidate_paths
import metroflow.route_metrics as metrics
from metroflow.v1.release_plan import LegalRouteCache


def test_histogram_encloses_exact_sorted_p99_at_bin_and_rank_edges():
    values = [0, 1, 127, 128, 255, 256, 257, 258, 511, 512, 513]
    values += [2**power + offset for power in range(10, 64)
               for offset in (-1, 0, 1, 2**(power-8)-1)]
    for size in (1, 2, 99, 100, 101, len(values)):
        sample = values[-size:]
        collector = metrics.RouteLatencyMeasurements()
        for duration in reversed(sample):
            collector.record_ns(duration, 'candidate_paths')
        report = collector.report()
        rank_value = sorted(sample)[(99*len(sample)+99)//100-1]
        bounds = report['p99_ns']
        assert bounds['lower'] <= rank_value <= bounds['upper']
        assert bounds['upper'] - bounds['lower'] <= max(0, bounds['lower']/128)
        assert report['observed_calls'] == len(sample)
        assert report['min_ns'] == min(sample)
        assert report['max_ns'] == max(sample)
    before = len(collector.counts)
    for _ in range(10000):
        collector.record_ns(100, 'candidate_paths')
    assert len(collector.counts) == before == 7425


def test_empty_and_saturated_measurements_do_not_invent_a_quantile():
    collector = metrics.RouteLatencyMeasurements()
    assert collector.report()['status'] == 'NOT_MEASURED'
    assert collector.report()['p99_ns'] is None
    for value in (2**64, 2**65, 2**66):
        collector.record_ns(value, 'candidate_paths')
    report = collector.report()
    assert report['overflow_samples'] == 3
    assert report['p99_ns'] == dict(lower=2**64, upper=2**66)
    with pytest.raises(ValueError):
        collector.record_ns(-1, 'candidate_paths')


def test_route_results_errors_and_nested_cache_hits_are_preserved(monkeypatch):
    arcs = (Arc('a','O','A'), Arc('b','A','D'))
    costs = dict(a=1, b=1)
    expected = candidate_paths(arcs, costs, 'O', 'D', 1)
    times = iter((10, 110, 200, 201, 300, 350))
    monkeypatch.setattr(metrics, 'perf_counter_ns', lambda: next(times))

    @metrics.measure_route_latency('release_runtime.path')
    @lru_cache(maxsize=1)
    def path(origin, destination):
        return candidate_paths(arcs, costs, origin, destination, 1)

    with metrics.RouteLatencyMeasurements() as collector:
        assert path('O','D') == expected
        assert path('O','D') == expected
        with pytest.raises(ValueError, match='budget'):
            candidate_paths(arcs, costs, 'O', 'D', 0)
    report = collector.report()
    assert report['observed_calls'] == 3
    assert report['failed_calls'] == 1
    assert report['calls_by_api']['release_runtime.path'] == 2
    assert report['calls_by_api']['candidate_paths'] == 1
    assert report['p99_ns'] == dict(lower=100, upper=100)
    assert report['min_ns'] == 1
    # Context exit restores the disabled path: no clock reads are made.
    assert candidate_paths(arcs, costs, 'O', 'D', 1) == expected


def test_legal_source_cache_misses_hits_and_unreachable_queries_all_count():
    arcs = (Arc('a','O','A'), Arc('b','A','D'))
    cache = LegalRouteCache(arcs, dict(a=1,b=1), {('a','b')})
    with metrics.RouteLatencyMeasurements() as collector:
        assert cache.resolve('O','D') == ('a','b')
        assert cache.resolve('O','D') == ('a','b')
        assert cache.resolve('D','O') is None
    report = collector.report()
    assert cache.tree_builds == 2
    assert report['observed_calls'] == 3
    assert report['calls_by_api']['legal_route_cache.resolve'] == 3
    assert report['failed_calls'] == 0
    assert report['p99_ns']['lower'] <= report['max_ns'] <= report['p99_ns']['upper']
