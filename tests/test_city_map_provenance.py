from __future__ import annotations

import ast
import json
from pathlib import Path

import tomllib


ROOT = Path(__file__).resolve().parents[1]


def _all_string_values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, dict):
        return tuple(item for child in value.values() for item in _all_string_values(child))
    if isinstance(value, (list, tuple)):
        return tuple(item for child in value for item in _all_string_values(child))
    return ()


def test_city_map_source_boundary_forbids_external_runtime_dependency() -> None:
    boundary = (ROOT / "docs/map/CITY_MAP_SOURCE_PROVENANCE.md").read_text(
        encoding="utf-8"
    )
    policy = json.loads(
        (ROOT / "docs/map/city_map_source_policy.json").read_text(encoding="utf-8")
    )
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert _all_string_values(pyproject)

    assert policy["upstream"] == {
        "repository": "https://github.com/citiesskylines-csur/CSUR",
        "reviewed_commit": "a47270e0a20ff5bda23db3d7db34a993b36c9a69",
        "license": "GPL-3.0",
    }
    assert policy["reuse_policy"] == "concepts_only_no_source_copy"
    assert len(policy["permitted_concept_ids"]) == 5
    assert len(policy["excluded_source_surfaces"]) == 6
    assert "does not vendor, import, or copy source" in boundary
    assert "CSUR is not a city-scale centerline or topology generator" in boundary
    for permitted_concept in (
        "typed units with explicit widths",
        "start and end cross-sections",
        "base, lateral shift, lane",
        "lane-count deltas",
        "deterministic canonical identifier",
    ):
        assert permitted_concept in boundary
    for excluded_surface in (
        "`modeling/`",
        "`graphics/`",
        "`prefab/`",
        "`bin/`",
        "`builder/`",
        "Cities: Skylines segment-length",
    ):
        assert excluded_surface in boundary
    for token in policy["forbidden_dependency_tokens"]:
        for relative_path in policy["dependency_manifests"]:
            manifest_path = ROOT / relative_path
            assert manifest_path.is_file(), relative_path
            assert token not in manifest_path.read_text(encoding="utf-8").lower()


def test_runtime_sources_do_not_import_csur_packages() -> None:
    for path in (ROOT / "src/metroflow").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported_modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_modules.append(node.module)
        assert not any("csur" in name.lower() for name in imported_modules), path


def test_runtime_source_roots_have_no_unapproved_csur_tokens() -> None:
    policy = json.loads(
        (ROOT / "docs/map/city_map_source_policy.json").read_text(encoding="utf-8")
    )
    legacy_keys = tuple(policy["legacy_metadata"]["keys"])

    for relative_root in policy["runtime_source_roots"]:
        source_root = ROOT / relative_root
        assert source_root.is_dir(), relative_root
        for path in source_root.rglob("*"):
            if path.suffix not in {".py", ".rs"}:
                continue
            normalized = path.read_text(encoding="utf-8").lower()
            for legacy_key in legacy_keys:
                normalized = normalized.replace(legacy_key, "")
            assert "csur" not in normalized, path


def test_legacy_csur_metadata_cannot_gain_new_consumers() -> None:
    policy = json.loads(
        (ROOT / "docs/map/city_map_source_policy.json").read_text(encoding="utf-8")
    )
    legacy_keys = tuple(policy["legacy_metadata"]["keys"])
    source_files = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "src/metroflow").rglob("*.py")
        if any(key in path.read_text(encoding="utf-8") for key in legacy_keys)
    }

    assert policy["legacy_metadata"]["status"] == "removed_from_runtime"
    assert source_files == set(policy["legacy_metadata"]["allowed_source_files"])


def test_city_map_roadmap_preserves_link_level_runtime_authority() -> None:
    roadmap = (ROOT / "docs/harness/CITY_MAP_PR_LIST.md").read_text(encoding="utf-8")

    assert "RoadNetworkCSR" in roadmap
    assert "do not introduce lane-level microscopic state" in roadmap
    assert "At most three subagents may be active" in roadmap
    assert "Static PNG/HTML outputs are diagnostic artifacts" in roadmap


def test_legacy_docs_do_not_claim_csur_runtime_authority() -> None:
    authoritative_paths = tuple((ROOT / "docs").rglob("*.md")) + tuple(
        (ROOT / "specs/001-metroflow").rglob("*.md")
    )
    legacy_docs = "\n".join(path.read_text(encoding="utf-8") for path in authoritative_paths)

    assert "CSUR contributes" not in legacy_docs
    assert "CSUR lane grammar" not in legacy_docs
    assert "project-authored" in legacy_docs
    assert "아직 runtime에 구현되지 않았다" in legacy_docs
