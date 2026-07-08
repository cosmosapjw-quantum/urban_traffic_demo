from __future__ import annotations


def build_terrain_field(*, width: int, height: int, seed: int) -> dict[str, object]:
    # Minimal deterministic terrain placeholder used by generator_v2 scaffolding.
    return {
        "width": int(width),
        "height": int(height),
        "seed": int(seed),
        "water_mask": [[False for _ in range(width)] for _ in range(height)],
    }
