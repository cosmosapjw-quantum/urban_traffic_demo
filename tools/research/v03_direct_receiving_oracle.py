"""Independent exact-rational interval and canonical code-stream oracle."""
from fractions import Fraction as F
from collections import defaultdict
import random,json,struct
rng=random.Random(20261128)
cases=512;windows=0;atoms=0;code_checks=0
def first_codes(values):
    dictionary={};seq=[]
    for x in values:
        if x not in dictionary: dictionary[x]=len(dictionary)
        seq.append(dictionary[x])
    return seq,list(dictionary)
for i in range(cases):
    rows=[]
    for _ in range(rng.randrange(4,25)):
        k=rng.randrange(4);a=F(rng.randrange(20),4);b=a+F(rng.randrange(9),4)
        m=F(rng.randrange(1,20),16);birth=m*F(rng.randrange(100),16)
        rows.append((k,a,b,m,birth))
    E=sorted({e for _,a,b,_,_ in rows for e in (a,b)})
    dense=defaultdict(lambda:[F(0),F(0)])
    point=defaultdict(lambda:[F(0),F(0)])
    for k,a,b,m,B in rows:
        if a==b:point[k,a][0]+=m;point[k,a][1]+=B;atoms+=1
        else:
            for u,v in zip(E,E[1:]):
                if a<=u<v<=b:
                    r=(v-u)/(b-a);dense[k,u,v][0]+=m*r;dense[k,u,v][1]+=B*r
    for k in range(4):
        for l,u in enumerate(E):
            for v in E[l:]:
                # Half-open interval (u,v], with point atoms at right edge.
                original=[F(0),F(0)]
                for tag,a,b,m,B in rows:
                    if tag!=k:continue
                    r=F(int(u<a<=v)) if a==b else max(F(0),min(v,b)-max(u,a))/(b-a)
                    original[0]+=r*m;original[1]+=r*B
                actual=[sum((x[z] for (tag,a,b),x in dense.items() if tag==k and u<=a<b<=v),F(0))+sum((x[z] for (tag,a),x in point.items() if tag==k and u<a<=v),F(0)) for z in range(2)]
                assert original==actual and v*original[0]-original[1]==v*actual[0]-actual[1]
                windows+=1
    # A distinct numeric value per code may be changed independently; only
    # the ordinal partition is reusable, never the old dictionary values.
    ords=[rng.randrange(8) for _ in range(128)]
    vals=[struct.pack('<dd',float(j+1),float(2*j)) for j in ords]
    vals2=[struct.pack('<dd',float(j+100),float(2*j+1)) for j in ords]
    c,d=first_codes(vals);c2,d2=first_codes(vals2)
    assert c==c2 and d!=d2 and [d2[j] for j in c]==vals2
    code_checks+=len(c)
print(json.dumps(dict(status='PASS',arithmetic='Fraction',seed=20261128,cases=cases,marked_windows=windows,point_atoms=atoms,code_ordinal_checks=code_checks,scope='exact rational common refinement and independent first-occurrence ordinal partition; not full floating dynamics'),indent=2))
