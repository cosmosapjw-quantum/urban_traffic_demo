import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("v1_plan", ROOT / "tools/v1_plan.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def plan():
    return json.loads((ROOT / "docs/v1/PLAN.json").read_text())


def test_plan_is_acyclic_and_every_required_deliverable_is_mapped():
    p = plan()
    order = mod.validate(p)
    assert len(order) == 21
    rank = {key: i for i, key in enumerate(order)}
    assert all(rank[d] < rank[n["id"]] for n in p["nodes"] for d in n["depends_on"])
    assert p["next_node"] in {n["id"] for n in p["nodes"] if n["status"] != "ACCEPTED"}


def test_generated_documents_are_one_view_of_one_authority():
    p = plan()
    for filename, text in mod.outputs(p).items():
        assert (ROOT / "docs/v1" / filename).read_text() == text


def test_cycle_dangling_and_empty_acceptance_are_rejected():
    p = plan()
    p["nodes"][0]["depends_on"] = ["RLS01"]
    with pytest.raises(ValueError, match="cycle"):
        mod.validate(p)
    p = plan()
    p["nodes"][1]["depends_on"] = ["missing"]
    with pytest.raises(ValueError, match="unknown"):
        mod.validate(p)
    p = plan()
    p["nodes"][1]["acceptance"] = []
    with pytest.raises(ValueError):
        mod.validate(p)


def test_scoped_tests_are_not_a_release_claim():
    with pytest.raises(ValueError, match="BLOCKED"):
        mod.validate(plan(), release=True)
    assert all(
        n["status"] == "ACCEPTED"
        and n["integration_evidence"]["merge_sha"] == "b687425b1daa6ce61f912240cafbd9f294b0578b"
        for n in plan()["nodes"]
        if n["id"] in ("P00", "M01", "T01")
    )


def test_changed_pr_target_and_unmapped_requirement_rejected():
    p = plan()
    p["nodes"][1]["pr"]["base"] = "main"
    with pytest.raises(ValueError):
        mod.validate(p)
    p = plan()
    p["requirements"][0]["nodes"] = []
    with pytest.raises(ValueError):
        mod.validate(p)


def test_verified_node_code_and_tests_really_exist_in_current_workspace():
    for n in plan()["nodes"]:
        if n["id"] not in ("M01", "T01"):
            continue
        assert all((ROOT / f).exists() for f in n["files"])


def test_status_labels_alone_do_not_forge_a_release():
    p = plan()
    for node in p["nodes"]:
        node["status"] = "ACCEPTED"
    p["next_node"] = None
    with pytest.raises(ValueError, match="missing receipt"):
        mod.validate(p, release=True)


def test_stacked_implementation_is_not_integration_or_acceptance():
    p = plan()
    assert p["execution_policy"]["implementation_mode"] == "stacked_scoped_then_review"
    m03 = next(n for n in p["nodes"] if n["id"] == "M03")
    assert m03["status"] == "VERIFIED_SCOPED"
    assert "integration_evidence" not in m03
    child = next(n for n in p["nodes"] if n["id"] == "D01")
    assert child["pr"]["base"] == m03["pr"]["branch"]
    assert child["implementation_parent"]["sha"] == "410b6f280347eb20b5bf0255755ec4674e233582"
    m03["status"] = "BLOCKED"
    with pytest.raises(ValueError, match="dependency lacks scoped evidence"):
        mod.validate(p)


def test_full_ci_is_deferred_for_v1_stacks_but_available_for_final_review():
    text = (ROOT / ".github/workflows/ci.yml").read_text()
    assert 'branches-ignore: ["v1/**"]' in text
    assert 'branches-ignore: ["v1/**", "research/v1-integration-20261025"]' in text
    assert "workflow_dispatch:" in text
    assert plan()["current_execution"]["full_repository_ci"] == "DEFERRED_BY_USER"
