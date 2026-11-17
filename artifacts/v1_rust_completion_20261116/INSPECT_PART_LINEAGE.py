"""Read-only, one-pass MFWHOLE1 checkpoint inspection with capped key sets.

This is a frontend diagnostic, not a simulator or a checkpoint rewriter.
Numerical values and serialized rows are never modified. When a key set hits
--max-keys, duplicate counts remain lower bounds and completeness is explicit.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import struct
import time


class Reader:
    def __init__(self, path):
        self.file = open(path, "rb", buffering=1024 * 1024)
        self.sha = hashlib.sha256()
        self.offset = 0

    def read(self, size):
        data = self.file.read(size)
        if len(data) != size:
            raise ValueError(f"truncated checkpoint at {self.offset}, need {size}")
        self.sha.update(data)
        self.offset += size
        return data

    def u64(self):
        return struct.unpack("<Q", self.read(8))[0]

    def f64(self):
        return struct.unpack("<d", self.read(8))[0]

    def skip(self, size):
        while size:
            take = min(size, 1024 * 1024)
            self.read(take)
            size -= take

    def string(self):
        size = self.u64()
        if size > 1024 * 1024:
            raise ValueError("unreasonable checkpoint binding length")
        return self.read(size).decode("utf-8")


class ExactSum:
    """Small floating expansion; finalized with Python's math.fsum."""
    def __init__(self):
        self.partials = []

    def add(self, value):
        keep = 0
        for previous in self.partials:
            if abs(value) < abs(previous):
                value, previous = previous, value
            high = value + previous
            low = previous - (high - value)
            if low:
                self.partials[keep] = low
                keep += 1
            value = high
        self.partials[keep:] = [value] if value else []

    def total(self):
        return math.fsum(self.partials)


class BoundedKeys:
    def __init__(self, cap):
        self.cap = cap
        self.keys = set()
        self.complete = True
        self.duplicates = 0

    def add(self, key):
        if key in self.keys:
            self.duplicates += 1
            return True
        if len(self.keys) < self.cap:
            self.keys.add(key)
        else:
            self.complete = False
        return False


MASS_EDGES = (1e-24, 1e-20, 1e-16, 1e-12, 1e-8, 1e-4, 1., 1e4, math.inf)


class Histogram:
    def __init__(self):
        self.counts = [0] * len(MASS_EDGES)
        self.mass = [ExactSum() for _ in MASS_EDGES]

    def add(self, mass):
        for index, edge in enumerate(MASS_EDGES):
            if mass < edge:
                self.counts[index] += 1
                self.mass[index].add(mass)
                break

    def report(self):
        return [{"lower_inclusive": 0. if i == 0 else MASS_EDGES[i - 1],
                 "upper_exclusive": None if math.isinf(edge) else edge,
                 "rows": self.counts[i], "mass_fsum": self.mass[i].total()}
                for i, edge in enumerate(MASS_EDGES)]


