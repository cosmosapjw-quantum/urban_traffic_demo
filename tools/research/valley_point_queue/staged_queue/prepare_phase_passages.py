"""Per-route finite-response passage times for the optional Valley queue arm."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np


def build(repo, prep, phase, out):
    sys.path.insert(0, str(phase.resolve()))
    from native_phase_boundary import original_laws
    city, calendar, _, static = original_laws(repo.resolve())
    from metroflow.foundation_kinetics import VehicleClass, passage
    meta = json.loads((prep/"input_summary.json").read_text())
    network = prep/"network.txt"
    assert (city, calendar.identity) == (meta["city_identity"], meta["schedule_identity"])
    assert hashlib.sha256(network.read_bytes()).hexdigest() == meta["extracted_input_sha256"]
    cls = static["classes"][static["class_names"].index("car")]
    pref,tau,acc,brake = cls[:4]
    speed0 = cls[11]
    vh = VehicleClass("car", preferred_mps=pref, response_s=tau, accel_mps2=acc, brake_mps2=brake)
    lengths = np.array([g[0] for g in static["groups"]])
    targets = np.minimum(pref, [g[1] for g in static["groups"]])
    with network.open() as f:
        L,P,*_ = next(f).split()
        free = [float(next(f).split()[0]) for _ in range(int(L))]
        assert np.allclose(free, lengths/targets, rtol=2e-15, atol=1e-13)
        paths = []
        for _ in range(int(P)):
            count,*edges = map(int,next(f).split())
            assert len(edges)==count
            paths.append(edges)
    slots = np.full((len(paths),max(map(len,paths))),-1,dtype=int)
    times = np.zeros_like(slots,dtype=float)
    for i,path in enumerate(paths):
        slots[i,:len(path)] = path
    speed = np.full(len(paths),speed0,dtype=float)
    max_error = 0.0
    for j,edges in enumerate(slots.T):
        active = edges>=0
        idx = edges[active]
        u,V,L = speed[active],targets[idx],lengths[idx]
        lim = np.where(V>=u,acc,brake)
        a = np.where(V>=u,lim,-lim)
        sat = np.maximum(0,(abs(V-u)-lim*tau)/lim)
        def characteristic(t):
            p = np.minimum(t,sat)
            w = u+a*p
            r = t-p
            change = -np.expm1(-r/tau)
            return u*p+0.5*a*p*p+V*r+(w-V)*tau*change, w+(V-w)*change
        lo = np.zeros_like(u)
        hi = 2+2*L/V+np.maximum(0,V-u)/acc+2*tau
        assert np.all(characteristic(hi)[0]>=L)
        for _ in range(48):
            m = (lo+hi)/2
            before = characteristic(m)[0]<L
            lo = np.where(before,m,lo)
            hi = np.where(before,hi,m)
        _,v = characteristic(hi)
        speed[active] = v
        times[active,j] = hi
        for k in {0,len(hi)//2,len(hi)-1}:
            ref_t,ref_v = passage(vh,float(u[k]),float(V[k]),float(L[k]))
            max_error=max(max_error,abs(ref_t-hi[k]),abs(ref_v-v[k]))
    assert max_error < 2e-9
    with out.open("w") as f:
        print(len(paths),file=f)
        for i,p in enumerate(paths):
            print(len(p),*(format(x,".17g") for x in times[i,:len(p)]),file=f)
    print(json.dumps(dict(city=city,schedule=calendar.identity,network_sha256=meta["extracted_input_sha256"],
                          passage_sha256=hashlib.sha256(out.read_bytes()).hexdigest(),paths=len(paths),
                          route_edge_occurrences=int((slots>=0).sum()),scalar_subset_max_error=float(max_error))))


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for n in ("repo","prepared","phase_code","output"):
        parser.add_argument(n,type=Path)
    a=parser.parse_args()
    build(a.repo,a.prepared,a.phase_code,a.output)
