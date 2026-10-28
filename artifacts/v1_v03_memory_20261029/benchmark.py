"""Measure retained exact factorized calendar legs with original/shared profiles."""
from dataclasses import replace
import gc
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from metroflow.v1.access_audit import fixture_city
from metroflow.v1.activity import compile_activity
import metroflow.v1.demand as demand
import metroflow.v1.factorized_demand as factorized
from metroflow.v1.schedules import daily_profiles

cached=demand.calendar_profiles
city=fixture_city()
home=compile_activity(city,'block')
job=compile_activity(city,'block','job')
homes=tuple(replace(home,block_id=f'h{i}') for i in range(50))
jobs=tuple(replace(job,block_id=f'j{i}') for i in range(50))
schedule=factorized.compile_factorized_demand(homes,jobs,service_fraction=0,worker_fraction=.1)


def measure(shared):
    gc.collect()
    cached.cache_clear()
    demand.calendar_profiles=cached if shared else daily_profiles
    factorized.calendar_profiles=cached if shared else daily_profiles
    tracemalloc.start()
    start=time.perf_counter()
    legs=tuple(schedule.iter_legs())
    elapsed=time.perf_counter()-start
    retained,peak=tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return legs,dict(retained_bytes=retained,peak_bytes=peak,wall_s=elapsed,
                     distinct_profiles=len({id(leg.departures) for leg in legs}))


runs=[]
try:
    for index in range(5):
        a,b=(False,True) if index%2==0 else (True,False)
        first,fa=measure(a)
        second,fb=measure(b)
        assert first==second
        by_mode={a:fa,b:fb}
        runs.append(dict(baseline=by_mode[False],shared=by_mode[True],all_legs_equal=True))
        del first,second
finally:
    demand.calendar_profiles=cached
    factorized.calendar_profiles=cached
summary={mode:{key:statistics.mean(run[mode][key] for run in runs)
               for key in ('retained_bytes','peak_bytes','wall_s','distinct_profiles')}
         for mode in ('baseline','shared')}
result=dict(scope='50home x50job x3modes;15000 exact outward/return legs; uniform declared synthetic fixture; marginal schedule built outside tracing',
            reference='original schedules.daily_profiles called per cohort vs bounded immutable profile-pair sharing',
            repetitions=5,order='alternating paired; full tuple equality checked every pair',python=platform.python_version(),
            parent_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            schedule_identity=schedule.identity,legs=15000,runs=runs,means=summary,
            retained_reduction_fraction=1-summary['shared']['retained_bytes']/summary['baseline']['retained_bytes'],
            source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
                           ('src/metroflow/v1/demand.py','src/metroflow/v1/factorized_demand.py','tests/v1/test_calendar_memory.py')},
            source_cap='maxsize8 profile pairs only; no calendar limit increase; OD records and progress remain distinct',
            full_release_city_campaign='NOT_RUN')
Path(__file__).with_name('RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(legs=15000,means=summary,retained_reduction_fraction=result['retained_reduction_fraction'])))
