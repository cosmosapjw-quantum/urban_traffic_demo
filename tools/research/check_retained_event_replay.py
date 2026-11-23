#!/usr/bin/env python3
"""Matched native old/new replay on the existing mixed-service test calendar.

Run in separate processes with an explicitly selected native extension directory.
This finite check covers both storage policies, nonempty event history, immutable
snapshots, multi-tick versus one-tick calls, and checkpoint restart. It is not a
city-scale timing benchmark.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests/v1"), str(ROOT)]
from test_native_engine import small_fixture, make_native
from _metroflow_rust import NativeWholeEngine, budget_trace_snapshot
from metroflow.v1.native_engine import native_binary_provenance


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def physical_report(native, state):
    row = native.report(state)
    return {k: row[k] for k in ("time_s", "ledger", "released_intent_first_moments",
                               "service", "assignment")}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--label", required=True)
    args = ap.parse_args()
    assert os.environ.get("METROFLOW_BUDGET_TRACE") == "record"
    city, legs, corridors = small_fixture()
    output = {"label": args.label, "native": native_binary_provenance(),
              "script_sha256": digest(Path(__file__)), "policies": {}}
    for policy in ("legacy_records", "bounded_bytes_v1"):
        _, calendar, payload = make_native(city, legs, corridors)
        def fresh():
            return NativeWholeEngine(calendar, payload, 256 * 1024**2, 1, policy)
        native = fresh()
        state = native.initial()
        budget_trace_snapshot(reset=True)
        rows = []
        snapshots = []
        nonempty = 0
        max_events = 0
        with tempfile.TemporaryDirectory(prefix="event-replay-") as tmp:
            tmp = Path(tmp)
            saved = {}
            for t in range(1, 121):
                state = native.advance(state, t)
                event_count = native.debug_state(state)["service_last_events"]
                nonempty += bool(event_count)
                max_events = max(max_events, event_count)
                if t in (1, 3, 5, 10, 15, 30, 60, 120):
                    path = tmp / (str(t) + ".bin")
                    native.save(str(path), state)
                    saved[t] = path
                    report = physical_report(native, state)
                    rows.append(dict(time_s=t, wire_sha256=digest(path),
                                     wire_bytes=path.stat().st_size, physical=report))
                    snapshots.append((state, report))
            assert nonempty > 0, "fixture failed to exercise retained nonempty events"
            for old, report in snapshots:
                assert physical_report(native, old) == report
            batch = fresh()
            batch_state = batch.advance(batch.initial(), 120)
            path = tmp / "batch.bin"
            batch.save(str(path), batch_state)
            assert digest(path) == rows[-1]["wire_sha256"], "batch partition changed wire"
            restarted = fresh()
            restored = restarted.load(str(saved[15]))
            final = restarted.advance(restored, 120)
            restart_path = tmp / "restart.bin"
            restarted.save(str(restart_path), final)
            assert digest(restart_path) == rows[-1]["wire_sha256"], "restart changed wire"
        output["policies"][policy] = dict(
            states=rows, nonempty_event_ticks=nonempty, max_events=max_events,
            snapshot_immutable=True, batch_wire_identical=True,
            restart_wire_identical=True, trace=budget_trace_snapshot(reset=False))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"label": args.label, "native_sha256": output["native"]["sha256"],
          "policies": {k: {x: v[x] for x in ("nonempty_event_ticks", "max_events",
          "batch_wire_identical", "restart_wire_identical")} for k, v in output["policies"].items()}}))


if __name__ == "__main__":
    main()
