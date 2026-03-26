from typing import Iterable


def mean_positive(values: Iterable[float]) -> float:
    vals = [v for v in values if v >= 0]
    if not vals:
        return 0.0
    return sum(vals) / len(vals)
