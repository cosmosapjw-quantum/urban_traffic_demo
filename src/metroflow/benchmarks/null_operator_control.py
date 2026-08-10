"""A control arm that deletes streets at random and knows nothing else.

The morphology envelope orders the generator arms, and that ordering is the
evidence behind every proposal to rebuild one of them. Before spending a rebuild
on it, the instrument needs a control: an operator that produces no urban
information at all, applied to an arm the envelope rejects. If the envelope then
accepts the result, a passing score does not mean what its use implies.

This operator is handed a compiled topology and deletes a seeded fraction of its
undirected streets. That is the whole algorithm. It has no access to terrain,
form fields, land use, districts or road hierarchy -- `tests/
test_null_operator_control.py` asserts that this file never mentions them, so the
claim "information-free" stays true by test rather than by intention.

Weak connectivity is preserved by construction. An operator that passed the
envelope by shattering the network would be a curiosity; the sharp question is
whether the envelope can be satisfied while the graph stays whole, because that
is the failure a reader of a passing score would not suspect.

This is an instrument control, not a generator. Nothing here may be promoted,
and no map it produces is a city.
"""

from __future__ import annotations

import random
from typing import Any

from metroflow.city.connectivity import analyze_weak_connectivity
from metroflow.city.generated_map import PreviewCityTopology
from metroflow.map.road_geometry import RoadGeometryCatalog

__all__ = ["thin_topology"]


def _undirected_key(link: Any) -> tuple[int, int]:
    src = int(link.src_node_id)
    dst = int(link.dst_node_id)
    return (src, dst) if src <= dst else (dst, src)


def thin_topology(
    topology: PreviewCityTopology,
    *,
    removal_fraction: float,
    seed: int,
) -> PreviewCityTopology:
    """Delete `removal_fraction` of undirected streets, keeping the graph whole.

    Both directions of a street go together: removing one carriageway and
    leaving the other would be a directedness experiment, not a street-deletion
    one, and the morphometrics are measured on the undirected graph anyway.

    A candidate whose removal would raise the weak-component count is put back.
    The realised fraction is therefore at most the requested one, and is
    reported in metadata rather than assumed -- a control that quietly removed
    less than it claimed would understate its own result.
    """

    fraction = float(removal_fraction)
    if not 0.0 <= fraction < 1.0:
        raise ValueError("removal_fraction must be in [0, 1)")

    nodes = tuple(topology.nodes)
    links = tuple(topology.links)

    groups: dict[tuple[int, int], list[Any]] = {}
    for link in links:
        groups.setdefault(_undirected_key(link), []).append(link)

    order = sorted(groups)
    random.Random(seed).shuffle(order)
    target = int(len(order) * fraction)

    surviving = dict(groups)
    removed = 0
    for key in order:
        if removed >= target:
            break
        candidate = dict(surviving)
        del candidate[key]
        kept = tuple(link for group in candidate.values() for link in group)
        if not kept:
            continue
        if analyze_weak_connectivity(nodes=nodes, links=kept).component_count > 1:
            # Putting it back is the point: a network that passes by falling
            # apart would answer a question nobody asked.
            continue
        surviving = candidate
        removed += 1

    kept_links = tuple(
        sorted(
            (link for group in surviving.values() for link in group),
            key=lambda item: int(item.link_id),
        )
    )
    kept_link_ids = {int(link.link_id) for link in kept_links}

    geometry = _restrict_geometry(topology.road_geometry, kept_link_ids)

    metadata = dict(topology.metadata)
    metadata.update(
        {
            "engine": "null_thinned_v1",
            "null_operator": "uniform_random_undirected_street_deletion",
            "null_operator_requested_fraction": fraction,
            "null_operator_realised_fraction": (
                removed / len(order) if order else 0.0
            ),
            "null_operator_seed": int(seed),
            "evidence_status": "instrument_control_not_a_generator",
        }
    )

    return PreviewCityTopology(
        nodes=nodes,
        links=kept_links,
        road_geometry=geometry,
        metadata=metadata,
    )


def _restrict_geometry(
    geometry: RoadGeometryCatalog | None,
    kept_link_ids: set[int],
) -> RoadGeometryCatalog | None:
    """Keep the surviving assignments and the centerlines they still name.

    The catalog requires its assignments to cover the links exactly, so a
    filtered link set needs a filtered catalog; rebuilding one from node
    coordinates instead would replace measured polylines with chords and change
    what the instrument reads.
    """

    if geometry is None:
        return None
    assignments = tuple(
        item for item in geometry.assignments if int(item.link_id) in kept_link_ids
    )
    referenced = {int(item.geometry_id) for item in assignments}
    centerlines = tuple(
        item for item in geometry.centerlines if int(item.geometry_id) in referenced
    )
    return RoadGeometryCatalog(centerlines=centerlines, assignments=assignments)
