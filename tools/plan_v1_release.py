"""Compile a bounded page of the real release calendar; never simulate pages independently."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'src'))
from tools.run_v1_acceptance import load_release_city  # noqa: E402
from metroflow.v1.activity import compile_activity  # noqa: E402
from metroflow.v1.factorized_demand import compile_factorized_demand  # noqa: E402
from metroflow.v1.release_plan import ReleasePlan  # noqa: E402


def plan_case(case, policy, count=16):
    city, row = load_release_city(case)
    homes = tuple(compile_activity(city,b.id) for b in city.face_graph.blocks if b.residents)
    jobs = tuple(compile_activity(city,b.id,'job') for b in city.face_graph.blocks if b.jobs)
    services = tuple(compile_activity(city,b.id,'service',service_stock=b.jobs) for b in city.face_graph.blocks if b.jobs)
    schedule = compile_factorized_demand(homes,jobs,services,day=case['day'],freight_kg=1000,
                                         worker_shortfall=policy)
    plan = ReleasePlan(city,schedule,max_sources=2,max_access_laws=8)
    cursor, page = plan.take(plan.cursor(),count)
    return dict(case=case['id'],city_identity=city.identity,schedule_identity=schedule.identity,
                source_sha256=row['source_sha256'],patch_sha256=row['patch_sha256'],
                requested_workers=schedule.requested_workers,allocated_workers=schedule.allocated_workers,
                unassigned_workers=schedule.unassigned_workers,residents=schedule.resident_stock,
                cursor=asdict(cursor),calendar_summary=plan.summary(cursor),page=[dict(id=p.leg.id,status=p.status,links=p.links,
                                               amounts=asdict(p.leg.amounts)) for p in page],
                compiled_legs=len(page),route_trees=plan.routes.tree_builds,
                units=dict(persons='person-leg amounts, outward and return counted separately',
                           vehicles='vehicle-leg amounts',cargo_kg='kg',resident_stock='persons'),
                simulated_s=0,full_campaign='NOT_RUN',
                scope='bounded exact calendar/route page, one shared runtime required for all activated routes')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case',required=True)
    p.add_argument('--count',type=int,default=16)
    p.add_argument('--out',type=Path,default=ROOT/'artifacts/v1_v03_joint_20261027')
    args=p.parse_args()
    matrix=json.loads((ROOT/'scenarios/v1/release_matrix.json').read_text())
    case=next(c for c in matrix['cases'] if c['id']==args.case)
    result=plan_case(case,matrix['worker_shortfall'],args.count)
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/(args.case+'.plan.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(case=result['case'],compiled_legs=result['compiled_legs'],
                         route_trees=result['route_trees'],simulated_s=0)))
