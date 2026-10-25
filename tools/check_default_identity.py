"""Capture immutable default fingerprints before and after adding policy hooks."""

from pathlib import Path
import sys
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from metroflow.active_suffix import Model, Road, Demand, Config
from metroflow.active_suffix.packed import PackedModel

roads = (
    Road("oa", "O", "A", 100.0, 10.0, 1.0, 20.0),
    Road("ad", "A", "D", 100.0, 10.0, 1.0, 20.0),
    Road("ob", "O", "B", 180.0, 10.0, 1.0, 30.0),
    Road("bd", "B", "D", 180.0, 10.0, 1.0, 30.0),
)
rows = []
for cls in (Model, PackedModel):
    for closed in (False, True):
        m = cls(
            roads,
            (Demand("O", "D", 0.0, 80.0, 0.5),),
            Config(dt_s=2.0, paths_per_od=2, adaptive_routes=True),
            capacity_windows=(("ad", 20.0, 60.0, 0.0),) if closed else (),
        )
        s = m.initial()
        records = []
        for _ in range(100):
            s = m.step(s)
            records.append(m.fingerprint(s))
        rows.append(dict(model=cls.__name__, closure=closed, fingerprints=records))
print(json.dumps(rows, indent=2))
