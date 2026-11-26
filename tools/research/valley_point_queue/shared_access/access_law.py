"""Finite atom coupling by exact CDF refinement; use original normalized marginals."""
from fractions import Fraction
from collections import defaultdict

def canonical(atoms):
    d=defaultdict(Fraction)
    for t,p in atoms:
        t,p=Fraction(t),Fraction(p)
        if t<0 or p<0: raise ValueError('negative delay or weight')
        if p: d[t]+=p
    total=sum(d.values())
    if total<=0: raise ValueError('empty law')
    return [(t,p/total) for t,p in sorted(d.items())]

def coupled(a,b):
    a,b=canonical(a),canonical(b)
    i=j=0
    x,y=a[0][1],b[0][1]
    out=[]
    while i<len(a) and j<len(b):
        w=min(x,y)
        out.append((a[i][0],b[j][0],w))
        x-=w;y-=w
        if x==0:
            i+=1
            if i<len(a): x=a[i][1]
        if y==0:
            j+=1
            if j<len(b): y=b[j][1]
    assert i==len(a) and j==len(b) and len(out)<=len(a)+len(b)-1
    return out

def verify(a,b,out):
    x,y=defaultdict(Fraction),defaultdict(Fraction)
    for t,s,w in out:
        assert w>0
        x[t]+=w;y[s]+=w
    assert sorted(x.items())==canonical(a) and sorted(y.items())==canonical(b)

def main():
    from itertools import product
    count=0
    for n,m in product(range(1,6),repeat=2):
        for j,k in product(range(1,7),repeat=2):
            a=[(i,Fraction(i+j)) for i in range(n)]
            b=[(2*i,Fraction((m-i)*k+1)) for i in range(m)]
            c=coupled(a,b);verify(a,b,c)
            assert sum(w for _,_,w in c)==1
            assert sum(t*w for t,_,w in c)==sum(t*w for t,w in canonical(a))
            assert sum(s*w for _,s,w in c)==sum(s*w for s,w in canonical(b))
            count+=1
    # Exact shared-space atomic transfer and head eligibility, exhaustive bounded state.
    transfer=0
    for a,b,c,d in product(range(5),repeat=4):
        # two classes, lengths 5 and 12 m
        source=5*a+12*b; target=5*c+12*d; S=64
        if max(source,target)>S:continue
        for length,n in ((5,a),(12,b)):
            for m in range(n+1):
                if target+length*m<=S:
                    x,y=source-length*m,target+length*m
                    assert 0<=x<=S and 0<=y<=S and x+y==source+target
                    transfer+=1
    print(f"exact CDF couplings={count}; exact shared-space transfers={transfer}; passed")
if __name__=='__main__': main()
