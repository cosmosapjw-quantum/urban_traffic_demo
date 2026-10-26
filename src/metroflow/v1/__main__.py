"""Installed V1 capability and physical-city validation entry point."""

import argparse
import json
from pathlib import Path
import platform
import sys

from . import __all__
from .city import CityContractError, load_city, iter_validation_matrix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("capabilities")
    city = commands.add_parser("validate-city")
    source = city.add_mutually_exclusive_group(required=True)
    source.add_argument("--matrix", action="store_true", help="six 8km cities x seeds 7/17/41")
    source.add_argument("--input", type=Path, help="atlas or V1 city JSON")
    city.add_argument("--out", type=Path, help="also save the JSON validation report")
    access = commands.add_parser("access-audit")
    access.add_argument("--matrix", action="store_true", required=True)
    access.add_argument("--out", type=Path)
    demand = commands.add_parser("demand-audit")
    demand.add_argument("--population", type=int, default=100000)
    demand.add_argument("--day", choices=("weekday", "weekend"), default="weekday")
    demand.add_argument("--out", type=Path)
    physics = commands.add_parser("physics-oracles")
    physics.add_argument("--suite", choices=("kinetic",), required=True)
    physics.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.command == "capabilities":
        print(
            json.dumps(
                {"api": "metroflow.v1", "exports": __all__, "full_day_runner": "NOT_IMPLEMENTED"},
                sort_keys=True,
            )
        )
        return 0
    try:
        if args.command == "physics-oracles":
            from .kinetic_oracles import kinetic_oracles

            rows = kinetic_oracles()
        elif args.command == "demand-audit":
            from .demand_audit import audit_demand

            rows = [audit_demand(args.population, args.day)]
        elif args.command == "access-audit":
            from .access_audit import access_matrix

            rows = access_matrix()
        elif args.matrix:
            rows = []
            for row in iter_validation_matrix():
                rows.append(row)
                print(
                    f"{len(rows)}/18 {row['case']} seed={row['seed']} {row['status']}",
                    file=sys.stderr,
                    flush=True,
                )
                if args.out:
                    args.out.parent.mkdir(parents=True, exist_ok=True)
                    args.out.write_text(
                        json.dumps(
                            dict(status="IN_PROGRESS", expected_cases=18, cases=rows),
                            allow_nan=False,
                        )
                    )
        else:
            rows = [load_city(json.loads(args.input.read_text())).report()]
        result = dict(
            status="PASS" if all(r["status"] == "PASS" for r in rows) else "NOT_ACCEPTED",
            python=platform.python_version(),
            cases=rows,
        )
    except CityContractError as exc:
        result = dict(status=exc.status, reason=exc.reason, cases=[])
    except OSError as exc:
        result = dict(status="ENVIRONMENT_BLOCKER", reason=str(exc), cases=[])
    except ValueError as exc:
        result = dict(status="MODEL_ERROR", reason=str(exc), cases=[])
    payload = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.out.with_name(args.out.name + ".tmp")
        tmp.write_text(payload)
        tmp.replace(args.out)
    sys.stdout.write(payload)
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
