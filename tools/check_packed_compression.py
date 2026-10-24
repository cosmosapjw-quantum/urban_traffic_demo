"""Matched-clock ablation: only calendar representation changes, not physics."""
from pathlib import Path
import sys,json,math,time
from dataclasses import replace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from metroflow.active_suffix import Road,Signal,Demand,Config
from metroflow.active_suffix.packed import PackedModel,TransitRun
from metroflow.active_suffix.routing import braess_reference

class PointCalendar(PackedModel):
    def _pack(self,future):
        records={}
        for e in future:
            assert e.first_tick==e.last_tick
            key=e.first_tick,e.suffix
            records[key]=records.get(key,0.)+e.mass
        return tuple(TransitRun(t,t,s,m) for (t,s),m in sorted(records.items()) if m>0)

def main():
    path=Path(sys.argv[1]);out=Path(sys.argv[2]);out.parent.mkdir(parents=True,exist_ok=True)
    data=json.loads(path.read_text())
    roads=tuple(Road(**(r|{'signal':Signal(**r['signal']) if r['signal'] else None})) for r in data['compiled']['roads'])
    demands=tuple(Demand(**d) for d in data['plan']['demands'])
    cfg=replace(Config(**data['config']),dt_s=2.)
    turns=frozenset(tuple(x) for x in data['compiled']['turns'])
    a,b=PointCalendar(roads,demands,cfg,allowed_turns=turns),PackedModel(roads,demands,cfg,allowed_turns=turns)
    x,y=a.initial(),b.initial();peakx=peaky=0;errors={'occupancy':0.,'completed':0.,'residence':0.}
    started=time.perf_counter()
    for _ in range(150):
        x,y=a.step(x),b.step(y)
        peakx=max(peakx,len(x.transit));peaky=max(peaky,len(y.transit))
        errors['occupancy']=max(errors['occupancy'],max(abs(i-j) for i,j in zip(a.occupancy(x)[0],b.occupancy(y)[0])))
        errors['completed']=max(errors['completed'],abs(x.completed-y.completed))
        errors['residence']=max(errors['residence'],abs(x.vehicle_seconds-y.vehicle_seconds))
        assert errors['occupancy']<1e-8 and errors['completed']<1e-8 and errors['residence']<1e-7
    before,after=braess_reference(),braess_reference(shortcut=True)
    assert abs(before['mean_cost_min']-65.)<1e-8 and abs(after['mean_cost_min']-80.)<1e-8
    result=dict(status='PASS_SCOPED',time_s=300.,dt_s=2.,point_records=peakx,packed_records=peaky,
                max_difference=errors,wall_both_models_s=time.perf_counter()-started,
                source_changes=False,clock_changes=False,physics_changes=False,
                static_braess_minutes=[before['mean_cost_min'],after['mean_cost_min']])
    out.write_text(json.dumps(result,indent=2,allow_nan=False));print(json.dumps(result,indent=2))

if __name__=='__main__':main()
