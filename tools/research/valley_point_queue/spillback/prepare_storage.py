"""Extract native standing-space capacities in car-equivalent vehicle units."""
import hashlib
import json
import math
import sys
from pathlib import Path

repo, prepared, out = map(Path, sys.argv[1:])
sys.path.insert(0, str(repo / 'tools/research/valley_point_queue/onset'))
from native_phase_boundary import original_laws
city, calendar, _, static = original_laws(repo.resolve())
meta = json.loads((prepared / 'input_summary.json').read_text())
assert (city, calendar.identity) == (meta['city_identity'], meta['schedule_identity'])
assert static['identity'] == meta['source_static_identity']
assert static['link_ids'] == json.loads((prepared / 'link_ids.json').read_text())
network = prepared / 'network.txt'
assert hashlib.sha256(network.read_bytes()).hexdigest() == meta['extracted_input_sha256']
footprint = static['classes'][static['class_names'].index('car')][12]
capacity = [g[4] / footprint for g in static['groups']]
assert all(math.isfinite(k) and k > 0 for k in capacity)
with network.open() as f:
    L, P, G, W, _ = map(float, next(f).split())
    assert int(L) == len(capacity)
    for g in static['groups']:
        dt, c = map(float, next(f).split())
        assert math.isclose(dt, g[0]/min(g[1],10.), rel_tol=1e-12) and math.isclose(c,g[3],rel_tol=1e-12)
    paths = [list(map(int,next(f).split()))[1:] for _ in range(int(P))]
    windows = [list(map(float,next(f).split())) for _ in range(int(W))]
    ratios = {}
    for h in (600, 300, 150, 10):
        ratios[h] = 0.0
    for line in f:
        a,b,p,m,_,_ = map(float,line.split()); a,b,p = int(a),int(b),int(p)
        k = min(capacity[e] for e in paths[a]+paths[b]); w = windows[p]
        for h in ratios:
            ratios[h] = max(ratios[h], m/math.ceil(max(w[1]-w[0],w[3]-w[2])/h)/k)
assert all(x <= 1 for x in ratios.values()), ratios
out.write_text(str(len(capacity))+'\n'+'\n'.join(format(x,'.17g') for x in capacity)+'\n')
print(json.dumps(dict(city_identity=city,schedule_identity=calendar.identity,network_sha256=meta['extracted_input_sha256'],storage_sha256=hashlib.sha256(out.read_bytes()).hexdigest(),links=len(capacity),footprint_m=footprint,min_storage_veh=min(capacity),max_storage_veh=max(capacity),max_batch_capacity_ratio=ratios),indent=2))