def inspect_packets(reader, cap, label, index, aggregate, histogram):
    packet_count = reader.u64()
    route_offsets = BoundedKeys(cap)
    cell_full_rows = BoundedKeys(cap)
    cell_target_rows = BoundedKeys(cap)
    result = {"kind": label, "cell_index": index, "packets": packet_count,
              "parts": 0, "uniform_interval_packets": 0,
              "uniform_interval_parts": 0, "mixed_interval_packets": 0,
              "none_interval_parts": 0, "point_interval_parts": 0,
              "positive_width_interval_parts": 0, "adjacent_equal_target_packets": 0,
              "exact_fullpart_duplicate_rows_lower_bound": 0,
              "exact_combine_key_duplicate_rows_lower_bound": 0,
              "packet_key_sets_complete": True,
              "packet_common_interval_saving_bytes_x86_64": 0}
    previous_target = None
    for _ in range(packet_count):
        target = reader.read(8)
        if target == previous_target:
            result["adjacent_equal_target_packets"] += 1
        previous_target = target
        count = reader.u64()
        result["parts"] += count
        full = BoundedKeys(cap)
        combine = BoundedKeys(cap)
        first_interval = None
        uniform = True
        for part_index in range(count):
            raw = reader.read(32)
            tag, offset, mass, birth = struct.unpack("<QQdd", raw)
            if not (math.isfinite(mass) and mass > 0 and math.isfinite(birth) and birth >= 0):
                raise ValueError("invalid native part mass/birth")
            flag = reader.u64()
            if flag == 1:
                interval_tail = reader.read(24)
                a, bflag, b = struct.unpack("<dQd", interval_tail)
                if bflag != 1 or not (math.isfinite(a) and math.isfinite(b) and 0 <= a <= b):
                    raise ValueError("invalid native part interval")
                interval = b"\1" + interval_tail[:8] + interval_tail[16:]
                result["point_interval_parts" if a == b else "positive_width_interval_parts"] += 1
            elif flag == 0:
                if reader.u64() != 0:
                    raise ValueError("unpaired native part interval")
                interval = b"\0"
                result["none_interval_parts"] += 1
            else:
                raise ValueError("invalid native interval flag")
            if part_index == 0:
                first_interval = interval
            elif interval != first_interval:
                uniform = False
            route_offsets.add(raw[:16])
            full.add(raw + interval)
            cell_full_rows.add(raw + interval)
            cell_target_rows.add(target + raw + interval)
            combine.add(raw[:16] + interval)
            histogram.add(mass)
        result["exact_fullpart_duplicate_rows_lower_bound"] += full.duplicates
        result["exact_combine_key_duplicate_rows_lower_bound"] += combine.duplicates
        result["packet_key_sets_complete"] &= full.complete and combine.complete
        if uniform:
            result["uniform_interval_packets"] += 1
            result["uniform_interval_parts"] += count
            result["packet_common_interval_saving_bytes_x86_64"] += max(0, 32 * count - 24)
        else:
            result["mixed_interval_packets"] += 1
    result["unique_route_offsets_lower_bound"] = len(route_offsets.keys)
    result["recurrent_route_offset_rows_lower_bound"] = route_offsets.duplicates
    result["cell_route_offset_keys_complete"] = route_offsets.complete
    result["exact_fullpart_duplicates_across_cell_packets_lower_bound"] = cell_full_rows.duplicates
    result["exact_target_fullpart_duplicates_across_cell_packets_lower_bound"] = cell_target_rows.duplicates
    result["cell_fullpart_key_sets_complete"] = cell_full_rows.complete and cell_target_rows.complete
    for key, value in result.items():
        if isinstance(value, bool):
            aggregate[key] = aggregate.get(key, True) and value
        elif isinstance(value, int) and key != "cell_index":
            aggregate[key] = aggregate.get(key, 0) + value
    return result


def inspect_stage(reader, cap, now):
    count = reader.u64()
    group = None
    group_size = 0
    group_keys = BoundedKeys(cap)
    distribution = Counter()
    histogram = Histogram()
    result = {"rows": count, "contiguous_leg_birth_groups": 0,
              "duplicate_full_rows_within_group_lower_bound": 0,
              "group_key_sets_complete": True, "ready_now": 0,
              "ready_in_future": 0}

    def finish_group():
        if group_size:
            distribution[group_size] += 1
            result["contiguous_leg_birth_groups"] += 1
            result["duplicate_full_rows_within_group_lower_bound"] += group_keys.duplicates
            result["group_key_sets_complete"] &= group_keys.complete

    for _ in range(count):
        raw = reader.read(32)
        leg, mass, born, delay = struct.unpack("<Qddd", raw)
        current = (leg, raw[16:24])
        if current != group:
            finish_group()
            group, group_size, group_keys = current, 0, BoundedKeys(cap)
        group_size += 1
        group_keys.add(raw)
        histogram.add(mass)
        result["ready_now" if born + delay <= now + 1e-10 else "ready_in_future"] += 1
    finish_group()
    result["rows_per_contiguous_leg_birth_group"] = sorted(distribution.items())
    result["mass_histogram"] = histogram.report()
    result["group_scope"] = "original contiguous rows sharing leg and bit-identical birth; not a globally coalesced or proven source-emission ID"
    return result


