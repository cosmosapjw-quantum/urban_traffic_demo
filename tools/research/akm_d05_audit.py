"""Independent finite checks of D05 receipts, wire, and next interface bound."""
from pathlib import Path
from fractions import Fraction as F
import hashlib, json, math, sys, random, struct
A=Path('artifacts/akm_d05_transport_20261128'); B=Path(sys.argv[1])
def load(p):return json.loads(p.read_text())
def get(name):return load(A/(name+'.json'))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def near(x,y,tol=1e-9):return abs(x-y)<=tol*max(1,abs(x),abs(y))
a=get('S04_A_results');assert len(a['results'])==20 and len(a['pulses'])==8
assert sha(B/'metroflow-akm-d05-lab')==a['executable_sha256']
for r in a['results']:
    q=r['scenario']
    assert r['status']=='HORIZON_REACHED' and r['time_s']==q['horizon']
    assert r['allocation_calls']==r['reallocation_calls']==0 and r['slots']==12
    assert near(r['released'],r['completed']+r['pending']+r['active'])
    assert r['metrics']['max_storage']<=1+1e-9
    assert len(r['curves'])==int(q['horizon']/(600 if q['day_profile'] else 60))
    for t,rel,comp,pend,active,age in r['curves']:
        assert near(rel,comp+pend+active)
        assert min(rel,comp,pend,active,age)>=-1e-9
    if q['day_profile'] and q['dt']==1.25:
        idx=a['results'].index(r)
        assert sha(B/'A_lab'/f'lab-{idx}-final.bin')==r['checkpoint_sha256']
for r in a['pulses']:
    assert abs(r['mean_s']-10)<1e-7 and abs(r['variance_s2']-50/r['cells'])<1e-5
def compare(x,y):
    assert len(x['curves'])==len(y['curves']) and all(i[0]==j[0] for i,j in zip(x['curves'],y['curves']))
    den=max(1.,x['released'],y['released'])
    return {'dt_s':[x['scenario']['dt'],y['scenario']['dt']],
            'conditional_mean_gap_relative_to_coarse':abs(y['completed_conditional_mean_s']/x['completed_conditional_mean_s']-1),
            'completion_curve_max_gap_fraction':max(abs(i[2]-j[2]) for i,j in zip(x['curves'],y['curves']))/den,
            'final_incomplete_gap_fraction':abs(x['pending']+x['active']-y['pending']-y['active'])/den,
            'stock_integral_relative_gap':abs(y['metrics']['stock_veh_s']/x['metrics']['stock_veh_s']-1)}
arms={}
for mode in [False,True]:
    subset=[r for r in a['results'] if r['scenario']['selective']==mode]
    day=[r for r in subset if r['scenario']['day_profile']]
    ov={}
    for amp in [10,100]:
        rows=[r for r in subset if r['scenario']['amplitude']==amp]
        ov[str(amp)]=[compare(x,y) for x,y in zip(rows,rows[1:])]
    arms[str(mode)]=dict(day=[compare(x,y) for x,y in zip(day,day[1:])],overload=ov,
       fixed_offer=next(r['completed_conditional_mean_s'] for r in subset if r['scenario']['fixed_offer']),
       fine_day_mean=day[-1]['completed_conditional_mean_s'],fine_day_stock=day[-1]['metrics']['stock_veh_s'],
       fine_day_gate_pass=compare(day[-2],day[-1])['conditional_mean_gap_relative_to_coarse']<=.02 and compare(day[-2],day[-1])['completion_curve_max_gap_fraction']<=.02)
assert not any(r['fine_day_gate_pass'] for r in arms.values())
bs=[]
for mesh in [1200,600,300]:
    r=get(f'S05_B_mesh{mesh}');z=r['result'];assert r['config']['horizon_s']==28800 and r['config']['mesh_s']==mesh and r['config']['seed']==7
    assert r['network_sha256']=='af8a0c16e2bd31d4a42282e83d076ea10075e6cbe0bb3982dfb5978cfa9f72a5'
    assert r['passages_sha256']=='a310ee706ae3eb64ba35eef2c9275da38141dbd32eb89f86bcb6a90c89bd73c1'
    assert r['executable_sha256']==sha(B/'metroflow-active-city')
    assert [s['time_s'] for s in z['snapshots']]==[25720.,28800.]
    for s in z['snapshots']:
        assert s['max_storage_ratio']<=1+1e-9 and s['max_receiving_ratio']<=1+1e-9
        for c in s['classes']:assert near(c['released'],c['completed']+c['active'])
    c=z['snapshots'][-1]['classes'][0]
    bs.append(dict(mesh_s=mesh,completed=c['completed'],released=c['released'],mean_s=c['trip_seconds']/c['completed'],
            active=c['active'],peak_storage=z['snapshots'][-1]['max_storage_ratio'],peak_receiving=z['snapshots'][-1]['max_receiving_ratio'],
            wait_veh_s=z['wait_veh_s'],blocked_veh_s=z['blocked_veh_s'],initial_batches=z['initial_batches'],events=z['event_count'],
            peak_ready=z['active_mobility']['peak_ready_entries'],rss=r['peak_rss_bytes'],wall_s=r['wall_s'],snapshots=z['snapshots']))
