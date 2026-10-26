"""Rendering observation only; no visual score is promoted to physics validation."""

import importlib.util
from pathlib import Path
import pytest


def test_direction_arrows_follow_the_actual_ramp_polyline(tmp_path, monkeypatch):
    pytest.importorskip("matplotlib")
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib.axes import Axes
    from metroflow.restored_city import generate

    path = Path(__file__).resolve().parents[1] / "tools/render_restored_city.py"
    spec = importlib.util.spec_from_file_location("restored_render_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    calls = []
    original = Axes.annotate

    def observe(self, *args, **kwargs):
        calls.append((kwargs["xytext"], kwargs["xy"]))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Axes, "annotate", observe)
    city = generate("organic")
    ramps = [s for s in city.sections if s.facility == "ramp"]
    mod.draw(city, tmp_path / "actual_map.png")
    assert len(calls) == len(ramps)
    for (start, end), ramp in zip(calls, ramps):
        points = [p[:2] for p in ramp.points]
        assert start in points and end in points, "Arrow lies off the authoritative curved road"
        assert points.index(start) < points.index(end)
