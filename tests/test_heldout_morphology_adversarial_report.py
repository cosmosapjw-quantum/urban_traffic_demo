"""Behavior contract for the external morphology adversarial-audit package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


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
REQUIRED_FAILURE_IDS = {f"MF-{index:03d}" for index in range(1, 37)}
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
    )
    assert all(phrase in report for phrase in required_phrases)
    assert "VALIDATED" in ledger
    assert "NEGATIVE_RESULT" in ledger
    assert "FORBIDDEN" in ledger


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
