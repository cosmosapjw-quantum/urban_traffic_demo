"""Independent audit of actual D09 finite-cohort evidence. No simulation."""
from pathlib import Path
import hashlib,json,math,struct,sys
A=Path('artifacts/akm_d09_final_cohort_20261128')
O=Path('artifacts/akm_d09_city_pilot_20261128')
B=Path(sys.argv[1])
def load(p):return json.loads(p.read_bytes())
def get(n):return load(A/(n+'.json'))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def near(x,y,tol=1e-9):return abs(x-y)<=tol*max(1.,abs(x),abs(y))
TH=[1e-15,1e-12,1e-9,1e-6,1e-3]
def wire(name):
    # Decode complete road prefix independently; native recovery checks
    # the full service/journey suffix and exact bytes.
    with (B/(name+'.bin')).open('rb') as f:
        assert f.read(8)==b'AKMFULL4'
        def read(fmt):return struct.unpack('<'+fmt,f.read(struct.calcsize('<'+fmt)))
        def u():return read('Q')[0]
        n=u();assert n<4096;identity=f.read(n).decode()
        t,initial,offered,outlet=read('4d')
        classes=[read('2d') for _ in range(u())]
        def rows(name):
            n=u();assert n<=1000000
            keys=set();tags=set();masses=[];births=[];counts=[0]*len(TH)
            mm=[[] for _ in TH];bb=[[] for _ in TH];last=None
            for _ in range(n):
                tag,pos,m0,m1,j0,j1,z0,z1,b=read('QQ7d')
                key=(tag,pos);assert last is None or last<key;last=key
                keys.add(key);tags.add(tag);m=m0+m1
                assert m>0 and math.isfinite(m) and 0<=b<=m*t+1e-10*max(1.,m*t)
                for mi,ji,zi in [(m0,j0,z0),(m1,j1,z1)]:
                    assert all(math.isfinite(x) and x>=0. for x in (mi,ji,zi))
                    if mi==0:assert ji==zi==0
                    else:assert ji/mi<=1+1e-10 and zi/mi<=ji/mi+1e-10 and (ji/mi)**2<=zi/mi+1e-10
                masses.append(m);births.append(b)
                for k,th in enumerate(TH):
                    if m<=th:counts[k]+=1;mm[k].append(m);bb[k].append(b)
            return keys,dict(storage=name,rows=n,distinct_tags=len(tags),mass_veh=math.fsum(masses),birth=math.fsum(births),
                bins=[dict(threshold_veh=th,rows=c,mass_veh=math.fsum(m),birth_veh_s=math.fsum(b)) for th,c,m,b in zip(TH,counts,mm,bb)])
        rk,r=rows('road');pk,p=rows('pending')
        bus=u();assert bus==2
        tracks={}
        for _ in range(u()):
            a,b,d,t0=read('QQ2d');assert (a,b) not in tracks and d>=0 and 0<=t0<=t;tracks[a,b]=(d,t0)
        cross={}
        for _ in range(u()):
            a,b,q=read('QQd');assert 0<q<1 and (a,b) not in cross;cross[a,b]=q
        wk,w=rows('waiting')
        distance={}
        for _ in range(u()):
            a,b,x=read('QQd');assert math.isfinite(x) and x>=0 and (a,b) not in distance;distance[a,b]=x
        assert set(tracks).isdisjoint(distance) and set(tracks)|set(distance)==rk
        assert wk<=set(distance) and set(cross)<=set(tracks)|pk
        assert r['rows']+p['rows']+w['rows']<=1000000
        return dict(identity=identity,time_s=t,initial_birth=initial,offered_birth=offered,outlet_birth=outlet,classes=classes,
                    maps=[r,p,w],bus_tracks=len(tracks),fluid_tracks=len(distance),crossings=len(cross))
manifest=sha(B/'valley-original.manifest.json')
assert manifest=='2088b2df7a0bb0503adea24bfcdec196758171d5d52f64f42b03269dcb008bd3'
names=['S05_cohort360','S05_cohort31','S05_recover31','S05_resume360','S05_old_pilot','S06_prefix','S07_recover_prefix','S07_day','S07_recover_final','S08_front']
rs={n:get(n) for n in names}
exe=sha(B/'metroflow-akm-native')
for n,r in rs.items():
    assert sha(B/(n+'.bin'))==r['checkpoint_sha256'] and r['executable_sha256']==exe
    assert r['road_rows']<=r['road_rows_guard']==1000000
    assert r['peak_rss_kib']*1024<=8*1024**3 and r['peak_storage_ratio']<=1+1e-9
    for row in r['ledger'].values():
        assert near(row['requested'],row['released']+row['pending']) and near(row['released'],row['completed']+row['active'])
        assert row['active']>=-1e-9*max(1.,row['released']) and row['pending']>=-1e-9*max(1.,row['requested'])
    assert near(math.fsum(x[0]-x[1] for x in r['class_road_ledger']),r['active_road_mass'])
    assert near(r['initial_road_birth']+r['new_offered_birth'],r['outlet_birth']+r['active_road_birth'],1e-8)
    if n.startswith(('S06','S07')):
        assert r['manifest_sha256']==manifest and r['calendar_legs']==918450 and r['calendar_totals']==[120000.,58801.,1000.] and r['unsupported_legs']==610820
        times=[x['time_s'] for x in r['pilot']['samples']]
        assert times[-1]==r['time_s'] and all(x<y for x,y in zip(times,times[1:]))
