"""V02 audits preserve unsupported service and render frozen execution geometry."""

import importlib.util
import json
from pathlib import Path
import gzip
import pytest
from metroflow.v1.access_audit import fixture_city
from metroflow.v1.city import load_city, CityContractError

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("audit_v1_maps", ROOT / "tools/audit_v1_maps.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_frozen_seeds_and_case_matrix_are_fixed_not_searched():
    assert audit.SEEDS == (7, 17, 41)
    assert len(audit.PRIMARY) == 6
    assert len(set(name for name, _, _ in audit.PRIMARY)) == 6


def test_registered_access_not_replaced_by_hypothetical_boundary_doors():
    city = fixture_city()
    # Remove the explicit registry to reproduce the generated atlas contract.
    data = city.to_dict()
    data["portals"] = []
    data.pop("identity")
    missing = load_city(data)
    row = audit.audit_city(missing)
    assert row["registered_served_residents"] == 0
    assert row["registered_unserved_residents"] == 1000
    assert row["registered_access_cdf"] is None
    assert row["declared_boundary_access_mass"] == pytest.approx(1000)
    values = [v for _, v in row["declared_boundary_access_cdf"]]
    assert values == sorted(values) and 0 <= values[0] <= values[-1] <= 1


def test_svg_is_generated_from_frozen_json_and_binds_source_identity(tmp_path):
    data = fixture_city().to_dict()
    source = tmp_path / "fixture.json.gz"
    source.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
    restored = audit.read_frozen(source)
    digest = audit.sha(source)
    svg = audit.render_svg(restored, "fixture", digest)
    assert "frozen_json_archive_sha256:" + digest in svg
    assert f"registered portals={len(restored['portals'])}" in svg
    altered = dict(restored, portals=[])
    assert audit.render_svg(altered, "fixture", digest) != svg


def test_illegal_geometry_does_not_get_an_empty_success_flag():
    data = fixture_city().to_dict()
    data["roadmap"]["sections"][0]["length_m"] = -1
    data.pop("identity")
    with pytest.raises(CityContractError):
        load_city(data)


def test_frozen_evidence_has_all_cases_and_keeps_unserved_population():
    matrix = ROOT / "artifacts/v1/map_audit/MATRIX.json"
    if not matrix.exists() or json.loads(matrix.read_text())["status"] == "IN_PROGRESS":
        pytest.skip("full V02 audit has not completed; never replace with fake pass")
    result = json.loads(matrix.read_text())
    assert result["primary_cases"] == 18 and result["mixed_cases"] == 20
    primary = [r for r in result["cases"] if r["family"] == "primary"]
    assert len(primary) == 18
    assert {(r["case"], r["seed"]) for r in primary} == {
        (name, seed) for name, _, _ in audit.PRIMARY for seed in audit.SEEDS
    }
    assert len(result["cases"]) == 38
    for row in result["cases"]:
        assert row["residents"] + row["unplaced_residents"] == row["requested_population"] == 100000
        assert (
            row["registered_served_residents"] + row["registered_unserved_residents"]
            == row["residents"]
        )
        assert not row["geometry_flags"]
        source = matrix.parent / row["source"]
        assert audit.sha(source) == row["source_sha256"]
        assert audit.sha(matrix.parent / row["svg"]) == row["svg_sha256"]
    assert (matrix.parent / "REPRESENTATIVE_SIX.png").is_file()
