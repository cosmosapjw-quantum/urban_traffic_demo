"""Emit reproducible subprocess evidence for this bounded research scope."""
from pathlib import Path
import ast,hashlib,json,os,platform,subprocess,sys,time


def main():
    root=Path(__file__).resolve().parents[1]
    out=root/'artifacts/terrain_zones_20261024';out.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,PYTHONPATH=str(root/'src'))
    cmds=[['-m','pytest','-q',*map(str,sorted((root/'tests').glob('test_environment_*.py')))],
          ['-m','compileall','-q','src/metroflow/environment','src/metroflow/active_suffix'],
          ['-S','tools/run_environment_map.py'],['-S','tools/run_environment_traffic.py'],
          ['-S','tools/audit_environment.py']]
    rows=[]
    for i,args in enumerate(cmds):
        start=time.perf_counter();run=subprocess.run([sys.executable,*args],cwd=root,env=env,
                              capture_output=True,text=True,timeout=30)
        log=out/f'final_command_{i}.txt';log.write_text(run.stdout+run.stderr)
        rows.append(dict(command=[sys.executable,*args],exit_code=run.returncode,
                         elapsed_s=time.perf_counter()-start,log=log.name))
        if run.returncode:raise RuntimeError(f'command failed: {log}')
    sources={}
    for folder in ('environment','active_suffix'):
        for path in sorted((root/'src/metroflow'/folder).glob('*.py')):
            data=path.read_bytes();tree=ast.parse(data)
            for node in ast.walk(tree):
                imports=[]
                if isinstance(node,ast.Import):imports=[x.name.split('.')[0] for x in node.names]
                elif isinstance(node,ast.ImportFrom) and node.level==0:imports=[node.module.split('.')[0]]
                assert all(x in sys.stdlib_module_names for x in imports),(path,imports)
            sources[str(path.relative_to(root))]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
                         git_blob=hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest())
    receipt=dict(status='PASS_SCOPED',python=platform.python_version(),commands=rows,
             stdlib_ast_scan=True,sources=sources,whole_repository_ci='NOT_RUN',local_100k_full_day='NOT_RUN',
             graphics='NOT_RUN',native_subagent='NOT_RUN')
    (out/'FINAL_VERIFICATION.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt,indent=2))

if __name__=='__main__':main()
