from pathlib import Path
import hashlib, json, os, struct
from test_native_road import road
from metroflow.v1.native_road import NativeRoadNetwork
from _metroflow_rust import budget_trace_snapshot

def digest(x):
    h=hashlib.sha256()
    def add(v):
        if isinstance(v,(tuple,list)):
            h.update(b'A'+struct.pack('<Q',len(v)))
            for w in v: add(w)
        elif isinstance(v,float): h.update(b'F'+struct.pack('<d',v))
        elif isinstance(v,int): h.update(b'I'+struct.pack('<Q',v))
        elif isinstance(v,str):
            encoded=v.encode()
            h.update(b'S'+struct.pack('<Q',len(encoded))+encoded)
        elif v is None: h.update(b'N')
        else: raise TypeError(type(v))
    add(x)
    return h.hexdigest()

offers={0:(('z',5.,0.),('a',3.,0.),('merge',4.,0.),('alias',1.,0.)),3:(('z',1.25,2.5),('a',.5,.5)),21:(('merge',2.,20.),)}
results=[]
for mode in ('0','1'):
    os.environ['METROFLOW_EXPERIMENTAL_EVENT_INDEX_INCOMING']=mode
    engine=NativeRoadNetwork(road(intervals=True))
    engine.initial()
    engine.native.configure_storage_budget(256*1024**2)
    budget_trace_snapshot(reset=True)
    states=[]; through=0; exited=0
    for i in range(100):
        events=engine.native.step(1.,engine._offers(offers.get(i,())))
        through+=sum(e[2] is not None for e in events)
        exited+=sum(e[2] is None for e in events)
        engine.check(engine.snapshot())
        states.append(digest((engine.native.snapshot(),events)))
    r=budget_trace_snapshot(reset=True)
    refs=r['counters']['incoming_timed.event_referenced_rows'][1]
    assert through>0 and exited>0 and refs==(through if mode=='1' else 0)
    results.append(dict(mode=mode,refs=refs,through=through,exited=exited,states=states))
assert results[0]['states']==results[1]['states']
print(json.dumps(dict(schema='native_multiclass_receiving_shadow.v1',ticks=100,full_state_and_events_ieee_exact=True,terminal_sha256=results[0]['states'][-1],arms=[{k:v for k,v in a.items() if k!='states'}for a in results]),indent=2))
