from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_BUCKET_KEYS = ("style_id", "map_size_bucket", "metric_id")


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_envelope_corpus(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        doc = json.load(f)

    _expect("corpus_version" in doc, "missing corpus_version")
    _expect("required_keys" in doc, "missing required_keys")
    _expect("entries" in doc, "missing entries")

    required_keys = doc["required_keys"]
    entries = doc["entries"]

    _expect(isinstance(required_keys, list) and required_keys, "required_keys must be a non-empty list")
    _expect(isinstance(entries, list) and entries, "entries must be a non-empty list")

    for key in required_keys:
        for field in REQUIRED_BUCKET_KEYS:
            _expect(field in key, f"required key missing field: {field}")

    entry_key_set: set[tuple[str, str, str]] = set()
    for entry in entries:
        for field in REQUIRED_BUCKET_KEYS:
            _expect(field in entry, f"entry missing field: {field}")
        _expect("sample_count" in entry, "entry missing sample_count")
        _expect(int(entry["sample_count"]) > 0, "sample_count must be positive")

        for percentile in ("p10", "p50", "p90"):
            lo = f"{percentile}_min"
            hi = f"{percentile}_max"
            _expect(lo in entry and hi in entry, f"entry missing {percentile} bounds")
            _expect(float(entry[lo]) <= float(entry[hi]), f"invalid {percentile} bounds")

        entry_key_set.add((str(entry["style_id"]), str(entry["map_size_bucket"]), str(entry["metric_id"])))

    for key in required_keys:
        key_tuple = (str(key["style_id"]), str(key["map_size_bucket"]), str(key["metric_id"]))
        _expect(key_tuple in entry_key_set, f"required key not present in entries: {key_tuple}")

    return doc
