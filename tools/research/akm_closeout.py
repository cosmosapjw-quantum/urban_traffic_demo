#!/usr/bin/env python3
"""Verify AKM initial research receipts and artifact identities; no simulation mutation."""
import argparse, hashlib,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('backup',type=Path);p.add_argument('--output',type=Path,required=True);ns=p.parse_args()
r=Path(__file__).resolve().parents[2]; a=r/'artifacts/active_kinetic_meso_20261128'; b=ns.backup
def read(n):return json.loads((a/n).read_text())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
lab=read('C08_lab_results.json')
assert len(lab['results'])==12 and lab['replayed_case_indices']==[1,6]
for x in lab['results']:
    assert x['status']=='HORIZON_REACHED' and x['time_s']==x['scenario']['horizon']
    assert x['slots']==12 and x['allocation_calls']==x['reallocation_calls']==0
    assert abs(x['released']-x['completed']-x['active']-x['pending'])<1e-6
    assert x['metrics']['max_storage']<=1+1e-12
for i in [1,6]:
    assert sha(b/'lab'/f'lab-{i}-final.bin')==lab['results'][i]['checkpoint_sha256']
    assert (b/'lab'/f'lab-{i}-mid.bin').is_file()
assert sha(b/'metroflow-active-lab')==lab['executable_sha256']
city=[read(x) for x in ['C08_city_active28800.json','C08_city_active86400.json','C08_city_zero86400.json']]
for d in city:
    assert d['network_sha256']==sha(b/'network.txt') and d['passages_sha256']==sha(b/'passages.txt')
    assert d['executable_sha256']==sha(b/'metroflow-active-city')
    assert d['result']['snapshots'][-1]['time_s']==d['config']['horizon_s']
    for snap in d['result']['snapshots']:
        assert snap['max_storage_ratio']<=1+1e-9 and snap['max_receiving_ratio']<=1+1e-9
        for c in snap['classes']:
            assert abs(c['released']-c['completed']-c['active'])<1e-7 and abs(c['error'])<1e-7
for d in city[1:]:
    assert all(c['completed']==c['expected'] and c['active']==0 for c in d['result']['snapshots'][-1]['classes'])
old=json.loads((r/'artifacts/v03_rust_only_backend_20261126/rust_1200_86400_8.json').read_text())
zero=dict(city[2]['result']); stats=zero.pop('active_mobility')
assert stats['min_mobility']==1 and stats['added_passage_veh_s']==0
assert zero==old['result']
assert city[1]['config']==city[2]['config'] and city[1]['policy']['beta']==.6 and city[2]['policy']['beta']==0
micro=read('R07_micro_pdmp.json'); assert micro['samples_per_time']==100000 and all(x['within_joint_hoeffding_plus_numerical_tolerance'] for x in micro['results'])
assert sha(b/'metroflow-active-micro')==micro['executable_sha256']
rational=read('R07_independent_oracle.json');assert rational['status']=='PASS' and rational['rational_pushforwards']==1024
resp=read('R07_response_oracle.json');assert max(x['relative_error'] for x in resp['results'])<1e-4
log=(a/'C09_headless_tests.log').read_text()
assert '14 passed; 0 failed' in log and '1 passed; 0 failed' in log
assert 'pyo3' not in (a/'C09_cargo_tree.txt').read_text().lower()
baseline='f3e13c2b0251f97c1fd5da601ab8995d44ec2f5c'
oldplan=json.loads(subprocess.check_output(['git','show',baseline+':docs/v1/PLAN.json'],cwd=r))
newplan=json.loads((r/'docs/v1/PLAN.json').read_text())
assert newplan['version']=='1.1.55' and newplan['authority']!=oldplan['authority']
# All substantive original release data exactly equal. Only authority/policy note/version/date changed.
assert {k:v for k,v in newplan.items() if k not in {'version','date','authority','policy_changes'}}=={k:v for k,v in oldplan.items() if k not in {'version','date','authority','policy_changes'}}
assert newplan['policy_changes'][:-1]==oldplan['policy_changes']
assert subprocess.check_output(['git','diff',baseline,'--','crates/metroflow-rust'],cwd=r)==b''
active,zero=city[1:];c1=active['result']['snapshots'][-1]['classes'][0];c0=zero['result']['snapshots'][-1]['classes'][0]
d=lab['results']
res={'schema':'akm-research-receipt-v1','status':'VERIFIED_SCOPED_NOT_RELEASE','baseline':baseline,'research_branch':'research/active-kinetic-meso-20261128','scope':'R01-R10 and C01-C10 one bounded execution; grouped verified milestones not 20 separate pushes. A synthetic fixed-support moment and B archived projected city only. Original V03 unchanged.',
     'research_ssot':'docs/akm/RESEARCH_SSOT_KO.md','theory':'docs/research/ACTIVE_KINETIC_MESO_THEORY_20261128.md','stages':{'theory':10,'coding':10,'scope':'stage execution, not full implementation acceptance'},'research_dag':{'total':14,'verified_scoped':4,'ready':['D04','D06'],'remaining_attempts':20,'max_attempts':24},
     'original_release':{'plan_version':'1.1.55','original_release_fields_unchanged':True,'scoped_or_accepted':19,'accepted':5,'total':21,'native_rust_scoped':14,'native_rust_total':15,'full_day_accepted':0,'full_day_required':9,'matched_8h_accepted':0,'matched_8h_required':3,'original_frontier_s':25750,'original_status':'BLOCKED','exact_engine_diff_empty':True},
     'verified':{'lab_cases':12,'lab_zero_hot_advance_allocs':True,'lab_replay_file_digests':[d[i]['checkpoint_sha256'] for i in [1,6]],'max_mass_error':max(x['metrics']['max_mass_error'] for x in d),'max_birth_error':max(x['metrics']['max_birth_error'] for x in d),'full_day_dt_mean_gap_relative_coarse':abs(d[11]['completed_conditional_mean_s']/d[6]['completed_conditional_mean_s']-1),'zero_vs_historical_result_payload_equal':True,'active_car_mean_s':c1['trip_seconds']/c1['completed'],'zero_car_mean_s':c0['trip_seconds']/c0['completed'],'active_city_full_day_wall_s':active['wall_s'],'zero_city_full_day_wall_s':zero['wall_s'],'micro_comparison':True,'response_check':resp,'headless_tests':15},
     'not_claimed':['A strict FIFO, full-city adapter or physical convergence','B current original schedule, full passenger/land-use, refined departure mesh or city restart','calibrated real-world model','V03 accepted, full CI or main merge','native independent subagent review'],
     'limitations':['authored hazard and frozen-entry mean passage','A underutilized receiving and non-negligible synthetic day refinement gap','B archive inputs fixed route and 1200s mesh','AXIOMATIC_FOUNDATIONS_KO.md v0.1 unavailable'],
     'source_sha256':{str(x.relative_to(r)):sha(x) for x in sorted((r/'crates/metroflow-headless/src').rglob('*.rs'))},
     'evidence_sha256':{x.name:sha(x) for x in sorted(a.iterdir()) if x.is_file() and x.name not in {'C10_RESEARCH_RECEIPT.json','C10_verify.log'}},
     'milestones':subprocess.check_output(['git','log','--format=%H %s',baseline+'..HEAD'],cwd=r,text=True).splitlines()}
ns.output.write_text(json.dumps(res,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({k:res[k] for k in ('status','stages','research_dag','original_release','verified')},indent=2,ensure_ascii=False))
