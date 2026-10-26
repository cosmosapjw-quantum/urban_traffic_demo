"""Installed, dependency-free V1 capability entry point (not a full-day runner)."""

import argparse
import json

from . import __all__


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("capabilities",))
    parser.parse_args()
    print(
        json.dumps(
            {"api": "metroflow.v1", "exports": __all__, "full_day_runner": "NOT_IMPLEMENTED"},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
