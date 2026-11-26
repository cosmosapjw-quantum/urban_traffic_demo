"""Conservation, shared footprints, rate tokens, FIFO and deterministic replay."""
import pathlib,subprocess,tempfile,sys
from math import isclose
def run(exe,storage,entry,groups):
    with tempfile.TemporaryDirectory() as td:
        p=pathlib.Path(td)
        (p/'n').write_text(f'1 1 {len(groups)} 1 0\n1 {entry} 1 {storage}\n1 0\n0 0 0 0\n'+'\n'.join(groups)+'\n')
        (p/'t').write_text('1\n1 1\n')
        cmd=[str(exe),str(p/'n'),'600','-1','1',str(p/'t'),'120','7']
        r=subprocess.check_output(cmd,text=True);assert r==subprocess.check_output(cmd,text=True)
        sn=next(x for x in r.splitlines() if x.startswith('snap ')).split()
        cl=[x.split() for x in r.splitlines() if x.startswith('class ')]
        assert float(sn[5])==len(groups) and float(sn[6])==0 and float(sn[8])<1e-10
        assert float(sn[14])<1e-9 and float(sn[15])<=1+1e-9
        assert all(float(c[10])<1e-10 for c in cl)
        return r,sn,cl
if __name__=='__main__':
    exe=pathlib.Path(sys.argv[1]).resolve()
    # Bus and car cannot occupy 12m at the same time; same count with wrong
    # car-only footprint would admit both. Enough entry budget isolates storage.
    g=['0 -1 0 1 0 0 2 0','0 -1 0 1 0 0 0 1']
    r,s,c=run(exe,12,1,g);print(r,end='')
    assert float(s[10])==1 and int(s[12])>0 and int(s[13])==0
    # Unlimited storage for these two atoms, one vehicle per tick shared supply.
    r,s,c=run(exe,100,.1,g);print(r,end='')
    assert int(s[12])==0 and int(s[13])>0 and float(s[15])==1
    # Class identity and completion counts independently certified.
    assert float(c[0][7])==1 and float(c[2][7])==1
    print('PASS mixed storage, aggregate tick supply, class conservation, deterministic replay')
