"""D11 presentation must preserve native no-candidate status without inferring physics."""
import hashlib
import json
from pathlib import Path

import pytest

from metroflow.ui.akm_receipts import read_akm_decision

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "artifacts/akm_d11_decision_20261128/S06_decision.json"


def test_native_d11_decision():
    raw = PATH.read_bytes()
    data = json.loads(raw)
    view = read_akm_decision(PATH, expected_sha256=hashlib.sha256(raw).hexdigest())
    assert view.status == "NO_CANDIDATE_RESEARCH_DECISION"
    assert view.model == data["model_identity"]
    assert view.payload == data
    assert not hasattr(view, "time_s")


def test_d11_reject_wrong_schema_status_and_digest(tmp_path):
    with pytest.raises(ValueError, match="digest"):
        read_akm_decision(PATH, expected_sha256="0" * 64)
    p = tmp_path / "decision.json"
    data = json.loads(PATH.read_text())
    for key, value in [("schema", "other"), ("status", "ACCEPTED"), ("candidate_selected", "B")]:
        p.write_text(json.dumps(dict(data, **{key: value})))
        with pytest.raises(ValueError):
            read_akm_decision(p)