for a,b in [('S05_cohort31','S05_recover31'),('S05_cohort360','S05_resume360'),('S05_cohort360','S08_front'),('S06_prefix','S07_recover_prefix'),('S07_day','S07_recover_final')]:
    assert rs[a]['checkpoint_sha256']==rs[b]['checkpoint_sha256'] and rs[a]['ledger']==rs[b]['ledger']
old_fixture=load(O/'S05_pilot360.json')
assert rs['S05_old_pilot']['checkpoint_sha256']==old_fixture['checkpoint_sha256']
r=rs['S05_cohort360'];assert r['road_rows']==0 and r['journey_records'][3]==5
for k,v in [('persons',20.),('vehicles',13.06),('cargo_kg',100.)]:assert near(r['ledger'][k]['completed'],v)
assert rs['S05_old_pilot']['road_rows']==3 and rs['S05_old_pilot']['journey_records'][3]==15
assert not (B/'S05_invalid.bin').exists()
old=load(O/'S06_fresh_day.json');p=rs['S06_prefix'];f=rs['S07_day']
assert p['time_s']==old['time_s']==25430 and p['status']=='EXECUTED_FOR_REVIEW'
for k in ['persons','vehicles','cargo_kg']:
    for q in ['requested','released','pending','released_intent_first_moment']:assert p['ledger'][k][q]==old['ledger'][k][q]
assert p['road_rows']==371733 and p['cohort']['active_fluid']==326256 and p['cohort']['waiting_rows']==45477
assert p['road_rows']==sum(x['rows'] for x in p['support_census'])
assert all(x['bins'][2]['rows']==0 for x in p['support_census'])
assert f['start_s']==p['time_s'] and f['source_checkpoint_sha256']==p['checkpoint_sha256'] and f['requested_end_s']==86400
assert f['time_s']>p['time_s']
decoded={}
for n in ['S05_cohort31','S05_cohort360','S06_prefix','S07_day']:
    d=wire(n);r=rs[n];assert d['identity']==r['model_identity'] and d['time_s']==r['time_s']
    assert d['classes']==[tuple(x) for x in r['class_road_ledger']]
    assert sum(x['rows'] for x in d['maps'])==r['road_rows']
    assert near(math.fsum(x['mass_veh'] for x in d['maps']),r['active_road_mass'])
    assert near(math.fsum(x['birth'] for x in d['maps']),r['active_road_birth'])
    assert d['fluid_tracks']==r['cohort']['active_fluid'] and d['maps'][2]['rows']==r['cohort']['waiting_rows']
    assert near(d['maps'][2]['mass_veh'],r['cohort']['waiting_mass'])
    for x,y in zip(d['maps'],r['support_census']):
        for k in ['storage','rows','distinct_tags']:assert x[k]==y[k]
        assert near(x['mass_veh'],y['mass_veh'])
        for a,b in zip(x['bins'],y['bins']):
            assert a['rows']==b['rows'] and a['threshold_veh']==b['threshold_veh']
            assert near(a['mass_veh'],b['mass_veh'],1e-12) and near(a['birth_veh_s'],b['birth_veh_s'],1e-12)
    decoded[n]=d
s=get('S08_support');support=load(O/'S03_support.json')
assert s['manifest_sha256']==manifest and s['parent_profile_bound']==support['windows'][-1]
assert s['sum_single_run_seat_capacity']==960 and near(s['bus_person_intent'],30000.)
bias=(A/'S09_batch_bias.log').read_text()
assert bias.count('extra=7\n')==3
assert '329 passed; 0 failed; 2 ignored' in (A/'S09_native_tests.log').read_text()
assert '17 passed' in (A/'S09_frontend_tests.log').read_text()
print(json.dumps(dict(status='D09_FINAL_ATTEMPT_NOT_ACCEPTED',manifest_sha256=manifest,
    same_prefix={'time_s':p['time_s'],'old_rows':old['road_rows'],'new_rows':p['road_rows'],'row_reduction_fraction':1-p['road_rows']/old['road_rows'],
                 'old_person_completed':old['ledger']['persons']['completed'],'new_person_completed':p['ledger']['persons']['completed'],
                 'old_road_mass':old['active_road_mass'],'new_road_mass':p['active_road_mass'],'old_history':old['journey_records'],'new_history':p['journey_records'],
                 'old_tiny_rows':173429,'new_tiny_rows':0,'old_peak_rss_kib':old['peak_rss_kib'],'new_peak_rss_kib':p['peak_rss_kib']},
    continuation={k:f[k] for k in ['status','failure','start_s','requested_end_s','time_s','wall_s','advance_s','peak_rss_kib','road_rows','peak_road_rows','journey_records','ledger','cohort','whole_bus','support_census','pilot','checkpoint_sha256']},
    physical={'fixture_drain':True,'fixture_restart_byte_equal':True,'city_checkpoint_recovery_byte_equal':True,'old_pilot_wire_equal':True,
              'actual_refinement_steps_s':[1,.5,.25],'synchronization_extra_s':[7,7,7],'decoded_road_prefixes':decoded},
    support=s,decision='D09 STOPPED 2/2, original unsupported demand and unvalidated 24h/release; D10 blocked dependency, D11 separate decision ready; no further D09 retries',
    limits=['mean-characteristic sealed cohorts not exact first-passage/FIFO','intent-priority and bus-first quota not fairness proof','waiting stock does not translate until promotion','no arbitrary mass deletion','no new original support or city D07/D08 coupling','native recovery not direct-vs-split full city trajectory','full CI/main merge not run']),indent=2))