def inspect(path, max_keys):
    started = time.monotonic()
    reader = Reader(path)
    if reader.read(8) != b"MFWHOLE1":
        raise ValueError("expected MFWHOLE1 checkpoint")
    whole_identity = reader.string()
    road_identity = reader.string()
    now = reader.f64()
    count = reader.u64()
    cells, pending, largest = {}, {}, []
    histogram = Histogram()
    for index in range(count):
        reader.skip(8 * 8)
        row = inspect_packets(reader, max_keys, "cell", index, cells, histogram)
        largest.append(row)
        reader.skip(reader.u64() * 16)
    pending_count = reader.u64()
    if pending_count != count:
        raise ValueError("road cell/pending shape differs")
    for index in range(pending_count):
        row = inspect_packets(reader, max_keys, "pending", index, pending, histogram)
        if row["parts"]:
            largest.append(row)
    totals = [reader.f64() for _ in range(7)]
    reader.skip(reader.u64() * 5 * 8)
    # Service ledger, then the original event rows. These are skipped in place;
    # a large event log is never converted to Python tuples.
    for row_bytes in (40, 40, 8, 8, 8):
        reader.skip(reader.u64() * row_bytes)
    service_events = reader.u64()
    for _ in range(service_events):
        reader.skip(16)
        has_destination = reader.u64()
        if has_destination not in (0, 1):
            raise ValueError("invalid event destination flag")
        reader.skip(32 + 8 * has_destination)
    journey_time = reader.f64()
    if journey_time != now:
        raise ValueError("road/journey checkpoint clocks differ")
    stages = {name: inspect_stage(reader, max_keys, now)
              for name in ("entering", "egress", "internal")}
    for _ in range(2):
        reader.skip(reader.u64() * 8)
    histories = reader.u64()
    receipts = nonempty = 0
    for _ in range(histories):
        rows = reader.u64()
        receipts += rows
        nonempty += bool(rows)
        reader.skip(rows * 16)
    reader.skip(reader.u64() * 8)
    if reader.file.read(1):
        raise ValueError("unexpected trailing checkpoint bytes")
    reader.file.close()
    largest.sort(key=lambda row: row["parts"], reverse=True)
    all_parts = cells["parts"] + pending["parts"]
    return {"status": "MEASURED_READ_ONLY", "checkpoint": str(path),
            "checkpoint_sha256": reader.sha.hexdigest(), "checkpoint_bytes": reader.offset,
            "whole_identity": whole_identity, "road_identity": road_identity,
            "time_s": now, "cells": count, "road_cell_totals": cells,
            "road_pending_totals": pending, "largest_queues": largest[:20],
            "road_mass_histogram": histogram.report(), "road_source_released_mass": totals[0],
            "road_sink_mass": totals[1], "road_active_mass": totals[0] - totals[1],
            "service_last_events": service_events, "stages": stages,
            "receipts": receipts, "nonempty_histories": nonempty,
            "packed_finite_option_saving_bytes_x86_64": 16 * all_parts,
            "memory_scope": {"max_keys_per_set": max_keys,
                "simultaneously_live_capped_sets": 5,
                "largest_queue_records_retained": "only counters; per-packet and per-cell key sets are capped",
                "when_capped": "duplicate counts and unique-key counts are lower bounds; completeness flags become false"},
            "semantic_scope": "Repeated tag/offset across packets is NOT an equality or permission to merge; target, entry interval, FIFO position, mass and first moment remain distinct. No simulation or checkpoint mutation.",
            "wall_s": time.monotonic() - started}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-keys", type=int, default=100_000)
    args = parser.parse_args()
    if args.max_keys <= 0:
        parser.error("--max-keys must be positive")
    result = inspect(args.checkpoint, args.max_keys)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({key: result[key] for key in ("status", "time_s", "checkpoint_sha256", "wall_s")}))


if __name__ == "__main__":
    main()
