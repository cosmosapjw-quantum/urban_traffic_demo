"""Run the fixed realistic synthetic city plausibility audit."""

from __future__ import annotations

import argparse
import json

from metroflow.city.plausibility_audit import (
    REALISTIC_CITY_AUDIT_SEEDS,
    REALISTIC_CITY_AUDIT_STYLES,
    write_realistic_city_plausibility_artifacts,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-prefix", required=True)
    parser.add_argument(
        "--seeds",
        default=",".join(str(value) for value in REALISTIC_CITY_AUDIT_SEEDS),
    )
    parser.add_argument(
        "--styles",
        default=",".join(REALISTIC_CITY_AUDIT_STYLES),
    )
    args = parser.parse_args(argv)
    seeds = tuple(int(value.strip()) for value in args.seeds.split(",") if value.strip())
    styles = tuple(value.strip() for value in args.styles.split(",") if value.strip())
    paths = write_realistic_city_plausibility_artifacts(
        args.artifact_prefix,
        style_ids=styles,
        seeds=seeds,
    )
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "paths": {key: str(value) for key, value in paths.items()},
                "overall_pass": payload["overall_pass"],
                "map_count": payload["map_count"],
                "report_fingerprint": payload["fingerprint"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
