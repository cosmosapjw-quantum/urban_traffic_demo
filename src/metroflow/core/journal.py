from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class InterventionRecord:
    step: int
    kind: str
    payload: str = ""


@dataclass(frozen=True)
class InterventionJournal:
    records: Tuple[InterventionRecord, ...] = field(default_factory=tuple)
