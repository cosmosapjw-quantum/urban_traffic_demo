from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkResult:
    name: str
    step_latency_ms: float
    memory_mb: float
    note: str = ""
