"""Research-only bounded-budget A/B on one physical MFWHOLE1 checkpoint.

Use the exact same native extension and MFWHOLE1 input for both arms. Run a
separate outer process per arm. The optional larger internal allowance is a
conditional restart and never an original-release or from-zero receipt.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import struct
import sys
import time


GiB = 1024**3
OLD_BUDGET = 6 * GiB
PHYSICAL_KEYS = ("time_s", "city_identity", "schedule_identity", "assignment", "ledger",
                 "released_intent_first_moments", "service")


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def emit(path, phase, **data):
    with path.open("a") as handle:
        print(json.dumps(dict(phase=phase, **data), allow_nan=False), file=handle, flush=True)


def read_header(reader):
    magic = reader.read(8)
    if magic != b"MFWHOLE1":
        raise ValueError("unsupported wire schema")
    strings = []
    for _ in range(2):
        length = struct.unpack("<Q", reader.read(8))[0]
        if not 1 <= length <= 256:
            raise ValueError("bad identity field width")
        strings.append(reader.read(length))
    if strings[0] != strings[1]:
        raise ValueError("expected identical whole and road bindings")
    return magic, strings


def encode_header(magic, identities):
    return magic + b"".join(struct.pack("<Q", len(s)) + s for s in identities)


def rebind(raw, target, budget, expected_raw_sha):
    """Replace exactly the documented two binding fields; validate copied output off disk."""
    if target.exists():
        raise FileExistsError(target)
    old, new = str(OLD_BUDGET).encode(), str(budget).encode()
    if len(old) != len(new):
        raise ValueError("this control requires equal-width decimal budget fields")
    original, tail_hash = hashlib.sha256(), hashlib.sha256()
    with raw.open("rb") as source, target.open("xb") as out:
        magic, old_ids = read_header(source)
        old_header = encode_header(magic, old_ids)
        original.update(old_header)
        fields = old_ids[0].split(b":")
        if (len(fields) != 5 or fields[0] != b"native-whole-v1" or len(fields[1]) != 64
                or fields[2:] != [old, b"bounded_bytes_v1", b"retained_capacity_v3"]):
            raise ValueError("unrecognized binding grammar")
        fields[2] = new
        new_id = b":".join(fields)
        new_header = encode_header(magic, [new_id] * 2)
        out.write(new_header)
        for block in iter(lambda: source.read(4 * 1024**2), b""):
            original.update(block)
            tail_hash.update(block)
            out.write(block)
    if original.hexdigest() != expected_raw_sha or raw.stat().st_size != target.stat().st_size:
        raise ValueError("original digest or copied size differs")
    with target.open("rb") as check:
        if read_header(check) != (magic, [new_id, new_id]):
            raise ValueError("rebound disk identity differs")
        if hashlib.file_digest(check, "sha256").hexdigest() != tail_hash.hexdigest():
            raise ValueError("physical bytes changed")
    return dict(original_sha256=original.hexdigest(), rebound_sha256=digest(target),
                suffix_sha256=tail_hash.hexdigest(), suffix_bytes=raw.stat().st_size-len(new_header),
                header_bytes=len(new_header), differing_byte_offsets=[
                    i for i,(x,y) in enumerate(zip(old_header,new_header)) if x != y],
                old_native_identity=old_ids[0].decode(), new_native_identity=new_id.decode())


def build_driver(case, matrix, budget):
    from tools.run_v1_local_acceptance import (
        load_release_city, compile_activity, compile_factorized_demand, ReleasePlan,
        InventoryPolicy, build_inventory)
    from metroflow.v1.native_release_driver import NativeReleaseDriver

    city, _ = load_release_city(case)
    homes = tuple(compile_activity(city, b.id) for b in city.face_graph.blocks if b.residents)
    jobs = tuple(compile_activity(city, b.id, "job") for b in city.face_graph.blocks if b.jobs)
    services = tuple(compile_activity(city, b.id, "service", service_stock=b.jobs)
                     for b in city.face_graph.blocks if b.jobs)
    schedule = compile_factorized_demand(homes, jobs, services, day=case["day"], freight_kg=1000,
                                        worker_shortfall=matrix["worker_shortfall"])
    plan = ReleasePlan(city, schedule, step_s=10.)
    policy = dict(matrix["inventory_policy"])
    policy["departures_s"] = tuple(policy["departures_s"])
    return NativeReleaseDriver(plan, build_inventory(city, InventoryPolicy(**policy)),
                               byte_budget=budget, native_threads=1, step_s=10.,
                               storage_policy="bounded_bytes_v1")


def compare_physics(report, reference):
    for key in PHYSICAL_KEYS:
        if report[key] != reference[key]:
            raise ValueError("restored report differs for " + key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "raw", "reference", "result"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--native-sha256", required=True)
    parser.add_argument("--internal-bytes", type=int, required=True)
    parser.add_argument("--steps", type=int, default=12)
    args = parser.parse_args()
    if args.result.exists() or args.internal_bytes not in (OLD_BUDGET, 15*GiB//2) or args.steps <= 0:
        raise ValueError("require unused receipt and controlled arm")
    resource.setrlimit(resource.RLIMIT_AS, (8*GiB, 8*GiB))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    sys.path[:0] = [str(args.repo), str(args.repo/"src")]
    from metroflow.v1.native_engine import native_binary_provenance
    from tools.run_v1_local_acceptance import _ledger_error
    from _metroflow_rust import budget_trace_snapshot

    started = time.monotonic()
    ref = json.loads(args.reference.read_text())
    matrix_path = args.repo/"scenarios/v1/release_matrix.json"
    matrix = json.loads(matrix_path.read_text())
    assert digest(matrix_path) == ref["original_matrix_sha256"]
    assert resource.getrlimit(resource.RLIMIT_AS)[0] == matrix["limits"]["peak_rss_bytes"]
    native = native_binary_provenance()
    trace = budget_trace_snapshot(reset=True)
    assert native["sha256"] == args.native_sha256 and trace["mode"] == "record" and trace["alloc_counting"]
    case = next(case for case in matrix["cases"] if case["id"] == ref["case"])
    emit(args.result, "bound", native=native, budget=args.internal_bytes, case=case["id"],
         outer_bytes=8*GiB, matrix_sha256=digest(matrix_path), reference_sha256=digest(args.reference),
         code_sha256=digest(Path(__file__)), source_attribution=os.getenv("METROFLOW_TRACE_SOURCE_ATTRIBUTION"),
         release_eligible=False)
    source = args.raw
    if args.internal_bytes != OLD_BUDGET:
        source = args.result.with_suffix(".rebound.bin")
        binding = rebind(args.raw, source, args.internal_bytes, ref["final_checkpoint_sha256"])
        emit(args.result, "rebound", **binding)
    elif digest(source) != ref["final_checkpoint_sha256"]:
        raise ValueError("control raw digest mismatch")
    driver = build_driver(case, matrix, args.internal_bytes)
    if args.internal_bytes != OLD_BUDGET:
        assert driver.runtime.identity == binding["new_native_identity"]
    else:
        assert driver.identity == ref["current_driver_identity"]
    state = driver.load(source)
    restored = driver.report(state)["execution"]
    compare_physics(restored, ref["final_execution_report"])
    assert state.time_s == ref["completed_time_s"]
    emit(args.result, "restored", time_s=state.time_s, matched_keys=PHYSICAL_KEYS,
         driver_identity=driver.identity, runtime_identity=driver.runtime.identity,
         construction_byte_budget=restored["construction"]["byte_budget"],
         ledger=restored["ledger"], restore_wall_s=time.monotonic()-started)
    if args.internal_bytes != OLD_BUDGET:
        source.unlink()  # unique test header and verified-identical physical payload
    for _ in range(args.steps):
        target = state.time_s + 10.
        t0 = time.monotonic()
        budget_trace_snapshot(reset=True)
        emit(args.result, "attempt", target=target)
        try:
            state = driver.advance(state, target)
        except Exception as error:
            emit(args.result, "rejected", error_type=type(error).__name__, message=str(error),
                 target=target, wall_s=time.monotonic()-t0, trace=budget_trace_snapshot(reset=False))
            return 3 if "budget" in (str(error)+type(error).__name__).lower() or isinstance(error, MemoryError) else 4
        report = driver.report(state)
        problem = _ledger_error(report, target, population=100000)
        if problem:
            raise ValueError(problem)
        values = {k:report["execution"][k] for k in PHYSICAL_KEYS}
        emit(args.result, "validated", time_s=state.time_s, wall_s=time.monotonic()-t0,
             peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
             physical=values, trace=budget_trace_snapshot(reset=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
