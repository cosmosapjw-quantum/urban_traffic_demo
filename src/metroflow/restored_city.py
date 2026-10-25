"""Bounded restoration of physical road grammars (research, not default)."""

from dataclasses import dataclass
from .environment.terrain import Terrain, synthetic_terrain as synthetic_terrain


@dataclass(frozen=True, slots=True)
class Junction:
    id: str
    xyz: tuple[float, float, float]
    layer: int = 0


@dataclass(frozen=True, slots=True)
class Section:
    id: str
    start: str
    end: str
    points: tuple[tuple[float, float, float], ...]
    hierarchy: str
    facility: str
    forward_lanes: int
    backward_lanes: int
    length_m: float
    max_grade: float
    failure_group: str | None = None
    ramp_purpose: str | None = None


@dataclass(frozen=True, slots=True)
class RoadMap:
    style: str
    terrain: Terrain
    nodes: tuple[Junction, ...]
    sections: tuple[Section, ...]
    rejected: tuple[tuple[str, int], ...] = ()


STYLES = ("grid_core", "organic", "superblock_mixed", "ring_radial")


def generate(style="grid_core", n=12, seed=17, interchanges=True):
    from .restored_grammar import build

    return build(style, n, seed, interchanges)
