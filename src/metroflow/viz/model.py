from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class ViewFrame:
    sim_step: int
    weekday: bool
    minute_of_day: int
    edge_congestion: Tuple[float, ...] = tuple()
