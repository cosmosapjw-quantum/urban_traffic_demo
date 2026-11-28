"""The Python presentation boundary reads Rust observations, never simulates."""
import hashlib
import json
from pathlib import Path

import pytest

from metroflow.ui.akm_receipts import read_akm_receipt

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts/akm_d05_final_20261128"


def test_native_receipt_retains_status_identity_and_reserved_carrier():
    path = ART / "S07_entry31.json"
    raw = path.read_bytes()
    view = read_akm_receipt(path, expected_sha256=hashlib.sha256(raw).hexdigest())
    original = json.loads(raw)
    assert view.schema == original["schema"]
    assert view.status == original["status"]
    assert view.model == original["model_identity"]
    assert view.time_s == 31
    assert view.payload["interface"] == original["interface"]
    assert view.payload["ledger"] == original["ledger"]
    assert view.scope == original["scope"]


def test_archive_receipt_keeps_observation_sequence_and_scope():
    path = ART / "S06_B_mesh300.json"
    view = read_akm_receipt(path)
    original = json.loads(path.read_text())
    assert view.time_s == 28800
    assert view.status == "OBSERVED_RESEARCH"
    assert view.payload["snapshots"] == original["result"]["snapshots"]
    assert view.payload["observation_times_s"] == original["observation_times_s"]
    assert view.scope == original["scope"]
    assert view.payload["network_sha256"] == original["network_sha256"]


def test_frontend_fails_closed_on_hash_schema_and_nonfinite(tmp_path):
    path = ART / "S04_interface_one.json"
    with pytest.raises(ValueError, match="digest"):
        read_akm_receipt(path, expected_sha256="0" * 64)
    q = tmp_path / "wrong.json"
    q.write_text('{"schema":"unknown"}')
    with pytest.raises(ValueError, match="schema"):
        read_akm_receipt(q)
    q.write_text('{"schema":"metroflow_akm_native_owners_v1","time_s":NaN}')
    with pytest.raises(ValueError, match="nonfinite"):
        read_akm_receipt(q)
