"""Guard credit must follow the caller's original immutable input throughout a batch."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def measure(checkpoint):
    from _metroflow_rust import NativeWholeEngine, budget_trace_snapshot
    from test_native_engine import make_native, small_fixture

    _, calendar, payload = make_native(*small_fixture())
    engine = NativeWholeEngine(calendar, payload, 256 * 1024**2, 1, "bounded_bytes_v1")
    initial = engine.initial()
    road = engine.debug_state(initial)["road"]
    assert road["cell_parts"] + road["pending_parts"] == 0

    budget_trace_snapshot(reset=True)
    final = engine.advance(initial, 120)
    trace = budget_trace_snapshot(reset=True)
    credit = trace["counters"]["arc.default_pointer_verified_credit"]
    assert credit == (120, 0, 0), credit
    engine.save(str(checkpoint), final)
    occupied = engine.advance(initial, 40)
    road = engine.debug_state(occupied)["road"]
    assert road["cell_parts"] + road["pending_parts"] > 0

    budget_trace_snapshot(reset=True)
    engine.advance(occupied, 41)
    one_tick = budget_trace_snapshot(reset=False)["counters"]["arc.default_pointer_verified_credit"]
    assert one_tick[0] == 1 and one_tick[1] == one_tick[2] > 0, one_tick
    return {
        "checkpoint": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        "attribution": trace["source_attribution"],
        "exact_census": "exact.intervals" in trace["counters"],
        "guard_calls": trace["sites"]["road_base:components"]["calls"],
    }


def test_original_call_input_and_trace_source_scope(tmp_path):
    observed = []
    for source in (None, "off"):
        env = dict(os.environ, METROFLOW_BUDGET_TRACE="record", PYTHONHASHSEED="0",
                   PYTHONPATH=os.pathsep.join(sys.path))
        env.pop("METROFLOW_TRACE_SOURCE_ATTRIBUTION", None)
        if source:
            env["METROFLOW_TRACE_SOURCE_ATTRIBUTION"] = source
        path = tmp_path / ("full.bin.gz" if source is None else "lean.bin.gz")
        run = subprocess.run([sys.executable, __file__, str(path)], env=env,
                             check=True, capture_output=True, text=True)
        observed.append(json.loads(run.stdout))
    full, lean = observed
    assert full["attribution"] and full["exact_census"]
    assert not (lean["attribution"] or lean["exact_census"])
    assert full["guard_calls"] == lean["guard_calls"] == 120
    assert full["checkpoint"] == lean["checkpoint"]


if __name__ == "__main__":
    print(json.dumps(measure(Path(sys.argv[1]))))
