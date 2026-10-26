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
    physics.add_argument("--suite", choices=("kinetic", "junctions", "timing", "routing"), required=True)
    physics.add_argument("--out", type=Path)
    run = commands.add_parser("run")
    run.add_argument("--scenario", choices=("toy_day", "lagged_growth_control"), required=True)
    run.add_argument("--resume-check", action="store_true")
    run.add_argument("--checkpoint", type=Path)
    run.add_argument("--resume", type=Path)
    run.add_argument("--until", type=float, default=60.0)
    run.add_argument("--out", type=Path)
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
        if args.command == "run" and args.scenario == "lagged_growth_control":
            if args.resume or args.resume_check or args.checkpoint:
                raise ValueError("growth control does not expose toy traffic resume options")
            from .development import lagged_growth_control
            rows = lagged_growth_control()
        elif args.command == "run":
            from .runtime import toy_runtime
            from .checkpoint import save_checkpoint, load_checkpoint
            import tempfile
            model = toy_runtime()
            initial = load_checkpoint(args.resume, model) if args.resume else model.initial()
            with tempfile.TemporaryDirectory() as temp:
                checkpoint = args.checkpoint or Path(temp) / 'world.json'
                if args.resume_check:
                    middle = (initial.traffic.road.time_s + args.until) / 2
                    half = model.run(initial, middle, checkpoint)
                    save_checkpoint(checkpoint, model, half)
                    resumed = model.run(load_checkpoint(checkpoint, model), args.until, checkpoint)
                    continuous = model.advance(initial, args.until)
                    if resumed != continuous:
                        raise ValueError('resume state differs from uninterrupted execution')
                else:
                    resumed = model.run(initial, args.until, checkpoint)
            rows = [dict(case='toy_day', status='PASS', time_s=resumed.traffic.road.time_s,
                         completed_veh=resumed.traffic.road.completed,
                         phases=len(resumed.journal), resume_checked=args.resume_check,
                         scope='synthetic fixed demand/graph; not 24h city runner')]
        elif args.command == "physics-oracles":
            if args.suite == "kinetic":
                from .kinetic_oracles import kinetic_oracles

                rows = kinetic_oracles()
            elif args.suite == "junctions":
                from .junction_oracles import junction_oracles

                rows = junction_oracles()
            elif args.suite == "routing":
                from .routing_oracles import routing_oracles

                rows = routing_oracles()
            else:
                from .timing_oracles import timing_oracles

                rows = timing_oracles()
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
