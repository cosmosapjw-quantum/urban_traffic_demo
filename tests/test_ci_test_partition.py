from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PARTITION_TOOL = REPOSITORY_ROOT / "tools" / "ci_test_partition.py"


def _write_test_files(root: Path, *names: str) -> None:
    tests_dir = root / "tests"
    tests_dir.mkdir()
    for name in names:
        (tests_dir / name).write_text("def test_placeholder():\n    pass\n", encoding="utf-8")


def _complete_partition(root: Path) -> None:
    _write_test_files(
        root,
        "test_alpha.py",
        "test_runtime.py",
        "test_scalable_authority.py",
        "test_scalable_blocks.py",
        "test_scalable_topology.py",
    )


def test_cli_verifies_complete_disjoint_nonempty_partition(tmp_path: Path) -> None:
    _complete_partition(tmp_path)

    result = subprocess.run(
        [sys.executable, str(PARTITION_TOOL), "--root", str(tmp_path), "--verify"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "baseline-a-g-s-z: 1",
        "baseline-h-r: 1",
        "scalable-authority: 1",
        "scalable-blocks-config: 1",
        "scalable-topology-runtime: 1",
        "verified: 5 files across 5 non-empty disjoint shards",
    ]


def test_cli_emits_selected_paths_as_repo_relative_nul_records(tmp_path: Path) -> None:
    _complete_partition(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(PARTITION_TOOL),
            "--root",
            str(tmp_path),
            "--shard",
            "scalable-topology-runtime",
            "--format",
            "nul",
        ],
        check=False,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout == b"tests/test_scalable_topology.py\0"


def test_cli_emits_complete_ci_matrix_from_verified_registry(tmp_path: Path) -> None:
    _complete_partition(tmp_path)

    result = subprocess.run(
        [sys.executable, str(PARTITION_TOOL), "--root", str(tmp_path), "--matrix"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "include": [
            {"shard": "baseline-a-g-s-z", "lint": True},
            {"shard": "baseline-h-r", "lint": False},
            {"shard": "scalable-authority", "lint": False},
            {"shard": "scalable-blocks-config", "lint": False},
            {"shard": "scalable-topology-runtime", "lint": False},
        ]
    }


def test_cli_rejects_unknown_shard_without_emitting_paths(tmp_path: Path) -> None:
    _complete_partition(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(PARTITION_TOOL),
            "--root",
            str(tmp_path),
            "--shard",
            "unknown-shard",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "invalid choice: 'unknown-shard'" in result.stderr


def test_cli_fails_closed_for_unassigned_test_file(tmp_path: Path) -> None:
    _complete_partition(tmp_path)
    (tmp_path / "tests" / "test_1numeric.py").write_text(
        "def test_placeholder():\n    pass\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(PARTITION_TOOL), "--root", str(tmp_path), "--verify"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "ci test partition invalid: unassigned test files: tests/test_1numeric.py\n"
    )


def test_cli_fails_closed_for_suffix_style_pytest_module(tmp_path: Path) -> None:
    _complete_partition(tmp_path)
    (tmp_path / "tests" / "legacy_test.py").write_text(
        "def test_placeholder():\n    pass\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(PARTITION_TOOL), "--root", str(tmp_path), "--verify"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "ci test partition invalid: unassigned test files: tests/legacy_test.py\n"
    )


def test_cli_fails_closed_when_any_shard_is_empty(tmp_path: Path) -> None:
    _write_test_files(tmp_path, "test_alpha.py")

    result = subprocess.run(
        [sys.executable, str(PARTITION_TOOL), "--root", str(tmp_path), "--verify"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "ci test partition invalid: empty shards: baseline-h-r, scalable-authority, "
        "scalable-blocks-config, scalable-topology-runtime\n"
    )
