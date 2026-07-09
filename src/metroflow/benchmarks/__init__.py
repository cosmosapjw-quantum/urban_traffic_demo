__all__ = [
    "execute_benchmark",
    "run_benchmark",
    "run_benchmark_scenario",
    "run_hardware_atlas",
    "run_runtime_benchmark_suite",
]


def __getattr__(name: str):
    if name in {
        "execute_benchmark",
        "run_benchmark",
        "run_benchmark_scenario",
        "run_hardware_atlas",
        "run_runtime_benchmark_suite",
    }:
        from metroflow.benchmarks.run import (
            execute_benchmark,
            run_benchmark,
            run_benchmark_scenario,
            run_hardware_atlas,
            run_runtime_benchmark_suite,
        )

        return {
            "execute_benchmark": execute_benchmark,
            "run_benchmark": run_benchmark,
            "run_benchmark_scenario": run_benchmark_scenario,
            "run_hardware_atlas": run_hardware_atlas,
            "run_runtime_benchmark_suite": run_runtime_benchmark_suite,
        }[name]
    raise AttributeError(name)
