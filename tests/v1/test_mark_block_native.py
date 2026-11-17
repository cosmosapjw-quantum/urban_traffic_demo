"""Opt-in `mark_block_scaled_v1` road representation (named numerical policy).

The row representation stays the default and bit-identical. The shared path is
compared with the rows path on physical observables only; float operation order
differs by design. Requires the rebuilt extension; import failure is not RED.
"""
import math

import pytest
from _metroflow_rust import NativeWholeEngine, V1Road

from test_native_engine import make_native, small_fixture

MB = "mark_block_scaled_v1"


def road(rep="rows", width=.25):
    return V1Road(
        "mark-block-py", 1.,
        [[.1, 20., 10., 1., 1000., 1.]] + [[100., 20., 10., 10., 1000., 1.] for _ in range(4)],
        [None] * 5, [([0, 1, 2, 3], 0), ([0, 1, 2, 4], 0), ([0, 1, 4], 0)],
        [[20., 1., 2., 3., 2., 1., 4., .5, .2, .3, 4., 10., 6.]],
        [[0], [1], [2], [3], [4]], [], 20000, None, True,
        entry_projection_width_s=width, road_representation=rep)


def test_unknown_or_unprojected_representation_is_rejected():
    with pytest.raises(ValueError, match="road_representation"):
        road("blocks")
    with pytest.raises(ValueError, match="positive entry projection width"):
        road(MB, 0.)


def test_identity_and_rows_default():
    rows, mark = road(), road(MB)
    assert mark.snapshot()[0] == rows.snapshot()[0] + ":" + MB
    assert rows.road_representation == "rows" and mark.road_representation == MB
    assert rows.projection_diagnostics()["road_representation"] == "rows"


def test_shared_path_preserves_observables_of_rows_path():
    rows, mark = road(), road(MB)
    offers = [(0, .3, 0., None, None), (1, .2, 0., None, None), (2, .1, 0., None, None)]
    for i in range(60):
        ea, eb = rows.step(1., offers if i < 10 else []), mark.step(1., offers if i < 10 else [])
        for tag in range(3):
            for dest in (None, 1, 2, 3, 4):
                a = math.fsum(e[3] for e in ea if e[0] == tag and e[2] == dest)
                b = math.fsum(e[3] for e in eb if e[0] == tag and e[2] == dest)
                assert b == pytest.approx(a, rel=1e-12, abs=1e-15)
        sa, sb = rows.snapshot(), mark.snapshot()
        assert sb[4] == pytest.approx(sa[4], rel=1e-12, abs=1e-15)
        for la, lb in zip(sa[5], sb[5]):
            assert lb == pytest.approx(la, rel=1e-12, abs=1e-15)
        for ca, cb in zip(sa[2], sb[2]):
            for k in (2, 3):  # mass, birth per cell
                a = math.fsum(p[k] for _, parts in ca[1] for p in parts)
                b = math.fsum(p[k] for _, parts in cb[1] for p in parts)
                assert b == pytest.approx(a, rel=1e-12, abs=1e-15)
            a = math.fsum(p[2] * p[4] for _, parts in ca[1] for p in parts)
            b = math.fsum(p[2] * p[4] for _, parts in cb[1] for p in parts)
            assert b == pytest.approx(a, rel=1e-12, abs=1e-13)
    diag = mark.projection_diagnostics()
    assert diag["road_representation"] == MB and diag["checkpointed"] is False
    assert sa[4][1] == pytest.approx(6.0)


def test_shared_byte_failure_preserves_state():
    mark = road(MB, 2e-5)
    mark.configure_storage_budget(1024**2)
    mark.step(1., [(0, .3, 0., None, None)])
    before = mark.snapshot()
    with pytest.raises(MemoryError, match="storage budget"):
        mark.step(1., [])
    assert mark.snapshot() == before


@pytest.mark.parametrize("storage_policy", ["legacy_records", "bounded_bytes_v1"])
def test_whole_engine_mark_block_binding_checkpoint_replay(tmp_path, storage_policy):
    city, legs, corridors = small_fixture()
    _, calendar, payload = make_native(city, legs, corridors)

    def engine(rep, width=.25):
        return NativeWholeEngine(calendar, payload, 256 * 1024**2, storage_policy=storage_policy,
                                 entry_projection_width_s=width, road_representation=rep)
    rows, native = engine("rows"), engine(MB)
    assert native.identity == rows.identity.replace("retained_capacity_v4", "retained_capacity_v5") + ":" + MB
    assert native.execution_config()["road_representation"] == MB
    if storage_policy == "bounded_bytes_v1":
        assert native.storage_config()["resource_binding"] == "retained_capacity_v5"
        assert rows.storage_config()["resource_binding"] == "retained_capacity_v4"
        assert ":retained_capacity_v5:" in native.identity
    with pytest.raises(ValueError, match="road_representation"):
        engine("blocks")
    middle = native.advance(native.initial(), 30.)
    path = tmp_path / "mark.bin"
    native.save(str(path), middle)
    fresh = engine(MB)
    restored = fresh.load(str(path))
    a, b = native.advance(middle, 60.), fresh.advance(restored, 60.)
    assert native.report(a) == fresh.report(b)
    left, right = tmp_path / "left.bin", tmp_path / "right.bin"
    native.save(str(left), a)
    fresh.save(str(right), b)
    assert left.read_bytes() == right.read_bytes()
    with pytest.raises(ValueError, match="binding"):
        rows.load(str(path))
    # Physical ledgers agree with the row representation.
    ra = rows.report(rows.advance(rows.initial(), 60.))["ledger"]
    ma = native.report(a)["ledger"]
    for unit in ra:
        for key in ra[unit]:
            assert ma[unit][key] == pytest.approx(ra[unit][key], rel=1e-9, abs=1e-12)
