"""Read-only census of MFWHOLE3 road section, not a full checkpoint validator."""
import sys,struct,json,hashlib,time
from collections import Counter
import numpy as np
from pathlib import Path
p=Path(sys.argv[1]);start=time.monotonic()
c=Counter();hist=Counter();ratios=[]
with p.open('rb',buffering=1024*1024) as f:
 def read(n):
  x=f.read(n)
  if len(x)!=n:raise EOFError((f.tell(),n,len(x)))
  return x
 def u():return struct.unpack('<Q',read(8))[0]
 def skip(n):f.seek(n,1)
 magic=read(8);assert magic in (b'MFWHOLE2',b'MFWHOLE3')
 ident=read(u()).decode();road_ident=read(u()).decode();time_s=struct.unpack('<d',read(8))[0]
 def queue():
  prev=None
  for _ in range(u()):
   skip(8);n=u();kind=u()
   c['packets']+=1;c['rows']+=n;hist[str(kind)]+=n
   if kind==1:skip(48*n);continue
   assert kind in (0,2,3)
   ab=read(16)
   if kind==0:
    arr=np.frombuffer(read(24*n),dtype=np.dtype([('k','<u8'),('m','<u8'),('b','<u8')]))
    m=arr[['m','b']].copy() if False else None
    vals=np.empty(n,dtype=[('m','<u8'),('b','<u8')]);vals['m']=arr['m'];vals['b']=arr['b']
   else:
    if kind==2:prev=n;skip(8*n)
    else:assert prev==n
    vals=np.frombuffer(read(16*n),dtype=[('m','<u8'),('b','<u8')])
   c['uniform_rows']+=n
   # exact bit pairs; sample all packets >=16, smaller remain dense
   if n<16:continue
   c['eligible_rows']+=n;c['eligible_packets']+=1
   # counts of dictionary entries. u16 indices when <=65536 values, else u32.
   k=len(np.unique(vals))
   c['unique_pairs']+=k
   cost=16*k+n*(2 if k<=65536 else 4)+96
   dense=16*n
   if cost<dense:
    c['dictionary_packets']+=1;c['dictionary_rows']+=n;c['potential_moment_payload_saved_bytes']+=dense-cost
   runs=1+int(np.count_nonzero((vals['m'][1:]!=vals['m'][:-1])|(vals['b'][1:]!=vals['b'][:-1])))
   c['runs']+=runs
   if 20*runs+96<dense:
    c['run_packets']+=1;c['potential_run_saved_bytes']+=dense-(20*runs+96)
 cells=u()
 for _ in range(cells):skip(64);queue();skip(16*u())
 pending=u()
 for _ in range(pending):queue()
 skip(56);skip(40*u())
 end=f.tell()
print(json.dumps(dict(status='READ_ONLY_ROAD_CENSUS',source=str(p),magic=magic.decode(),identity=ident,road_identity=road_ident,time_s=time_s,cells=cells,pending=pending,road_section_end=end,counts=dict(c),rows_by_kind=dict(hist),elapsed_s=time.monotonic()-start,scope='all road packets; potential independent per-packet bit-pair dictionary capacity savings, not measured allocator/RSS; no full validation'),indent=2))
