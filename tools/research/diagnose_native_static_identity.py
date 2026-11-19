from pathlib import Path
import json,hashlib,os
from tools.run_v1_acceptance import load_release_city
from metroflow.v1.activity import compile_activity
from metroflow.v1.factorized_demand import compile_factorized_demand
from metroflow.v1.release_inventory import InventoryPolicy,build_inventory
from metroflow.v1.release_plan import ReleasePlan
from metroflow.v1.native_static import prepare_native_static
matrix=json.load(open('scenarios/v1/release_matrix.json'))
case=next(c for c in matrix['cases'] if c['id']=='valley_weekday_s7')
city,row=load_release_city(case)
homes=tuple(compile_activity(city,b.id) for b in city.face_graph.blocks if b.residents)
jobs=tuple(compile_activity(city,b.id,'job') for b in city.face_graph.blocks if b.jobs)
services=tuple(compile_activity(city,b.id,'service',service_stock=b.jobs) for b in city.face_graph.blocks if b.jobs)
schedule=compile_factorized_demand(homes,jobs,services,day=case['day'],freight_kg=1000,worker_shortfall=matrix['worker_shortfall'])
plan=ReleasePlan(city,schedule,step_s=10.0)
policy=dict(matrix['inventory_policy']);policy['departures_s']=tuple(policy['departures_s'])
inv=build_inventory(city,InventoryPolicy(**policy))
s=prepare_native_static(city,schedule,inv,step_s=10.0,record_budget=20000,event_budget=20000)
seed=os.environ.get('PYTHONHASHSEED','random')
out='/tmp/v03_static_seed_'+seed+'.json'
Path(out).write_text(json.dumps(s,sort_keys=True))
print('SEED',seed,'STATIC_SHA',s['identity'],'CITY',city.identity,'SCHED',schedule.identity,'INVENTORY',inv.identity)
for key in sorted(s):
 txt=json.dumps(s[key],sort_keys=True)
 print('FIELD',key,len(txt),hashlib.sha256(txt.encode()).hexdigest()[:20])
