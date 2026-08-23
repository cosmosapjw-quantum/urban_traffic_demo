#!/usr/bin/env python3
"""Portable, read-only runner for the frozen held-out validator.

The frozen validator is retained byte-for-byte because its SHA-256 is part of
the original result.  This runner supplies checkout/package locations without
rewriting that scientific authority and treats a reproduced scientific FAIL as
a successful reproduction, not as a process failure.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType
from typing import Any


sys.dont_write_bytecode = True


SOURCE_COMMIT = "e1979df281ac25a24a82fdea725422310f7c6807"
SOURCE_TREE = "622dbe37790c5414141cd5d5531a2158aa56f7e5"
STYLE_IDS = (
    "grid_core",
    "ring_radial",
    "river_constrained",
    "polycentric_tod",
    "superblock_mixed",
    "organic",
)
HELDOUT_SEEDS = (503, 701, 907)


def _git(repository: Path, revision: str) -> str:
    return subprocess.run(
        ["git", "rev-parse", revision],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _require_source_identity(repository: Path) -> None:
    commit = _git(repository, "HEAD")
    tree = _git(repository, "HEAD^{tree}")
    if commit != SOURCE_COMMIT or tree != SOURCE_TREE:
        raise RuntimeError(
            "source checkout identity mismatch: "
            f"expected {SOURCE_COMMIT}/{SOURCE_TREE}, got {commit}/{tree}"
        )


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _load_frozen_validator(repository: Path, package_dir: Path) -> ModuleType:
    source_root = (repository / "src").resolve()
    validator_path = (
        package_dir / "evidence" / "heldout_morphology_validator.py"
    ).resolve()
    if not source_root.is_dir():
        raise FileNotFoundError(source_root)
    if not validator_path.is_file():
        raise FileNotFoundError(validator_path)

    # Preload the package from the explicit checkout.  The frozen script later
    # inserts its historical author path, but Python resolves children through
    # this already-loaded package's __path__.
    sys.path.insert(0, str(source_root))
    import metroflow  # noqa: PLC0415

    metroflow_path = Path(metroflow.__file__).resolve()
    if not _is_relative_to(metroflow_path, source_root):
        raise RuntimeError(f"metroflow imported outside requested checkout: {metroflow_path}")

    spec = importlib.util.spec_from_file_location(
        "metroflow_frozen_heldout_validator", validator_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load frozen held-out validator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    for name, loaded in sorted(sys.modules.items()):
        if not (name == "metroflow" or name.startswith("metroflow.")):
            continue
        origin = getattr(loaded, "__file__", None)
        if origin is None:
            continue
        resolved = Path(origin).resolve()
        if not _is_relative_to(resolved, source_root):
            raise RuntimeError(f"{name} imported outside requested checkout: {resolved}")

    maps_dir = (package_dir / "maps").resolve()
    evidence_dir = (package_dir / "evidence").resolve()
    module.REPOSITORY = repository.resolve()
    module.SOURCE_ROOT = source_root
    module.OUTPUT_DIR = maps_dir
    module.RESULTS_PATH = evidence_dir / "heldout_morphology_results.json"
    module.MANIFEST_PATH = evidence_dir / "sample_manifest.json"
    module.CONTACT_SHEET_PATH = maps_dir / "heldout_morphology_seed503_contact_sheet.png"
    return module


def _expected_keys() -> list[tuple[str, int]]:
    return [(style_id, seed) for style_id in STYLE_IDS for seed in HELDOUT_SEEDS]


def _check_result_reproduction(module: ModuleType) -> None:
    committed = module.RESULTS_PATH.read_bytes()
    rederived = module._json_bytes(module.build_validation_result())
    if committed != rederived:
        raise RuntimeError("held-out result is not byte-identical on rederivation")
    payload: dict[str, Any] = json.loads(committed)
    keys = [(case["style_id"], case["seed"]) for case in payload["cases"]]
    if len(keys) != len(set(keys)) or set(keys) != set(_expected_keys()):
        raise RuntimeError("held-out result key partition mismatch")
    expected_inventory = {
        "attempted": 18,
        "expected": 18,
        "scored": 18,
        "skipped": 0,
    }
    if payload["attempt_inventory"] != expected_inventory:
        raise RuntimeError("held-out result attempt inventory mismatch")
    calculated_verdict = "PASS" if all(case["passed"] for case in payload["cases"]) else "FAIL"
    if payload["verdict"] != calculated_verdict:
        raise RuntimeError("held-out scientific verdict is internally inconsistent")
    print(
        "validation reproduction passed: 18/18 bytes re-derived; "
        f"scientific verdict={payload['verdict']}; skipped=0",
        flush=True,
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--package-dir", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--protocol-check", action="store_true")
    mode.add_argument("--check-validation", action="store_true")
    mode.add_argument("--check-samples", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    repository = args.repository.resolve()
    package_dir = args.package_dir.resolve()
    module = _load_frozen_validator(repository, package_dir)
    protocol = module.protocol_payload()
    if tuple(protocol["style_ids"]) != STYLE_IDS:
        raise RuntimeError("protocol style inventory mismatch")
    if tuple(protocol["heldout_seeds"]) != HELDOUT_SEEDS:
        raise RuntimeError("protocol seed inventory mismatch")
    if protocol["attempt_count_expected"] != 18:
        raise RuntimeError("protocol attempt count mismatch")
    if args.protocol_check:
        print("protocol check passed: styles=6 seeds=3 attempts=18", flush=True)
        return 0

    _require_source_identity(repository)
    if args.check_validation:
        _check_result_reproduction(module)
        return 0
    return 0 if module.check_samples() else 1


if __name__ == "__main__":
    raise SystemExit(main())
