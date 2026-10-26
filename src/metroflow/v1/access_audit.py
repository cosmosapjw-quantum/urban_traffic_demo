"""Small deterministic M03 acceptance matrix; not the V02 city release audit."""

import math
from ..environment.terrain import Terrain
from ..restored_city import Junction, RoadMap, Section
from ..terrain_city.area_access import AreaAccess, Portal
from ..terrain_city.network import Block
from .city import PortalRef, compile_city
from .activity import ActivityPatch, compile_activity, intrazonal_law
from .access import activity_access
from .development import compile_entry, select_entries


def fixture_city(scale=1.0):
    points = tuple(
        (x * scale, y * scale)
        for x, y in (
            (10.0, 10.0),
            (310.0, 10.0),
            (310.0, 110.0),
            (110.0, 110.0),
            (110.0, 310.0),
            (10.0, 310.0),
        )
    )
    nodes = tuple(Junction(str(i), (*p, 0.0)) for i, p in enumerate(points))
    sections = tuple(
        Section(
            str(i),
            a.id,
            b.id,
            (a.xyz, b.xyz),
            "local",
            "surface",
            1,
            1,
            math.dist(a.xyz, b.xyz),
            0.0,
        )
        for i, (a, b) in enumerate(zip(nodes, nodes[1:] + nodes[:1]))
    )
    area = AreaAccess(points)
    block = Block(
        "block",
        tuple(n.id for n in nodes),
        area.centroid,
        area.area_m2,
        sum(s.length_m for s in sections),
        "mixed",
        1000,
        200,
        1000,
        200,
    )
    road = RoadMap("access-audit", Terrain(1, 1000.0 * scale, (0.0,) * 4), nodes, sections)
    return compile_city(
        road,
        blocks=(block,),
        portals=(PortalRef("east", "block", "1"), PortalRef("north", "block", "5")),
    )


def access_matrix():
    rows = []
    for scale in (1.0, 2.0, 4.0):
        c = fixture_city(scale)
        def p(x, y):
            return x * scale, y * scale
        m = compile_activity(
            c,
            "block",
            patches=(ActivityPatch(800, (p(280, 40),)), ActivityPatch(200, (p(40, 280),))),
        )
        doors = (Portal("east", p(310, 10)), Portal("north", p(10, 310)))
        law, report = activity_access(m, doors)
        single, _ = activity_access(m, doors[:1])
        entries = tuple(
            compile_entry(c, m, g, capacity_veh_s=1.0, corridor=(start, end))
            for g, start, end in (
                ("east", p(280, 40), p(310, 10)),
                ("north", p(40, 280), p(10, 310)),
            )
        )
        choice = select_entries(
            m,
            entries,
            construction_budget_m=100 * scale,
            max_distance_m=100 * scale,
            forecast_vehicles=100,
            horizon_s=100,
        )
        a = compile_activity(c, "block", patches=(ActivityPatch(1000, (p(280, 40),)),))
        b = compile_activity(c, "block", patches=(ActivityPatch(1000, (p(40, 280),)),))
        internal = intrazonal_law(a, b).atoms[0][0]
        uniform = compile_activity(c, "block")
        coarse, cr = activity_access(uniform, doors, depth=1, bin_s=20.0)
        fine, fr = activity_access(uniform, doors, depth=2, bin_s=20.0)
        split = compile_activity(
            c,
            "block",
            patches=tuple(ActivityPatch(q.mass / 4, q.points) for q in m.patches for _ in range(4)),
        )
        splitlaw, _ = activity_access(split, doors)
        passed = (
            choice["status"] == "PASS"
            and internal > 0
            and single.mean_s > law.mean_s
            and m.mass == split.mass
            and abs(law.mean_s - splitlaw.mean_s) < 1e-9
            and abs(coarse.mean_s - fine.mean_s)
            <= coarse.quadrature_mean_bound_s + fine.quadrature_mean_bound_s
        )
        rows.append(
            dict(
                status="PASS" if passed else "NOT_ACCEPTED",
                scale=scale,
                city_identity=c.identity,
                activity_mass=m.mass,
                split_mass=split.mass,
                mean_s=law.mean_s,
                nearest_single_door_mean_s=single.mean_s,
                portal_probability=dict(law.portal_weights()),
                intrazonal_s=internal,
                uniform_refinement=dict(
                    mean_delta_s=abs(coarse.mean_s - fine.mean_s),
                    mean_bound_s=coarse.quadrature_mean_bound_s + fine.quadrature_mean_bound_s,
                    variance_delta_s2=abs(coarse.original_variance_s2 - fine.original_variance_s2),
                    p95_delta_s=abs(cr["p95_quadrature_s"] - fr["p95_quadrature_s"]),
                    quantile_certificate="NOT_CERTIFIED",
                ),
                selection=choice,
            )
        )
    return rows
