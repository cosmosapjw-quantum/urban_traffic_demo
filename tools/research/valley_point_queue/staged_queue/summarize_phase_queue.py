"""Cross-check the phase queue against a two-batch fixture and C07 matched runs."""
import argparse
import hashlib
import json
import math
import subprocess
import tempfile
from pathlib import Path


def parse(text):
    snap_keys = ("released","admitted","exited","completed","active","road","residual")
    sum_keys = ("planned_out","initial_batches","events","wait_veh_s","largest_delay_link",
                "largest_link_wait_veh_s","max_wait_on_largest_link_s","trip_veh_s")
    snapshots = {}
    final = None
    for line in text.splitlines():
        tag,*vals = line.split()
        if tag=="snap":
            t,*v = map(float,vals)
            snapshots[int(t)] = dict(zip(snap_keys,v,strict=True))
        elif tag=="end":
            final = dict(zip(sum_keys,map(float,vals),strict=True))
    assert final and snapshots
    return dict(snapshots=snapshots,final=final)


def run(prep, results, solver, onset_reference):
    report = {}
    with tempfile.TemporaryDirectory() as d:
        td=Path(d)
        (td/"net").write_text("1 1 2 1 50000\n10 0.5\n1 0\n0 100 200 300\n0 0 0 1 0 0\n0 0 0 1 0 0\n")
        (td/"kin").write_text("1\n1 7\n")
        for t,expected in ((69,(0,2)),(70,(1,1)),(80,(2,0))):
            vals = parse(subprocess.check_output([solver,td/"net","100","-1","1",td/"kin",str(t)],text=True))
            snap = vals["snapshots"][t]
            assert (snap["exited"],snap["road"])==expected and snap["residual"]==0
            assert vals["final"]["wait_veh_s"]==2
        assert vals["final"]["trip_veh_s"]==50
        report["two_batch_end_times_s"]=[70,80]
    report["preparation"] = json.loads((results/"preparation.json").read_text())
    source_dir = Path(__file__).resolve().parent
    report["source_sha256"] = {name: hashlib.sha256((source_dir/name).read_bytes()).hexdigest()
                               for name in ("prepare_phase_passages.py","phase_queue.diff","summarize_phase_queue.py")}
    report["solver_sha256"] = hashlib.sha256(solver.read_bytes()).hexdigest()
    report["onset_reference_sha256"] = hashlib.sha256(onset_reference.read_bytes()).hexdigest()
    arms={}
    for n in (600,300,150,10):
        f=prep/(f"base_{n}.out" if n!=10 else "prefix_10.out")
        r=results/f"phase_{n}.out"
        base,phase=(parse(p.read_text()) for p in (f,r))
        assert set(base["snapshots"])==set(phase["snapshots"])
        for row in phase["snapshots"].values():
            assert row["residual"]<1e-7
        if n!=10:
            last=phase["snapshots"][86400]
            assert all(math.isclose(last[k],2*phase["final"]["planned_out"],rel_tol=0,abs_tol=1e-6)
                       for k in ("released","admitted","exited","completed"))
            assert last["active"]==last["road"]==0
        tfile = results/f"phase_{n}.time"
        sec,ram=map(float,tfile.read_text().split())
        arms[n]=dict(baseline=base,phase_queue=phase,wall_s=sec,max_rss_KiB=int(ram),
                     baseline_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),
                     phase_stdout_sha256=hashlib.sha256(r.read_bytes()).hexdigest())
    report["matched_bins_s"]=arms
    onset_doc=json.loads(onset_reference.read_text())
    sidecar = report["preparation"]
    assert (sidecar["city"],sidecar["schedule"],sidecar["network_sha256"]) == (
        onset_doc["city"],onset_doc["schedule"],onset_doc["network_sha256"])
    ref=onset_doc["clocks"]["25720"]
    naive=ref["arms"]["prior_point_queue"]["exited_veh"]
    raw=arms[10]["baseline"]["snapshots"][25720]
    assert abs(raw["exited"]-naive)<1e-9
    native=ref["native_exited_veh"]
    rev=arms[10]["phase_queue"]["snapshots"][25720]
    report["onset_25720"]=dict(native_exited=native,native_admitted=ref["native_admitted_veh"],
          native_stock=ref["native_admitted_veh"]-native,atom_access_unconstrained=ref["arms"]["native_link_phase"]["exited_veh"],
          baseline_exited=raw["exited"],stage_queue_exited=rev["exited"],stage_queue_stock=rev["road"],
          outlet_abs_error_reduction=1-abs(rev["exited"]-native)/abs(raw["exited"]-native))
    forward = {}
    for t in (25730,25740):
        path = results/f"forward_{t}.out"
        if path.is_file():
            result = parse(path.read_text())
            snap = result["snapshots"][t]
            assert snap["residual"]<1e-7
            forward[t]=dict(admitted=snap["admitted"],exited=snap["exited"],road=snap["road"],
                            stdout_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    report["forward_queue_outputs"] = forward
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("prepared","results","solver","onset_reference","output"):
        p.add_argument(name,type=Path)
    a=p.parse_args()
    a.output.write_text(json.dumps(run(a.prepared,a.results,a.solver.resolve(),a.onset_reference),indent=2,allow_nan=False)+"\n")