bc=[]
for x,y in zip(bs,bs[1:]):
    denom=max(x['released'],y['released'],1)
    comp=max(abs(i['classes'][0]['completed']-j['classes'][0]['completed'])/max(1,i['classes'][0]['released'],j['classes'][0]['released']) for i,j in zip(x['snapshots'],y['snapshots']))
    rel=max(abs(i['classes'][0]['released']-j['classes'][0]['released'])/max(1,i['classes'][0]['released'],j['classes'][0]['released']) for i,j in zip(x['snapshots'],y['snapshots']))
    bc.append(dict(mesh_s=[x['mesh_s'],y['mesh_s']],mean_gap_relative=abs(y['mean_s']/x['mean_s']-1),
        sampled_completion_curve_gap=comp,sampled_release_curve_gap=rel,final_incomplete_gap_fraction=abs(y['active']-x['active'])/denom,
        peak_storage_gap_abs=abs(y['peak_storage']-x['peak_storage']),peak_receiving_gap_abs=abs(y['peak_receiving']-x['peak_receiving']),
        wall_ratio=y['wall_s']/x['wall_s'],event_ratio=y['events']/x['events']))
# Read only fixed-width state prefix of small checkpoints; independently
# preserve exact wire layout and track position/identity.
def wire(name):
    data=(B/(name+'.bin')).read_bytes();off=8
    def read(fmt):
        nonlocal off
        v=struct.unpack_from('<'+fmt,data,off);off+=struct.calcsize('<'+fmt);return v
    def u():return read('Q')[0]
    n=u();identity=data[off:off+n].decode();off+=n
    t,ib,ob,ex=read('4d');classes=[read('2d') for _ in range(u())]
    maps=[]
    for _ in range(2):
        rows=[]
        for i in range(u()):
            tag,pos=read('QQ');m0,m1,j0,j1,z0,z1,birth=read('7d');rows.append((tag,pos,m0+m1,birth))
        maps.append(rows)
    tracks=[]
    if data[:8]==b'AKMFULL2':
        k=u();tracks=[read('QQ2d') for _ in range(u())]
        assert k==2
        assert all(0<=x[2]<=100 and 0<=x[3]<=t for x in tracks)
    else:assert data[:8]==b'AKMFULL1'
    runs=[read('QQ3d') for _ in range(u())]
    people=[read('5d') for _ in range(u())]
    return dict(t=t,identity=identity,tracks=tracks,bus_runs=runs,passengers=people,road=maps[0],pending=maps[1],class_road_ledger=classes)
names=['S07_hybrid120','S07_hybrid360','S07_hybrid360_direct','S07_hybrid360_recover','S07_mixed360','S08_hybrid_half','S08_mixed_half','S08_hybrid_two','S08_mixed_two','S09_hybrid_active36','S09_hybrid_active36_recover','S09_hybrid_two_resume360','S08_hybrid_city25380','S08_hybrid_city25380_recover']
rs={name:get(name) for name in names}
for n,r in rs.items():
    assert r['status']=='EXECUTED_FOR_REVIEW' and r['failure'] is None
    assert sha(B/(n+'.bin'))==r['checkpoint_sha256'] and sha(B/'metroflow-akm-native')==r['executable_sha256']
    assert r['peak_rss_kib']*1024<8*1024**3 and r['peak_storage_ratio']<=1+1e-9 and r['peak_road_rows']<=r['road_rows_guard']
    for row in r['ledger'].values():
        assert min(row.values())>=-1e-7
        assert near(row['requested'],row['released']+row['pending']) and near(row['released'],row['completed']+row['active'])
    assert near(math.fsum(c[0]-c[1] for c in r['class_road_ledger']),r['active_road_mass'])
    assert near(r['initial_road_birth']+r['new_offered_birth'],r['outlet_birth']+r['active_road_birth'],1e-8)
for pair in [('S07_hybrid360','S07_hybrid360_direct','S07_hybrid360_recover'),('S09_hybrid_active36','S09_hybrid_active36_recover'),('S08_hybrid_two','S09_hybrid_two_resume360'),('S08_hybrid_city25380','S08_hybrid_city25380_recover')]:
    assert len({rs[n]['checkpoint_sha256'] for n in pair})==1
    assert all(rs[n]['ledger']==rs[pair[0]]['ledger'] for n in pair)
