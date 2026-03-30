import metroflow.metrics.benchmarks as benchmark_module
from metroflow.metrics.benchmarks import BenchmarkResult, run_city_smoke_benchmark


def test_city_smoke_benchmark_populates_proxy_scores():
    bench = run_city_smoke_benchmark(population=100_000, edge_count=12_500, zone_count=64)

    assert bench.name == "city100k-smoke"
    assert bench.step_proxy_score > 0.0
    assert bench.state_proxy_score > 0.0
    assert bench.signature == "100000:12500:64"


def test_city_smoke_benchmark_remains_proxy_only():
    bench = run_city_smoke_benchmark(population=100_000, edge_count=12_500, zone_count=64)

    assert isinstance(bench, BenchmarkResult)
    assert not bench.name.startswith("measured_")
    assert hasattr(bench, "step_proxy_score")
    assert hasattr(bench, "state_proxy_score")
    assert not hasattr(bench, "wall_clock_ns")


def test_city_smoke_benchmark_does_not_adopt_runtime_routing_integration(monkeypatch):
    def fail_if_wrapper_called(*args, **kwargs):
        raise AssertionError("proxy benchmark must not call step_world_with_routing")

    monkeypatch.setattr(benchmark_module, "step_world_with_routing", fail_if_wrapper_called, raising=False)

    bench = run_city_smoke_benchmark(population=100_000, edge_count=12_500, zone_count=64)

    assert bench.name == "city100k-smoke"
    assert not bench.name.startswith("measured_")
