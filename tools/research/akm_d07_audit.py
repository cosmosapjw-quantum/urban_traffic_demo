"""Independent D07 artifact-level legality, causality and paired outcome checks."""
from collections import Counter, defaultdict
from pathlib import Path
import hashlib,json,math,sys
A=Path('artifacts/akm_d07_causal_routing_20261128');B=Path(sys.argv[1])
def load(p):return json.loads(p.read_bytes())
def get(n):return load(A/(n+'.json'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
IDS=['approach','bridge','upper_exit','long','lower_exit','bypass','exit']
L=dict(zip(IDS,[150,60,60,130,130,100,80]))
PATHS={x[1]:x for x in [['approach','bridge','upper_exit','exit'],['approach','long','lower_exit','exit'],['approach','bypass','exit']]}
def close(a,b,tol=1e-9):return abs(a-b)<=tol*max(1.,abs(a),abs(b))
def rank(i,seed):
 mask=2**64-1;x=(i+seed+0x9e3779b97f4a7c15)&mask
 x=((x^(x>>30))*0xbf58476d1ce4e5b9)&mask
 x=((x^(x>>27))*0x94d049bb133111eb)&mask
 return (x^(x>>31))//2048/2**53
def audit(n):
 r=get(n);c=r['config'];gap=c['interarrival_s'];N=600//gap
 assert r['status']=='EXECUTED_FOR_REVIEW' and r['time_s']==1800
 assert r['checkpoint_sha256']==sha(B/(n+'.bin')) and r['executable_sha256']==sha(B/'metroflow-akm-d07')
 wire=load(B/(n+'.bin'));assert wire['schema']=='AKMD07LAB1' and wire['model']==r['model_identity'] and wire['world']['config']==c
 for k in ['owners','epochs','reroutes','samples','physical','graph_events','graph']:assert r[k]==wire['world'][k]
 assert r['peak_rss_kib']*1024<8*1024**3 and r['wall_s']<=120
 graph=r['graph_events'];p=r['physical'];os=r['owners'];rr=r['reroutes'];epochs=r['epochs'];sample=r['samples']
 assert len(os)==N and [o['id'] for o in os]==list(range(N))
 assert [o['birth'] for o in os]==list(range(0,600,gap))
 assert all(o['phase']==2 and o['done']>=o['birth'] and o['done']<=1800 for o in os)
 assert all(close(sum(o['moment']['m']),1) and close(o['moment']['birth'],o['birth']) for o in os)
 assert all(0<=p[k]<=1+1e-9 for k in ['peak_storage','peak_send','peak_receive','peak_metre'])
 assert [x['time_s'] for x in sample]==list(range(60,1801,60))
 for s in sample:
  assert s['released']==s['completed']+s['pending']+s['on_road']
  assert s['released']==sum(o['birth']<s['time_s'] for o in os)
  assert s['completed']==sum(o['done']<=s['time_s'] for o in os)
  assert all(0<=v<=1.5*L[i]+1e-8 for i,v in zip(IDS,s['stock_m']))
 assert sample[-1]==r['last_sample'] and sample[-1]['completed']==N
 ages={o['id']:o['done']-o['birth'] for o in os}
 assert close(sum(ages.values()),p['stock_integral']) and close(sum(ages.values())/N,r['mean_completed_s'])
 passages=defaultdict(list);window=defaultdict(list)
 for x in p['passages']:
  i=IDS[x['link']];passages[x['owner']].append(x)
  assert x['exited']-x['entered']>=L[i]/10
  window[(math.ceil(x['exited']/20)*20,i)].append(x)
 assert close(p['boundary_mass'],N+len(p['passages']))
 assert r['initial_branches']==dict(Counter(o['initial_branch'] for o in os))
 assert r['final_branches']==dict(Counter(o['route']['links'][1] for o in os))
 for o in os:
  pp=passages[o['id']]
  assert [IDS[x['link']] for x in pp]==o['route']['links']==PATHS[o['route']['links'][1]]
  assert pp[0]['entered']>=o['birth'] and pp[-1]['exited']==o['done']
  assert all(x['exited']==y['entered'] for x,y in zip(pp,pp[1:]))
  if 'bypass' in o['route']['links']:assert c['bypass'] and next(x for x in pp if x['link']==5)['entered']>=300
 assert [x['time'] for x in epochs]==list(range(0,1800,20))
 delivered_n=closure_n=0;pub=defaultdict(list);epochmap={e['time']:e for e in epochs}
 for e in epochs:
  t=e['time'];installed=set(IDS)-({'bypass'} if not c['bypass'] or t<300 else set())
  if 420<=t<540:assert not e['published']
  for report in e['published']:
   o=report['observation'];i=o['key']['id']
   assert report['channel']=='server' and i in installed and o['stamp_s']==o['end_s']==t and o['start_s']<=t
   if o['source']=='completed_link_passage':
    ww=window[t,i];assert len(ww)==o['mass_veh'] and close(sum(x['exited']-x['entered'] for x in ww)/len(ww),o['seconds'])
    assert o['start_s']==min(x['entered'] for x in ww)
   else:
    assert o['source']=='observed_no_entry' and i=='bridge' and 360<=t<420 and o['seconds']=='+inf' and o['mass_veh']>0
    closure_n+=1
   pub[i].append(o)
  costs={x['key']['id']:x for x in e['delivered']['costs']};assert set(costs)==installed
  for i,x in costs.items():
   feasible=[o for o in pub[i] if o['stamp_s']+40<=t and t-o['stamp_s']<=80]
   if feasible:
    o=max(feasible,key=lambda o:o['stamp_s']);assert x['stamp_s']==o['stamp_s'] and x['delivered_s']==o['stamp_s']+40 and x['age_s']==t-o['stamp_s']
    assert x['seconds']==o['seconds'] and x['population']==o['population'] and x['version']==o['version'];delivered_n+=1
   else:
    assert x['source']=='DECLARED_PRIOR' and x['stamp_s'] is None and x['delivered_s'] is None
    assert x['seconds']==L[i]/10+4
  if 500<=t<=560:assert e['delivered']['coverage_fraction']==0.
  paths=[p for p in PATHS.values() if set(p)<=installed and all(costs[i]['seconds']!='+inf' for i in p)]
  al=e['source']['alternatives'];assert {tuple(a['suffix']) for a in al}=={tuple(x) for x in paths}
  overlap=Counter(i for q in paths for i in q)
  weights=[]
  for a in al:
   q=a['suffix'];ps=sum(L[i]/overlap[i] for i in q)/sum(L[i] for i in q);cost=sum(costs[i]['seconds'] for i in q)
   assert close(a['path_size'],ps) and close(a['generalized_cost_s'],cost) and a['commitment']['graph_id']==e['graph_id']
   weights.append(ps*math.exp(-cost/12))
  assert all(close(a['probability'],w/sum(weights)) for a,w in zip(al,weights))
 assert closure_n>0 and delivered_n>0
 # Verify seeded source choice and each actual physical reroute in sequence.
 byowner=defaultdict(list)
 for z in rr:byowner[z['owner']].append(z)
 for o in os:
  e=epochmap[(int(o['birth'])//20)*20];u=rank(o['id'],c['seed']);v=0.;al=e['source']['alternatives'];selected=al[-1]
  for x in al:
   v+=x['probability']
   if u<v:selected=x;break
  old=selected['commitment']['links'];assert o['initial_branch']==old[1]
  last=-1000.
  for z in byowner[o['id']]:
   t=z['time'];pos=z['position'];assert z['birth']==o['birth'] and t-last>=40 and t%20==0 and o['birth']<=t<o['done']
   assert z['old']==old and z['new'] in PATHS.values() and old[:pos+1]==z['new'][:pos+1]
   assert z['epoch']==epochmap[t]['source']['cost_epoch'] and z['graph_id']==epochmap[t]['graph_id']
   if not z['hard']:assert z['gain_s']>5
   pp=passages[o['id']];assert pp[pos]['entered']<=t<pp[pos]['exited'] and t-pp[pos]['entered']>=L[old[pos]]/10
   if 'bypass' in z['new']:assert t>=300
   old=z['new'];last=t
  assert old==o['route']['links']
 if c['reroute']:assert rr
 else:assert not rr
 if c['bypass']:
  assert [(x['time'],x['accepted'],x['action']) for x in graph]==[(300.,True,'add:bypass'),(540.,False,'remove:bypass'),(1800.,True,'remove:bypass')]
  assert graph[0]['after']==graph[1]['before']==graph[1]['after']==graph[2]['before']
  assert graph[0]['before']!=graph[0]['after']!=graph[2]['after'] and not r['graph']['installed'][5]
  live=0
  for o in os:
   if o['birth']<540<o['done']:
    q=PATHS[o['initial_branch']]
    for z in byowner[o['id']]:
     if z['time']<540:q=z['new']
    live+=int('bypass' in q)
  assert live>0
 else:assert not graph;live=0
 return r,ages,{'name':n,'demand':N,'mean_s':r['mean_completed_s'],'stock_veh_s':p['stock_integral'],'peak_storage':p['peak_storage'],'peak_ready':p['peak_ready'],'blocked_steps':p['blocked_steps'],'reroutes':len(rr),'rerouted_owners':sum(bool(v) for v in byowner.values()),'hard_reroutes':sum(z['hard'] for z in rr),'initial_branches':r['initial_branches'],'final_branches':r['final_branches'],'delivered_cost_count':delivered_n,'closure_reports':closure_n,'live_bypass_at_rejection':live,'wall_s':r['wall_s'],'peak_rss_kib':r['peak_rss_kib']}
metrics=[];paired=[]
for gap in [2,4,8]:
 runs=[audit(f'S06_{gap}_{arm}') for arm in ['baseline','bypass','reroute']]
 metrics.extend(x[2] for x in runs)
 # Same dynamics before bypass install for two source-only arms.
 assert runs[0][0]['samples'][:5]==runs[1][0]['samples'][:5]
 for name,x,y in [('bypass_vs_baseline',runs[0],runs[1]),('reroute_vs_bypass',runs[1],runs[2])]:
  delta=[y[1][i]-x[1][i] for i in x[1]]
  paired.append(dict(gap=gap,comparison=name,better=sum(z<0 for z in delta),worse=sum(z>0 for z in delta),same=sum(z==0 for z in delta),min_delta_s=min(delta),max_delta_s=max(delta),mean_delta_s=sum(delta)/len(delta)))
assert any(x['worse']>0 for x in paired) and any(x['mean_delta_s']<0 for x in paired)
cut=load(B/'S07_cut440.bin');assert cut['world']['time']==440
assert sha(B/'S07_cut440.bin')==sha(B/'S07_recover440.bin')
assert sha(B/'S07_resume1800.bin')==sha(B/'S06_2_reroute.bin')
assert not any((B/x).exists() for x in ['S07_bad_model_output.bin','S07_bad_cross_output.bin','S07_bad_future_output.bin'])
print(json.dumps(dict(status='D07_VERIFIED_SCOPED_SYNTHETIC_NOT_RELEASE',matrix=metrics,paired=paired,
  recovery={'cut_s':440,'partial_owners':[{'id':o['id'],'fraction':o['cross']} for o in cut['world']['owners'] if o['cross']>0],
            'cut_sha256':sha(B/'S07_cut440.bin'),'final_sha256':sha(B/'S07_resume1800.bin')},
  scope='all nine finite synthetic cohorts; no original native calendar, service schedule, demand elasticity, equilibrium or city-wide convergence claim',
  limitations=['actual owner route updates in separate bounded lab, not original NativeJourneyCore integration','unit logical cohort, no all-class or empirical calibration; report closure is observed affected-ready availability, not completed passage mean','reroute policy enabled from t0, not only after bypass','checkpoint byte replay and selected malformed controls; not adversarial wire completeness','full receipt/history allocations, not no-heap or city scalability']),indent=2))
