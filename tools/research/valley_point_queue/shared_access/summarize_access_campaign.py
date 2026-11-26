"""Verify class, shared-space, receiving and horizon receipts (not native acceptance)."""
import argparse
import hashlib
import json
import math
import pathlib
import re

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('directory',type=pathlib.Path)
    parser.add_argument('--out',type=pathlib.Path,required=True)
    args=parser.parse_args()
    d=args.directory
    meta=json.loads((d/'access/input_summary.json').read_text())
    for name,key in [('network.txt','network_sha256'),('passages.txt','passages_sha256')]:
        with (d/'access'/name).open('rb') as f:
            assert hashlib.file_digest(f,'sha256').hexdigest()==meta[key], name
    expected=[meta['expected_vehicle_trips'][k] for k in meta['classes']]
    result=[]
    def close(a,b):
        assert math.isclose(a,b,rel_tol=0,abs_tol=1e-6),(a,b)
    for file in sorted(d.glob('access*_*.txt')):
        m=re.fullmatch(r'access(\d+)_(\d+)\.txt',file.name)
        assert m,file
        mesh,horizon=map(int,m.groups())
        lines=file.read_text().splitlines()
        snapshots={}
        classes={}
        end=None
        for line in lines:
            tag,*items=line.split()
            vals=list(map(float,items))
            assert all(math.isfinite(v) for v in vals),line
            if tag=='snap':
                assert len(vals)==16,line
                t=vals[0]
                assert t not in snapshots
                snapshots[t]=vals
                assert abs(vals[7])<=1e-6 and abs(vals[14])<=1e-6
                assert -1e-9<=vals[9]<=1+1e-9 and -1e-9<=vals[15]<=1+1e-9
                close(vals[1],vals[4]+vals[5])
                close(vals[2]-vals[3],vals[6])
            elif tag=='class':
                assert len(vals)==11,line
                t,c=vals[:2]
                assert c in (0,1,2) and (t,c) not in classes
                classes[t,c]=vals
                close(vals[2],expected[int(c)])
                close(vals[3],vals[6]+vals[7])
                close(vals[4]-vals[5],vals[8])
                assert abs(vals[9])<=1e-6
            elif tag=='end':
                assert end is None and len(vals)==9
                end=vals
            elif tag=='purpose':
                assert len(vals)==3 and min(vals)>=0,line
            else:
                raise AssertionError(line)
        assert snapshots and end is not None and max(snapshots)==horizon,file
        assert len(classes)==3*len(snapshots)
        for t,s in snapshots.items():
            for i,j in [(1,3),(2,4),(3,5),(4,6),(5,7),(6,8)]:
                close(s[i],sum(classes[t,c][j] for c in range(3)))
        timing=re.fullmatch(r'wall_s=([0-9.]+) peak_rss_kib=(\d+)\s*',file.with_suffix('.time').read_text())
        assert timing,file
        s=snapshots[horizon]
        completed=horizon==86400 and abs(s[4]-sum(expected))<1e-6 and abs(s[5])<1e-6
        result.append(dict(mesh_s=mesh,horizon_s=horizon,wall_s=float(timing[1]),peak_rss_kib=int(timing[2]),
            expected_total=sum(expected),released=s[1],admitted=s[2],exited=s[3],completed=s[4],active=s[5],road_stock=s[6],
            max_mass_error=max([abs(v[7]) for v in snapshots.values()]+[abs(v[9]) for v in classes.values()]),
            max_meter_error=max(abs(v[14]) for v in snapshots.values()),max_storage_ratio=s[9],max_receiving_ratio=s[15],
            storage_blocks=int(s[12]),rate_blocks=int(s[13]),waiting_veh_s=end[3],blocked_veh_s=end[4],event_count=int(end[2]),
            veh_trip_seconds=end[8],full_day_all_projected_trips_completed=completed,
            per_class=[dict(class_name=meta['classes'][c],expected=classes[horizon,c][2],completed=classes[horizon,c][6],active=classes[horizon,c][7],trip_seconds=classes[horizon,c][10]) for c in range(3)]))
    assert result
    out=dict(scope='fixed-route access-resolved three-class projection; not native V03',input_sha256=meta['network_sha256'],passages_sha256=meta['passages_sha256'],runs=result)
    args.out.write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out,indent=2))
if __name__=='__main__':
    main()
