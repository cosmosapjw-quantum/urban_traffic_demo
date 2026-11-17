"""Compare two probe_v1_event_store.py results (physical report and storage).

usage: compare_prefix.py BASELINE.json CANDIDATE.json OUT.json
"""
import json, math, sys

base, cand = (json.load(open(p)) for p in sys.argv[1:3])


def walk(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k in a and k in b:
                yield from walk(a[k], b[k], f"{path}.{k}" if path else k)
            else:
                yield path + "." + k, a.get(k), b.get(k), None
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        d = b - a
        rel = abs(d) / max(abs(a), abs(b), 1e-300) if d else 0.0
        yield path, a, b, (d, rel)
    elif a != b:
        yield path, a, b, None


diffs = [dict(path=p, baseline=a, candidate=b, diff=None if r is None else r[0],
              rel=None if r is None else r[1])
         for p, a, b, r in walk(base["report"]["execution"], cand["report"]["execution"])
         if r is None or r[0] != 0]
road = lambda d: {k: v for k, v in d["debug"]["road"].items() if isinstance(v, (int, float))}
out = dict(
    scope="same input Valley h=1 prefix; physical report execution section compared exactly",
    baseline=dict(status=base["status"], simulated_s=base["simulated_s"], wall_s=base["wall_s"],
                  peak_rss_bytes=base["peak_rss_bytes"], road=road(base), checkpoint=base["checkpoint"]),
    candidate=dict(status=cand["status"], simulated_s=cand["simulated_s"], wall_s=cand["wall_s"],
                   peak_rss_bytes=cand["peak_rss_bytes"], road=road(cand), checkpoint=cand["checkpoint"]),
    execution_differences=diffs,
    max_rel_numeric=max([d["rel"] for d in diffs if d["rel"] is not None] or [0.0]),
)
json.dump(out, open(sys.argv[3], "w"), indent=1, sort_keys=True)
print(json.dumps(dict(n_diff=len(diffs), max_rel=out["max_rel_numeric"]), indent=1))
for d in diffs:
    print(d["path"], d["baseline"], d["candidate"], d["rel"])
