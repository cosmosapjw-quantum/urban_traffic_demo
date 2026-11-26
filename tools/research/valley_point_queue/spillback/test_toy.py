"""Executable conservation and upstream blocking regression."""
import subprocess
import sys
import tempfile
from pathlib import Path

exe = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory() as t:
    p=Path(t)
    (p/'network').write_text('2 1 1 1 3600\n1 1\n15 1\n2 0 1\n0 3 3600 3603\n0 0 0 3 0 0\n')
    (p/'passages').write_text('1\n2 1 15\n')
    (p/'storage').write_text('2\n2\n1\n')
    def run(h):
        s=subprocess.check_output([str(exe),str(p/'network'),'1','-1','1',str(p/'passages'),str(p/'storage'),str(h)],text=True)
        print(s,end='')
        return [float(x) for x in s.splitlines()[0].split()[1:]], [float(x) for x in s.splitlines()[1].split()[1:]]
    s,e=run(35)
    assert s[:8]==[35,3,3,0,0,3,3,0] and s[9]==1 and s[10]>0 and s[11]>0
    s,e=run(120)
    assert s[:8]==[120,3,3,3,3,0,0,0] and s[9]==1 and s[11]==0
    assert e[4]>0 and e[7]==3
    # Deterministic replay is checked in the same executable.
    assert run(120)==(s,e)
print('PASS: saturated storage, upstream blocking, eventual discharge, independent ledgers, replay')
