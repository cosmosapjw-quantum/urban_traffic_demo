"""Read completed phase runs, check original projected mass and report grid/seed controls."""
import json
from pathlib import Path
import re
import sys

def read(path):
    rows=path.read_text().splitlines()
    sn=[list(map(float,r.split()[1:])) for r in rows if r.startswith('snap ')]
    end=[list(map(float,r.split()[1:])) for r in rows if r.startswith('end ')]
    assert len(end)==1 and sn and sn[-1][0]==86400 and len(sn[-1])==12, path
    e=end[0]; f=sn[-1]
    assert abs(f[4]-57095.9403264)<1e-6 and abs(f[5])<1e-7 and abs(f[6])<1e-7
    assert all(s[7]<1e-7 and 0<=s[9]<=1+1e-9 for s in sn)
    ts=path.with_suffix('.time').read_text()
    t=re.fullmatch(r'wall_s=([\d.]+) peak_rss_kib=(\d+)\s*',ts)
    assert t, (path,ts)
    return dict(complete_veh=f[4],active_veh=f[5],max_ledger_error=max(s[7] for s in sn),
                peak_storage_fraction=f[9],receiving_wait_veh_s=e[4],trip_time_veh_s=e[-1],
                service_wait_veh_s=e[3],events=int(e[2]),initial_batches=int(e[1]),
                onset_admitted=sn[0][2],onset_exited=sn[0][3],onset_stock=sn[0][6],
                wall_s=float(t[1]),peak_rss_kib=int(t[2]))

paths=[Path(x) for x in sys.argv[1:]]
print(json.dumps({p.stem:read(p) for p in paths},indent=2,allow_nan=False))
