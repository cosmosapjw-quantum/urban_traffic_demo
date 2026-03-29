from metroflow.metrics.benchmarks import run_city_smoke_benchmark


def test_city_smoke_benchmark_populates_proxy_scores():
    bench = run_city_smoke_benchmark(population=100_000, edge_count=12_500, zone_count=64)

    assert bench.name == "city100k-smoke"
    assert bench.step_proxy_score > 0.0
    assert bench.state_proxy_score > 0.0
    assert bench.signature == "100000:12500:64"
