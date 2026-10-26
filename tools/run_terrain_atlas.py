"""Deterministic city-scale synthetic map research; stdlib generator."""

from pathlib import Path
import argparse
import json
import sys
import time
import hashlib
import platform
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from metroflow.terrain_city.network import generate
from metroflow.terrain_city.audit import geometry_audit

CASES = {
    "planned_plain": ("planned", "flat"),
    "polycentric_river": ("polycentric", "river"),
    "radial_plain": ("radial", "flat"),
    "coastal_port": ("polycentric", "coast"),
    "valley_city": ("corridor", "valley"),
    "lake_city": ("polycentric", "lake"),
}


def main(case="polycentric_river", resolution=42, seed=17, size=8000.0, stage="initial", out=None):
    out = Path(out or f"artifacts/terrain_atlas_20261025/{stage}")
    out.mkdir(parents=True, exist_ok=True)
    t = time.perf_counter()
    style, terrain = CASES[case]
    atlas = generate(style, terrain, size, resolution, seed)
    gen = time.perf_counter() - t
    audit = geometry_audit(atlas)
    payload = asdict(atlas)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    (out / f"{case}.json").write_text(json.dumps(payload, allow_nan=False))
    receipt = atlas.summary | dict(
        case=case,
        stage=stage,
        python=platform.python_version(),
        generation_s=gen,
        total_s=time.perf_counter() - t,
        content_sha256=digest,
        audit=audit,
    )
    (out / f"{case}_receipt.json").write_text(json.dumps(receipt, indent=2, allow_nan=False))
    print(
        json.dumps(
            {
                k: v
                for k, v in receipt.items()
                if k not in ("audit", "land_use_counts", "hierarchy_length_km")
            },
            indent=2,
        )
    )
    if audit["illegal_projected_contacts"]:
        print("CONTACTS", audit["illegal_projected_contacts"][:8])
    return receipt


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--case", choices=CASES, default="polycentric_river")
    p.add_argument("--resolution", type=int, default=42)
    p.add_argument("--size", type=float, default=8000.0)
    p.add_argument("--seed", type=int, default=17)
    p.add_argument("--stage", default="initial")
    p.add_argument("--out")
    a = p.parse_args()
    main(a.case, a.resolution, a.seed, a.size, a.stage, a.out)
