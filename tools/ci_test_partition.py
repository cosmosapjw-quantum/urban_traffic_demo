from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from collections.abc import Callable
from pathlib import Path


ShardPredicate = Callable[[str], bool]

SHARD_RULES: tuple[tuple[str, ShardPredicate], ...] = (
    (
        "baseline-a-g-s-z",
        lambda name: not name.startswith("test_scalable_")
        and (
            fnmatch.fnmatchcase(name, "test_[a-g]*.py")
            or fnmatch.fnmatchcase(name, "test_[s-z]*.py")
        ),
    ),
    ("baseline-h-r", lambda name: fnmatch.fnmatchcase(name, "test_[h-r]*.py")),
    ("scalable-authority", lambda name: name == "test_scalable_authority.py"),
    (
        "scalable-blocks-config",
        lambda name: fnmatch.fnmatchcase(name, "test_scalable_[bc]*.py"),
    ),
    (
        "scalable-topology-runtime",
        lambda name: name.startswith("test_scalable_")
        and name != "test_scalable_authority.py"
        and not fnmatch.fnmatchcase(name, "test_scalable_[bc]*.py"),
    ),
)
SHARD_NAMES = tuple(name for name, _predicate in SHARD_RULES)


class PartitionError(ValueError):
    pass


def _repository_test_files(root: Path) -> tuple[Path, ...]:
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        raise PartitionError(f"tests directory not found: {tests_dir}")
    candidates = set(tests_dir.rglob("test_*.py"))
    candidates.update(tests_dir.rglob("*_test.py"))
    return tuple(sorted(path for path in candidates if path.is_file()))


def _partition(root: Path) -> dict[str, tuple[str, ...]]:
    selected: dict[str, list[str]] = {name: [] for name in SHARD_NAMES}
    unassigned: list[str] = []
    duplicated: list[str] = []

    for path in _repository_test_files(root):
        relative = path.relative_to(root).as_posix()
        memberships = [name for name, predicate in SHARD_RULES if predicate(path.name)]
        if not memberships:
            unassigned.append(relative)
        elif len(memberships) > 1:
            duplicated.append(f"{relative} ({', '.join(memberships)})")
        else:
            selected[memberships[0]].append(relative)

    if unassigned:
        raise PartitionError(f"unassigned test files: {', '.join(unassigned)}")
    if duplicated:
        raise PartitionError(f"multiply assigned test files: {', '.join(duplicated)}")

    empty = [name for name in SHARD_NAMES if not selected[name]]
    if empty:
        raise PartitionError(f"empty shards: {', '.join(empty)}")

    return {name: tuple(paths) for name, paths in selected.items()}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify and select the fail-closed GitHub Actions pytest partition."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root containing tests/ (default: inferred from this script)",
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--verify", action="store_true", help="verify and summarize all shards")
    action.add_argument("--matrix", action="store_true", help="emit the verified CI matrix as JSON")
    action.add_argument("--shard", choices=SHARD_NAMES, help="emit files for one verified shard")
    parser.add_argument(
        "--format",
        choices=("lines", "nul"),
        default="lines",
        help="selected-path output format for --shard (default: lines)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        partition = _partition(args.root.resolve())
    except PartitionError as error:
        print(f"ci test partition invalid: {error}", file=sys.stderr)
        return 2

    if args.verify:
        for name in SHARD_NAMES:
            print(f"{name}: {len(partition[name])}")
        total = sum(len(paths) for paths in partition.values())
        print(f"verified: {total} files across {len(SHARD_NAMES)} non-empty disjoint shards")
        return 0

    if args.matrix:
        matrix = {
            "include": [
                {"shard": name, "lint": name == "baseline-a-g-s-z"}
                for name in SHARD_NAMES
            ]
        }
        print(json.dumps(matrix, separators=(",", ":")))
        return 0

    paths = partition[args.shard]
    if args.format == "nul":
        sys.stdout.buffer.write(b"".join(path.encode() + b"\0" for path in paths))
    else:
        for path in paths:
            print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
