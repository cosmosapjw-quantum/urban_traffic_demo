"""Behavior contract for the external morphology adversarial-audit package."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "artifacts" / "heldout_morphology_adversarial_audit_20260823"
PDF_COPY = (
    ROOT
    / "output"
    / "pdf"
    / "metroflow-heldout-morphology-adversarial-audit-20260823.pdf"
)
STYLE_IDS = {
    "grid_core",
    "ring_radial",
    "river_constrained",
    "polycentric_tod",
    "superblock_mixed",
    "organic",
}
REQUIRED_FAILURE_IDS = {f"MF-{index:03d}" for index in range(1, 44)}
REQUIRED_ROOT_FILES = {
    "AUDITOR_README.md",
    "CLAIM_EVIDENCE_LEDGER.md",
    "EVIDENCE_MANIFEST.json",
    "FAILURE_INVENTORY.json",
    "FAILURE_INVENTORY.md",
    "INDEPENDENT_REVIEW.md",
    "REPORT.md",
    "metroflow-heldout-morphology-adversarial-audit-20260823.pdf",
}
REQUIRED_EVIDENCE_FILES = {
    "harness_receipt.json",
    "heldout_morphology_results.json",
    "heldout_morphology_reproducer.py",
    "heldout_morphology_validator.py",
    "pr17_remote_receipt.json",
    "sample_manifest.json",
    "source_receipt.json",
}


def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_builder() -> object:
    path = ROOT / "tools" / "build_heldout_morphology_adversarial_report.py"
    spec = importlib.util.spec_from_file_location("heldout_report_builder", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _copy_package(tmp_path: Path) -> tuple[object, Path]:
    package = tmp_path / "package"
    shutil.copytree(PACKAGE, package)
    builder = _load_builder()
    builder.PACKAGE = package
    builder.EVIDENCE = package / "evidence"
    builder.MAPS = package / "maps"
    builder.PDF_COPY = tmp_path / "report-copy.pdf"
    shutil.copyfile(package / builder.PDF_NAME, builder.PDF_COPY)
    return builder, package


def _rebind_manifest(package: Path) -> None:
    manifest_path = package / "EVIDENCE_MANIFEST.json"
    manifest = _load_json(manifest_path)
    manifest["files"] = [
        {
            "path": path.relative_to(package).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in sorted(package.rglob("*"))
        if path.is_file() and path.name != manifest_path.name
    ]
    _write_json(manifest_path, manifest)


def _rebind_result_receipt(package: Path) -> None:
    receipt_path = package / "evidence" / "source_receipt.json"
    receipt = _load_json(receipt_path)
    receipt["heldout_evidence"]["results_sha256"] = _sha256(
        package / "evidence" / "heldout_morphology_results.json"
    )
    _write_json(receipt_path, receipt)


def test_external_audit_package_has_exact_required_surface() -> None:
    assert PACKAGE.is_dir()
    assert {path.name for path in PACKAGE.iterdir() if path.is_file()} == (
        REQUIRED_ROOT_FILES
    )
    evidence_dir = PACKAGE / "evidence"
    maps_dir = PACKAGE / "maps"
    assert {path.name for path in evidence_dir.iterdir() if path.is_file()} == (
        REQUIRED_EVIDENCE_FILES
    )
    expected_maps = {"heldout_morphology_seed503_contact_sheet.png"}
    for style_id in STYLE_IDS:
        expected_maps.add(f"map_{style_id}_s503.png")
        expected_maps.add(f"map_{style_id}_s503.svg")
    assert {path.name for path in maps_dir.iterdir() if path.is_file()} == expected_maps


def test_failure_inventory_is_complete_unique_and_fail_closed() -> None:
    payload = _load_json(PACKAGE / "FAILURE_INVENTORY.json")
    assert payload["schema_version"] == "metroflow_morphology_failure_inventory_v1"
    records = payload["failures"]
    assert isinstance(records, list)
    assert {record["id"] for record in records} == REQUIRED_FAILURE_IDS
    assert len(records) == len(REQUIRED_FAILURE_IDS)
    assert all(
        set(record)
        == {
            "claim_effect",
            "current_state",
            "domain",
            "evidence",
            "first_observed",
            "id",
            "impact",
            "original_severity",
            "remaining_gate",
            "resolution",
            "title",
        }
        for record in records
    )
    allowed_states = {
        "CLOSED",
        "PARTIALLY_CLOSED",
        "OPEN",
        "NEGATIVE_RESULT",
        "NOT_EVALUATED",
        "CONTESTED",
    }
    assert all(record["current_state"] in allowed_states for record in records)
    assert all(record["evidence"] and record["impact"] for record in records)
    assert any(record["current_state"] == "OPEN" for record in records)
    assert any(record["current_state"] == "NEGATIVE_RESULT" for record in records)


def test_report_preserves_exact_result_and_claim_ceiling() -> None:
    results = _load_json(PACKAGE / "evidence" / "heldout_morphology_results.json")
    assert results["verdict"] == "FAIL"
    assert results["attempt_inventory"] == {
        "attempted": 18,
        "expected": 18,
        "scored": 18,
        "skipped": 0,
    }
    assert sum(case["passed"] for case in results["cases"]) == 15
    assert {
        (case["style_id"], case["seed"])
        for case in results["cases"]
        if not case["passed"]
    } == {("grid_core", 503), ("grid_core", 701), ("grid_core", 907)}

    report = (PACKAGE / "REPORT.md").read_text(encoding="utf-8")
    ledger = (PACKAGE / "CLAIM_EVIDENCE_LEDGER.md").read_text(encoding="utf-8")
    for style_id in STYLE_IDS:
        assert f"maps/map_{style_id}_s503.png" in report
    required_phrases = (
        "15/18",
        "seed-held-out structural morphology",
        "NOT fresh-OSM empirical validation",
        "runtime-default promotion remains blocked",
        "traffic-functional validation was not completed",
        "MF-001",
        "MF-036",
        "MF-043",
    )
    assert all(phrase in report for phrase in required_phrases)
    assert "VALIDATED" in ledger
    assert "NEGATIVE_RESULT" in ledger
    assert "FORBIDDEN" in ledger


def test_package_states_single_user_non_security_scope() -> None:
    report = (PACKAGE / "REPORT.md").read_text(encoding="utf-8")
    readme = (PACKAGE / "AUDITOR_README.md").read_text(encoding="utf-8")
    required = (
        "single-developer personal research code",
        "no security or tamper-resistance claim",
        "skeptical scientific and code review",
    )
    assert all(phrase in report for phrase in required)
    assert all(phrase in readme for phrase in required)


def test_manifest_binds_every_file_and_both_pdf_copies() -> None:
    manifest = _load_json(PACKAGE / "EVIDENCE_MANIFEST.json")
    assert manifest["schema_version"] == "metroflow_morphology_adversarial_audit_v1"
    assert manifest["source"]["commit"] == (
        "e1979df281ac25a24a82fdea725422310f7c6807"
    )
    assert manifest["source"]["tree"] == (
        "622dbe37790c5414141cd5d5531a2158aa56f7e5"
    )
    assert manifest["heldout_result"]["scientific_fingerprint"] == (
        "84b2f3657b21c9cedd9fe7723b4edf99ac3f7514cf7128aff6c994ff9da253f1"
    )
    records = manifest["files"]
    assert len(records) == len({record["path"] for record in records})
    expected_paths = {
        path.relative_to(PACKAGE).as_posix()
        for path in PACKAGE.rglob("*")
        if path.is_file() and path.name != "EVIDENCE_MANIFEST.json"
    }
    assert {record["path"] for record in records} == expected_paths
    for record in records:
        path = PACKAGE / record["path"]
        assert record["bytes"] == path.stat().st_size
        assert record["sha256"] == _sha256(path)

    package_pdf = (
        PACKAGE / "metroflow-heldout-morphology-adversarial-audit-20260823.pdf"
    )
    assert package_pdf.read_bytes().startswith(b"%PDF-")
    assert PDF_COPY.is_file()
    assert PDF_COPY.read_bytes() == package_pdf.read_bytes()


def test_checker_rejects_duplicate_or_incomplete_case_matrix(tmp_path: Path) -> None:
    builder, package = _copy_package(tmp_path)
    results_path = package / "evidence" / "heldout_morphology_results.json"
    results = _load_json(results_path)
    replacement = next(
        case
        for case in results["cases"]
        if case["style_id"] == "organic" and case["seed"] == 701
    )
    index = next(
        index
        for index, case in enumerate(results["cases"])
        if case["style_id"] == "organic" and case["seed"] == 907
    )
    results["cases"][index] = replacement
    _write_json(results_path, results)
    _rebind_result_receipt(package)
    _rebind_manifest(package)

    with pytest.raises(ValueError, match="result key"):
        builder.check_package(allow_review_missing=True)


def test_scientific_fingerprint_is_recomputed_from_payload() -> None:
    builder = _load_builder()
    results = _load_json(PACKAGE / "evidence" / "heldout_morphology_results.json")
    assert builder._scientific_fingerprint(results) == results["scientific_fingerprint"]
    results["cases"][0]["witnesses"]["axis_aligned_core_count"] += 1
    assert builder._scientific_fingerprint(results) != results["scientific_fingerprint"]


def test_checker_rejects_rebound_non_scientific_result_bytes(tmp_path: Path) -> None:
    builder, package = _copy_package(tmp_path)
    results_path = package / "evidence" / "heldout_morphology_results.json"
    results = _load_json(results_path)
    results["environment"]["python"] = "0.0-rebound"
    _write_json(results_path, results)
    _rebind_result_receipt(package)
    _rebind_manifest(package)

    with pytest.raises(ValueError, match="expected result digest"):
        builder.check_package(allow_review_missing=True)


def test_checker_rejects_nested_extra_and_unfinished_prose(tmp_path: Path) -> None:
    builder, package = _copy_package(tmp_path)
    nested = package / "maps" / "unreviewed" / "extra.txt"
    nested.parent.mkdir()
    nested.write_text("extra", encoding="utf-8")
    _rebind_manifest(package)
    with pytest.raises(ValueError, match="recursive package membership"):
        builder.check_package(allow_review_missing=True)

    nested.unlink()
    nested.parent.rmdir()
    report = package / "REPORT.md"
    report.write_text(report.read_text(encoding="utf-8") + "\nTODO\n", encoding="utf-8")
    _rebind_manifest(package)
    with pytest.raises(ValueError, match="unfinished marker"):
        builder.check_package(allow_review_missing=True)


def test_checker_rejects_rebound_truncated_png(tmp_path: Path) -> None:
    builder, package = _copy_package(tmp_path)
    png_path = package / "maps" / "map_grid_core_s503.png"
    png_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + struct.pack(">II", 1400, 1050))
    sample_path = package / "evidence" / "sample_manifest.json"
    sample = _load_json(sample_path)
    entry = next(item for item in sample["entries"] if item["style_id"] == "grid_core")
    entry["png_sha256"] = _sha256(png_path)
    _write_json(sample_path, sample)
    source_path = package / "evidence" / "source_receipt.json"
    source = _load_json(source_path)
    source["heldout_evidence"]["sample_manifest_sha256"] = _sha256(sample_path)
    _write_json(source_path, source)
    _rebind_manifest(package)

    with pytest.raises(ValueError, match="PNG"):
        builder.check_package(allow_review_missing=True)


def test_review_gate_rejects_substrings_and_contradictory_verdict(tmp_path: Path) -> None:
    builder, package = _copy_package(tmp_path)
    (package / "INDEPENDENT_REVIEW.md").write_text(
        "# Contradictory review\n\nP0: 01\nP1: 00\nP2: 0\n"
        "VERDICT: FAIL\nQuoted requirement: VERDICT: PASS\n",
        encoding="utf-8",
    )
    results = _load_json(package / "evidence" / "heldout_morphology_results.json")
    records = _load_json(package / "FAILURE_INVENTORY.json")["failures"]
    (package / "REPORT.md").write_text(
        builder._render_report(results, records, True).rstrip() + "\n",
        encoding="utf-8",
    )
    (package / "AUDITOR_README.md").write_text(
        builder._render_auditor_readme(True).rstrip() + "\n",
        encoding="utf-8",
    )
    _rebind_manifest(package)

    with pytest.raises(ValueError, match="review gate"):
        builder.check_package()


def test_portable_reproducer_has_explicit_source_and_package_paths() -> None:
    reproducer = PACKAGE / "evidence" / "heldout_morphology_reproducer.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(reproducer),
            "--repository",
            str(ROOT),
            "--package-dir",
            str(PACKAGE),
            "--protocol-check",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "styles=6 seeds=3 attempts=18" in completed.stdout
