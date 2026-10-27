"""Construct explicitly new synthetic entrances on a frozen city.

Uniform planar activity, constant access speed, and 1 veh/s gate capacity are
engineering priors. Legal-turn connectivity is certified on link states; gate
capacity is not a full-day demand or receiving-supply certificate.
"""
from dataclasses import asdict
import math

from ..terrain_city.area_access import AreaAccess
from .access import activity_access
from .activity import compile_activity
from .city import CityContractError, PortalRef, reject
from .development import compile_entry


def _components(net):
    """Iterative Kosaraju on directed road-link states (linear graph cost)."""
    forward = {r.id: [] for r in net.roads}
    reverse = {r.id: [] for r in net.roads}
    for a, b in net.allowed_turns:
        forward[a].append(b)
        reverse[b].append(a)
    seen, order = set(), []
    for start in forward:
        if start in seen:
            continue
        seen.add(start)
        stack = [(start, iter(forward[start]))]
        while stack:
            key, iterator = stack[-1]
            nxt = next(iterator, None)
            if nxt is None:
                order.append(key)
                stack.pop()
            elif nxt not in seen:
                seen.add(nxt)
                stack.append((nxt, iter(forward[nxt])))
    seen, components = set(), []
    for start in reversed(order):
        if start in seen:
            continue
        component, stack = set(), [start]
        seen.add(start)
        while stack:
            key = stack.pop()
            component.add(key)
            for nxt in reverse[key]:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        components.append(frozenset(component))
    return components


def generate_entries(city, *, depth=0):
    """Return (new snapshot, report); failed blocks retain all resident mass.

    Every active block boundary vertex is tested. A candidate's corridor starts
    at an incident triangle centroid. One geometrically ordered valid candidate
    per block is constructed; IDs provide labels, never physical priorities.
    Existing entrance evidence is not inferred from an undeclared registry.
    """
    if city.portals:
        reject('synthetic construction requires a portal-free source snapshot')
    if depth not in (0, 1, 2):
        reject('registered access depth must be 0, 1 or 2')
    blocks = tuple(b for b in city.face_graph.blocks if b.residents or b.jobs)
    nodes = {n.id: n for n in city.roadmap.nodes}
    candidates = tuple(PortalRef(f'new:{b.id}:{n}', b.id, n) for b in blocks for n in b.boundary)
    provisional = city.with_portals(candidates)
    components = _components(city.transport_graph)
    # Equal-size components are selected by their physical road geometry.
    roads = {r.id: r for r in city.transport_graph.roads}
    def geometry(component):
        return tuple(sorted((nodes[roads[k].tail].xyz, nodes[roads[k].head].xyz)
                            for k in component))
    backbone = min(components, key=lambda c: (-len(c), geometry(c))) if components else frozenset()
    outgoing, incoming = {}, {}
    for key in backbone:
        road = roads[key]
        outgoing.setdefault(road.tail, []).append(key)
        incoming.setdefault(road.head, []).append(key)
    selected, evidence, failures = [], [], []
    for block in blocks:
        kind = 'residential' if block.residents else 'job'
        measure = compile_activity(provisional, block.id, kind)
        area = AreaAccess(measure.block_points)
        valid = []
        for node_id in block.boundary:
            xy = nodes[node_id].xyz[:2]
            if node_id not in outgoing or node_id not in incoming:
                failures.append(dict(block_id=block.id, node_id=node_id,
                                     reason='outside selected legal-turn component'))
                continue
            reasons = []
            for triangle in area.triangles:
                if xy not in triangle:
                    continue
                centre = tuple(math.fsum(p[i] for p in triangle) / 3 for i in (0, 1))
                corridor = (centre, xy)
                portal_id = f'new:{block.id}:{node_id}'
                try:
                    entry = compile_entry(provisional, measure, portal_id, capacity_veh_s=1.0,
                                          corridor=corridor, existing=False)
                except (CityContractError, ValueError) as exc:
                    reasons.append(str(exc))
                    continue
                valid.append((xy, corridor, entry))
                break
            else:
                failures.append(dict(block_id=block.id, node_id=node_id, reason=reasons))
        if valid:
            _, corridor, entry = min(valid, key=lambda row: (row[0], row[1]))
            selected.append(PortalRef(entry.id, block.id, entry.node_id))
            evidence.append(dict(**asdict(entry), corridor=corridor,
                                 departure_link=sorted(outgoing[entry.node_id])[0],
                                 arrival_link=sorted(incoming[entry.node_id])[0]))
    result = city.with_portals(tuple(selected))
    # Bind entry identities to the final immutable snapshot and revalidate.
    sample_rows, bounds = [], []
    for row in evidence:
        block = next(b for b in blocks if b.id == row['block_id'])
        measure = compile_activity(result, block.id, 'residential' if block.residents else 'job')
        entry = compile_entry(result, measure, row['id'], capacity_veh_s=1.0,
                              corridor=row['corridor'], existing=False)
        row['city_identity'] = entry.city_identity
        if block.residents:
            law, report = activity_access(measure, (entry.door,), depth=depth)
            sample_rows.extend((s['cost_s'], s['weight'] * block.residents, math.sqrt(12) * radius / 1.4)
                               for s, (_, _, radius) in zip(report['samples'], measure.quadrature(depth)))
            bounds.append(block.residents * law.quadrature_mean_bound_s)
    served = sum(b.residents for b in blocks if any(p.block_id == b.id for p in selected))
    total = city.requested_population
    unserved = total - served
    return result, dict(
        source_identity=city.identity, identity=result.identity,
        policy='new synthetic entrance per active block; uniform area access; speed 1.4 m/s; capacity 1 veh/s',
        existing=False, entries=evidence, candidate_failures=failures,
        registered_portal_count=len(selected), registered_served_residents=served,
        registered_unserved_residents=unserved,
        registered_access_status='PASS' if not unserved else 'PARTIAL_UNSERVED',
        registered_entry_validation_status='PASS' if len(selected) == len(blocks) else 'PARTIAL_UNSERVED',
        registered_connectivity_status='PASS' if len(selected) == len(blocks) else 'PARTIAL_UNSERVED',
        registered_access_cdf=[[t, math.fsum(w for cost, w, _ in sample_rows if cost <= t) / total
                                if total else 0.0] for t in (30, 60, 120, 300, 600)],
        registered_access_cdf_lower=[[t, math.fsum(w for cost, w, e in sample_rows if cost + e <= t) / total
                                     if total else 0.0] for t in (30, 60, 120, 300, 600)],
        registered_access_cdf_upper=[[t, math.fsum(w for cost, w, e in sample_rows if cost - e <= t) / total
                                     if total else 0.0] for t in (30, 60, 120, 300, 600)],
        cdf_bound_basis='1/speed Lipschitz geodesic inside each convex triangular cell; sqrt(12)*RMS radius bounds cell vertices',
        cdf_scope=f'depth{depth} area quadrature; denominator includes all requested residents; unserved remain outside CDF',
        quadrature_mean_bound_s=math.fsum(bounds) / total if total else 0.0,
        connectivity_basis='mutual reachability through one SCC of legal-turn directed-link states',
        backbone_links=len(backbone),
        capacity_scope='declared admission rate; receiving/storage and daily demand feasibility not tested')
