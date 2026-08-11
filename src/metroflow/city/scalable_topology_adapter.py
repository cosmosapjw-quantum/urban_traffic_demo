from __future__ import annotations

from metroflow.city.scalable_blocks import ScalableBlockAuthority
from metroflow.city.scalable_topology import ScalableStreetNetwork

__all__ = (
    "ScalableCompiledTopology",
    "ScalableGroupCrosswalk",
    "ScalableNumericProfile",
    "ScalableRoadCrosswalk",
    "compile_scalable_topology",
    "require_valid_scalable_compiled_topology",
)


class ScalableCompiledTopology:
    pass


class ScalableGroupCrosswalk:
    pass


class ScalableNumericProfile:
    pass


class ScalableRoadCrosswalk:
    pass


def _lower_scalable_records(*, nodes, roads):
    raise NotImplementedError(
        "S1_OWNER_RED: pure scalable lowering is not implemented"
    )


def compile_scalable_topology(
    network: ScalableStreetNetwork,
    *,
    block_authority: ScalableBlockAuthority,
) -> ScalableCompiledTopology:
    raise NotImplementedError


def require_valid_scalable_compiled_topology(
    compiled: ScalableCompiledTopology,
    *,
    network: ScalableStreetNetwork,
    block_authority: ScalableBlockAuthority,
) -> None:
    raise NotImplementedError(
        "S6_OWNER_RED: current-content validation is not implemented"
    )
