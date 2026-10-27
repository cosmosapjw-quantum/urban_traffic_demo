"""Release preflight must bind real inputs and refuse false full-run receipts."""
import json
import lzma
from dataclasses import replace

import pytest

import tools.run_v1_acceptance as acceptance
from metroflow.v1.access_audit import fixture_city
from metroflow.v1.city import compile_city
from metroflow.v1.generated_entries import generate_entries


def test_frozen_release_patch_reconstructs_exact_city_and_rejects_corruption(tmp_path):
    fixture = fixture_city()
    block = replace(fixture.face_graph.blocks[0], residents=100000, housing_capacity=100000)
    source = compile_city(fixture.roadmap, fixture.landscape, (block,))
    city, _ = generate_entries(source)
    frozen = tmp_path/'artifacts/v1/map_audit'
    evidence = tmp_path/'artifacts/v1_portal_resolution_20261027'
    frozen.mkdir(parents=True)
    evidence.mkdir(parents=True)
    base = frozen/'source.json.xz'
    base.write_bytes(lzma.compress(json.dumps(source.to_dict()).encode()))
    payload = dict(base_source=base.name, base_sha256=acceptance.sha(base),
                   parent_identity=source.identity, identity=city.identity,
                   portals=city.to_dict()['portals'])
    patch = evidence/'patch.json.xz'
    patch.write_bytes(lzma.compress(json.dumps(payload).encode()))
    row = dict(case='test', seed=7, patch=patch.name, patch_sha256=acceptance.sha(patch),
               identity=city.identity)
    (evidence/'00.audit.json').write_text(json.dumps(row))
    restored, _ = acceptance.load_release_city(dict(map_index=0,map_case='test',seed=7),tmp_path)
    assert restored.identity == city.identity
    patch.write_bytes(b'changed')
    with pytest.raises(ValueError, match='patch SHA'):
        acceptance.load_release_city(dict(map_index=0,map_case='test',seed=7),tmp_path)


def test_preflight_preserves_demand_failure_and_never_reports_execution(monkeypatch):
    monkeypatch.setattr(acceptance,'load_release_city',lambda case, root: (
        fixture_city(),dict(source_sha256='source',patch_sha256='patch')))
    result = acceptance.preflight(dict(id='small',day='weekday',max_cohorts=20000))
    assert result['demand_status'] == 'PHYSICAL_INFEASIBLE'
    assert result['executed_simulated_s'] == 0
    assert result['runtime_rss_measurement'] == 'NOT_RUN'
    assert result['status'] == 'BLOCKED_IMPLEMENTATION_DEPENDENCY'
    assert result['local_campaign'] == 'BLOCKED_LOCAL_EXECUTION'
