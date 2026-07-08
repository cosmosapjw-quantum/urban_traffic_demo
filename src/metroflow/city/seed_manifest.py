from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_seed_manifest(doc: dict[str, Any]) -> dict[str, Any]:
    for key in ("manifest_id", "manifest_version", "scenario_id", "seed_count", "seeds"):
        _expect(key in doc, f"missing seed manifest key: {key}")

    seeds = doc["seeds"]
    _expect(isinstance(seeds, list), "seeds must be a list")
    _expect(all(isinstance(s, int) for s in seeds), "all seeds must be integers")

    seed_count = int(doc["seed_count"])
    _expect(seed_count == len(seeds), "seed_count must match number of seeds")
    _expect(len(set(seeds)) == len(seeds), "seeds must be unique")
    return doc


def load_seed_manifest(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        doc = json.load(f)
    return validate_seed_manifest(doc)
