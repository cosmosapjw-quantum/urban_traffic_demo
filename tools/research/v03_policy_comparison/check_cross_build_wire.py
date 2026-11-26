"""Compare a wider-policy retained state with a recorded ordinary-policy wire digest."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


def compare(wide_checkpoint, control_events, comparison, time_s):
    rebind = json.loads(comparison.read_text())["identity_rebind"]
    rows = [json.loads(line) for line in control_events.read_text().splitlines()]
    control, = [r for r in rows if r["phase"] == "wire" and r["time_s"] == time_s]
    wide = rebind["new_native_identity"].encode()
    ordinary = rebind["old_native_identity"].encode()
    if len(wide) != len(ordinary):
        raise ValueError("this check requires equal-width binding strings")
    original_hash = hashlib.sha256()
    normalized_hash = hashlib.sha256()
    payload_hash = hashlib.sha256()
    with gzip.open(wide_checkpoint, "rb") as source:
        header = source.read(rebind["header_bytes"])
        if header.count(wide) != 2:
            raise ValueError("expected exactly two wide-policy bindings in the header")
        patched = header.replace(wide, ordinary)
        offsets = [i for i, (a,b) in enumerate(zip(header,patched)) if a != b]
        if offsets != rebind["differing_byte_offsets"]:
            raise ValueError("header differs beyond the documented policy fields")
        original_hash.update(header)
        normalized_hash.update(patched)
        size = len(header)
        for block in iter(lambda: source.read(4*1024**2), b""):
            original_hash.update(block)
            normalized_hash.update(block)
            payload_hash.update(block)
            size += len(block)
    result = dict(time_s=time_s, wire_bytes=size, differing_header_offsets=offsets,
                  experimental_raw_sha256=original_hash.hexdigest(), physical_suffix_sha256=payload_hash.hexdigest(),
                  normalized_sha256=normalized_hash.hexdigest(), control_raw_sha256=control["raw_sha256"],
                  exact_except_two_budget_bindings=(normalized_hash.hexdigest()==control["raw_sha256"]
                                                   and size == control["raw_bytes"]))
    if not result["exact_except_two_budget_bindings"]:
        raise ValueError(f"normalized state mismatch: {result}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("wide-checkpoint", "control-events", "comparison", "out"):
        parser.add_argument("--"+name, required=True, type=Path)
    parser.add_argument("--time-s", type=int, required=True)
    args = parser.parse_args()
    result = compare(args.wide_checkpoint, args.control_events, args.comparison, args.time_s)
    args.out.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result))
