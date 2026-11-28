#!/usr/bin/env python3
"""Validate/render the authoritative embedded AKM DAG; never auto-run a node."""
import argparse,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DOC=ROOT/'docs/akm/RESEARCH_SSOT_KO.md'
PASS={'VERIFIED_SCOPED','ACCEPTED'}
TERMINAL=PASS|{'STOPPED','BLOCKED_TERMINAL'}
STATUSES=TERMINAL|{'PLANNED','READY','IN_PROGRESS','BLOCKED'}
def load():
    s=DOC.read_text()
    a=re.findall(r'<!-- AKM_DAG_BEGIN -->\s*```json\s*(.*?)\s*```\s*<!-- AKM_DAG_END -->',s,re.S)
    assert len(a)==1,'single authoritative DAG block required'
    return json.loads(a[0])
def validate(p):
    assert p['plan_id']=='METROFLOW-AKM' and p['maximum_work_in_progress']<=2
    assert p['maximum_candidates']==3 and 0<p['max_reference_work_fraction']<=.15
    nodes=p['nodes']; by={n['id']:n for n in nodes}
    assert len(nodes)==len(by)==14 and list(by)==[f'D{i:02d}' for i in range(14)]
    assert sum(n['max_attempts'] for n in nodes)==p['maximum_total_attempts']==24
    assert sum(n['status']=='IN_PROGRESS' for n in nodes)<=p['maximum_work_in_progress']
    for n in nodes:
        assert n['status'] in STATUSES and 0<=n['attempts_used']<=n['max_attempts']<=2
        assert n['question'] and n['deliverable'] and n['claim_gate']
        deps=n['requires']+n['requires_terminal']
        assert len(deps)==len(set(deps)) and all(x in by and x<n['id'] for x in deps)
        if n['status'] in TERMINAL:
            assert n.get('evidence') and (ROOT/n['evidence']).is_file(),n['id']
        if n['status'] in PASS|{'READY','IN_PROGRESS'}:
            assert all(by[x]['status'] in PASS for x in n['requires'])
            assert all(by[x]['status'] in TERMINAL for x in n['requires_terminal'])
        if n['status'] not in TERMINAL:assert n['attempts_used']<n['max_attempts'],n['id']
    # strictly increasing indices on every edge guarantee acyclicity.
    assert 'D13' in by and all(x in by for x in ['D11','D12'])
    return by
def ready(p,by):
    return [n['id'] for n in p['nodes'] if n['status'] in {'PLANNED','READY'} and all(by[x]['status'] in PASS for x in n['requires']) and all(by[x]['status'] in TERMINAL for x in n['requires_terminal'])]
def views(p):
    dot=['digraph AKM {','  rankdir=LR;','  node [shape=box];']
    mer=['flowchart TD']
    for n in p['nodes']:
        i=n['id']; label=i+' '+n['name']+' ['+n['status']+']'
        dot.append('  '+i+' [label='+json.dumps(label,ensure_ascii=False)+'];')
        mer.append(f'  {i}["{label}"]')
        for x in n['requires']:dot.append(f'  {x} -> {i};');mer.append(f'  {x} --> {i}')
        for x in n['requires_terminal']:dot.append(f'  {x} -> {i} [style=dashed,label="terminal"];');mer.append(f'  {x} -. terminal .-> {i}')
    dot.append('}')
    return {'DAG.dot':'\n'.join(dot)+'\n','DAG.mmd':'\n'.join(mer)+'\n'}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=['validate','render','next']);args=ap.parse_args()
    p=load();by=validate(p);v=views(p)
    if args.command=='render':
        for f,s in v.items():(DOC.parent/f).write_text(s)
    elif args.command=='validate':
        for f,s in v.items():assert (DOC.parent/f).read_text()==s,f+' generated view differs'
    r=ready(p,by)
    print(json.dumps({'status':'VALID_RESEARCH_PLAN_NOT_RELEASE','nodes':len(by),'scoped_or_accepted':sum(n['status'] in PASS for n in by.values()),'terminal':sum(n['status'] in TERMINAL for n in by.values()),'attempts_used':sum(n['attempts_used'] for n in by.values()),'attempts_limit':p['maximum_total_attempts'],'ready':r,'next':r[:max(0,p['maximum_work_in_progress']-sum(n['status']=='IN_PROGRESS' for n in by.values()))]},ensure_ascii=False))
if __name__=='__main__':main()
