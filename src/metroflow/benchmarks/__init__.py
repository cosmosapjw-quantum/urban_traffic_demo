__all__ = [
    "execute_benchmark",
    "run_benchmark",
    "run_benchmark_scenario",
]


def __getattr__(name: str):
    if name in {"execute_benchmark", "run_benchmark", "run_benchmark_scenario"}:
        from metroflow.benchmarks.run import (
            execute_benchmark,
            run_benchmark,
            run_benchmark_scenario,
        )

        return {
            "execute_benchmark": execute_benchmark,
            "run_benchmark": run_benchmark,
            "run_benchmark_scenario": run_benchmark_scenario,
        }[name]
    raise AttributeError(name)
