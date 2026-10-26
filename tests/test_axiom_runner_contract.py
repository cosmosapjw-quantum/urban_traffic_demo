"""Reporting must describe the supplied city and the actually simulated clock."""

import importlib.util
import json
from dataclasses import asdict
from pathlib import Path
import pytest
from metroflow.active_suffix import Road, Demand


def runner():
    path = Path(__file__).resolve().parents[1] / "tools/run_axiom_traffic.py"
    spec = importlib.util.spec_from_file_location("axiom_report_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def city_input(tmp_path):
    data = {
        "compiled": {"roads": [asdict(Road("od", "O", "D", 100.0, 10.0, 1.0, 30.0))], "turns": []},
        "map": {
            "nodes": [{"id": "O", "xyz": [0.0, 0.0, 0.0]}, {"id": "D", "xyz": [100.0, 0.0, 0.0]}]
        },
        "plan": {
            "demands": [asdict(Demand("O", "D", 0.0, 8.0, 0.1))],
            "ledger": [["resident_stock", 3000.0]],
        },
    }
    path = tmp_path / "input.json"
    path.write_text(json.dumps(data))
    return path


def test_non_aligned_horizon_is_rejected_not_reported_as_executed(tmp_path):
    # dt=2: round(3/2) otherwise runs 4 seconds and labels it 3 seconds.
    with pytest.raises(ValueError, match="horizon"):
        runner().city(tmp_path, city_input(tmp_path), horizon=3.0)


def test_resident_stock_comes_from_input_not_a_fixed_100k_label(tmp_path):
    result = runner().city(tmp_path, city_input(tmp_path), horizon=4.0)
    assert result["resident_stock"] == 3000.0
    assert all(case["horizon_s"] == 4.0 for case in result["cases"])
