#!/usr/bin/env python3
"""Read bounded actual FIFO heads from a SHA-bound MFWHOLE1 checkpoint.

The codec is pinned to V1Road::write_state/write_packets. This is a read-only
sample of road heads, not a replacement state loader or full checkpoint audit.
"""
import argparse
import hashlib
import json
import math
import mmap
from pathlib import Path
import struct
import numpy as np

ROW = np.dtype([("tag","<u8"),("offset","<u8"),("mass","<f8"),("birth","<f8"),
                ("has_a","<u8"),("a","<f8"),("has_b","<u8"),("b","<f8")])

class Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0
    def read(self, n):
        if n < 0 or self.pos+n > len(self.data):
            raise ValueError("truncated checkpoint")
        b = self.data[self.pos:self.pos+n]; self.pos += n
        return b
    def u64(self):
        return struct.unpack("<Q",self.read(8))[0]
    def f64(self):
        return struct.unpack("<d",self.read(8))[0]
    def text(self):
        n=self.u64()
        if n>4096:raise ValueError("unexpected checkpoint identity size")
        return self.read(n).decode()
    def rows(self, n, keep):
        if n > 100_000_000:raise ValueError("invalid row count")
        # An all-Some packet has a verified fixed 64-byte wire row. The first
        # absent endpoint makes this test fail and selects the variable codec.
        if self.pos+n*64 <= len(self.data):
            a=np.frombuffer(self.data,dtype=ROW,count=n,offset=self.pos)
            fixed=bool(np.all(a["has_a"]==1) and np.all(a["has_b"]==1))
            if fixed:
                rows=([{"tag":int(x["tag"]),"offset":int(x["offset"]),
                        "mass":float(x["mass"]),"birth":float(x["birth"]),
                        "a":float(x["a"]),"b":float(x["b"])} for x in a] if keep else [])
                self.pos += n*64
                del a
                return rows
            del a
        rows=[]
        for _ in range(n):
            tag,offset,mass,birth=self.u64(),self.u64(),self.f64(),self.f64()
            ends=[]
            for _ in range(2):
                present=self.u64()
                if present not in (0,1):raise ValueError("invalid endpoint option")
                ends.append(self.f64() if present else None)
            if keep:rows.append(dict(tag=tag,offset=offset,mass=mass,birth=birth,a=ends[0],b=ends[1]))
        return rows

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkpoint",type=Path,required=True)
    p.add_argument("--receipt",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    receipt=json.loads(args.receipt.read_text())
    digest=hashlib.sha256()
    with args.checkpoint.open("rb") as f:
        while b:=f.read(1024*1024):digest.update(b)
    if (digest.hexdigest(),args.checkpoint.stat().st_size)!=(receipt["final_checkpoint_sha256"],receipt["final_checkpoint_bytes"]):
        raise ValueError("sample checkpoint differs from recorded bytes")
    selected=[];total_heads=0
    with args.checkpoint.open("rb") as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as data:
        r=Reader(data)
        if r.read(8)!=b"MFWHOLE1":raise ValueError("unsupported whole-engine wire")
        engine,road,time_s=r.text(),r.text(),r.f64()
        if time_s!=receipt["completed_time_s"]:raise ValueError("clock mismatch")
        cell_count=r.u64()
        if not 0<cell_count<=100_000:raise ValueError("invalid cell count")
        for cell in range(cell_count):
            state=[r.f64() for _ in range(8)]
            count=r.u64()
            if count>10_000_000:raise ValueError("invalid packet count")
            for i in range(count):
                target,n=r.f64(),r.u64()
                keep=i==0 and 2<=n<=4096 and (len(selected)<3 or n>len(selected[-1]["rows"]))
                rows=r.rows(n,keep)
                if i==0:total_heads+=1
                if keep:
                    if any(not math.isfinite(x[k]) for x in rows for k in ("mass","birth")):
                        raise ValueError("nonfinite head")
                    if any(x["mass"]<=0 for x in rows):raise ValueError("nonpositive head")
                    selected.append(dict(cell=cell,packet_index=0,target=target,cell_state=state,rows=rows))
                    selected.sort(key=lambda v:(-len(v["rows"]),v["cell"]))
                    selected=selected[:3]
            latent_count=r.u64()
            if latent_count>10000:raise ValueError("invalid class count")
            r.read(latent_count*16)
        end=r.pos
    if not selected:raise ValueError("no eligible full head found")
    result=dict(schema="METROFLOW_BOUNDED_ORIGINAL_HEAD_SAMPLE_V1",
                source_checkpoint_sha256=digest.hexdigest(),source_checkpoint_bytes=args.checkpoint.stat().st_size,
                source_receipt=str(args.receipt),time_s=time_s,engine_identity=engine,road_identity=road,
                road_cells_scanned=cell_count,first_packets_seen=total_heads,road_cells_wire_end=end,
                selection="largest complete first-packet compositions with 2..4096 rows; deterministic cell tie break",
                interpretation="actual source mixtures; not observed future service fractions or whole-network execution",
                heads=selected)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
    print(json.dumps(dict(time_s=time_s,cells=cell_count,heads_seen=total_heads,
                         selected=[(h["cell"],len(h["rows"])) for h in selected],output=str(args.out))))

if __name__=="__main__":main()