old=load(Path('artifacts/akm_observables_owners_20261128/S08_fixture360.json'))
assert old['checkpoint_sha256']==rs['S07_mixed360']['checkpoint_sha256']
oldcity=load(Path('artifacts/akm_observables_owners_20261128/S08_valley25380.json'))
city=rs['S08_hybrid_city25380']
for k in ['manifest_sha256','source_checkpoint_sha256','calendar_legs','calendar_totals','unsupported_legs','ledger','class_road_ledger','journey_records','road_rows','active_road_mass','active_road_birth']:
    assert city[k]==oldcity[k],k
assert city['whole_bus']['moves']==0 and city['model_identity']!=oldcity['model_identity']
wires={n:wire(n) for n in ['S07_hybrid360','S07_mixed360','S08_hybrid_half','S08_hybrid_two','S08_mixed_two','S09_hybrid_active36']}
assert wires['S09_hybrid_active36']['tracks'][0][2]>0
assert all(r[0]==1 and r[1]==2 for r in wires['S08_hybrid_two']['bus_runs'])
assert all(p[2]==2 for p in wires['S08_hybrid_two']['passengers'])
assert near(rs['S08_hybrid_two']['ledger']['persons']['completed'],20)
assert near(rs['S08_hybrid_half']['ledger']['persons']['completed'],16)
assert near(rs['S07_hybrid360']['ledger']['persons']['completed'],16)
assert near(rs['S08_mixed_two']['ledger']['persons']['completed'],18)
assert not (B/'S09_invalid_output.bin').exists()
# Constructive next-route bound: partial physical boundary reservation.
# This is an independent mathematical oracle, not a production implementation.
def interface(m,ell,L,w,c,F0,h):
    assert h*w<=L and F0>ell*m
    lower=min(c,w*(F0-ell*m)/(L*ell))
    assert lower>0
    a=F(0);n=0
    while a<m:
        cap=min(c*h,w*h*(F0-ell*a)/(L*ell))
        z=min(m-a,cap);assert z>0 and z<=c*h and ell*z<=w*h/L*(F0-ell*a)
        a+=z;n+=1
        assert n*h<=m/lower+h
    return n*h,m/lower+h
rng=random.Random(20261128);count=0
for _ in range(512):
    m=F(rng.randint(1,4),2);ell=F(rng.randint(4,15));L=F(100);w=F(5);c=F(rng.randint(1,6),2)
    F0=ell*m+F(rng.randint(1,100));h=F(rng.randint(1,8),4)
    t,upper=interface(m,ell,L,w,c,F0,h);assert t<=upper;count+=1
fixed=[]
for h in [F(1,2),F(1),F(2)]:
    t,upper=interface(F(1),F(12),F(100),F(5),F(2),F(200),h)
    fixed.append(dict(dt_s=float(h),strict_atomic_eligible=bool(min(2*h,F(200)*5*h/100/12)>=1),
                      incremental_entry_time_s=float(t),conditional_bound_s=float(upper)))
out=dict(status='D05_ATTEMPT_1_EXECUTED_NEGATIVE_AND_POSITIVE_SCOPED',A=arms,B={'runs':bs,'comparisons':bc},
         D={'whole_service_fixtures':{n:{'persons':r['ledger']['persons'],'bus':r['whole_bus'],'class_road_ledger':r['class_road_ledger'],'wire_sha256':r['checkpoint_sha256']} for n,r in rs.items() if not 'city' in n},
            'wire_decodes':wires,'original_city_no_bus_regression':True,'city_checkpoint_sha256':city['checkpoint_sha256'],
            'remaining':'strict atomic service quota starvation at dt<=1, not a time-refined physical closure'},
         interface_bound={'status':'DERIVED_NUMERICALLY_CHECKED_NOT_IMPLEMENTED','cases':count,'fixture_constant_other_stock':fixed,
             'assumptions':'strict spare storage F0>ell*m; positive fixed count cap and w; h*w<=L; no competing flows; no unused quota accumulation; completion bound only for crossing phase'},
         decision={'A':'retain original for comparison; reject combined selective/residual variant as current day-resolution solution; both fail 2% mean gate',
                   'B':'preferred fixed-route projected comparison lane on sampled AM completion/mean; storage and receiving peaks unresolved, not current calendar bridge',
                   'D':'retain exactly one fallback family; strict atomic arm negative at original dt, successful causal transit at dt2 is diagnostic only. Next final attempt use reserved interface transfer, no quota relaxation',
                   'D05':'READY attempt 1/2 consumed; next attempt final, no automatic D07, no V03 credit'})
print(json.dumps(out,indent=2))
