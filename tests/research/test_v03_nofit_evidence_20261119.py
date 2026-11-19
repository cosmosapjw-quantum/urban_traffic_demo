"""Genuine 100k V03 preparation evidence and no-fit observation bounds."""
from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path
import json, shutil,subprocess,sys,hashlib
import pytest

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/'tools/research/assemble_v03_nofit_evidence.py'
PREP=ROOT/'artifacts/kcmb_v03_physics_20261119/preparation'
spec=spec_from_file_location('v03_nofit_reader',SCRIPT)
mod=module_from_spec(spec)
sys.modules[spec.name]=mod
assert spec.loader
spec.loader.exec_module(mod)


def test_measured_native_original_population_preparation_three_cities():
    v=mod.build_evidence(ROOT,PREP)
    r=v['readiness']
    assert r['dag']['completed']==19 and r['dag']['total']==21
    assert r['v03']['calendar_preparation_verified']==3
    assert r['v03']['completed_full_day_runs']==0
    assert r['v03']['required_full_day_runs']==9
    assert r['v03']['status']=='BLOCKED'
    assert v['preparation_source_consistency']['same_native_binary']
    assert v['preparation_source_consistency']['same_candidate_source']
    assert v['preparation_source_consistency']['same_release_matrix']
    counts={k:q['calendar_legs'] for k,q in v['case_preparations'].items()}
    assert counts=={'river_weekday_s17':5093765,
                    'coastal_weekend_s41':2449750,
                    'valley_weekday_s7':918450}
    assert sum(counts.values())==8461965
    assert all(q['resident_stock']==100000 for q in v['case_preparations'].values())
    assert all(q['peak_rss_bytes']<8*1024**3 for q in v['case_preparations'].values())


def test_no_fit_affine_envelope_on_previous_explicit_model_is_not_cta_validation():
    x=mod.build_evidence(ROOT,PREP)
    y=x['hypothetical_probe_observation_envelope']
    assert y['source_model_parameters_are_assumed'] is True
    assert y['all_affine_weights_admissible_no_fit'] is True
    assert y['model_sampling_rule_verified_by_city'] is False
    assert y['real_holdout_bins_within_envelope']==12
    assert y['real_holdout_total_bins']==12
    assert y['max_speed_mps']-y['min_speed_mps']>7.
    assert y['min_speed_mps']==pytest.approx(3.70124523256,rel=2e-10)
    assert y['max_speed_mps']==pytest.approx(10.8419400397,rel=2e-10)
    assert abs(y['python_rust_max_endpoint_discrepancy_mps'])<1e-11
    assert x['v03_original_physics_accepted'] is False


def test_candidate_binary_hash_conflict_is_visible_without_fake_campaign_credit(tmp_path):
    for f in PREP.glob('*.prepare.json'):
        shutil.copy2(f,tmp_path/f.name)
    name=tmp_path/'valley_weekday_s7.prepare.json'
    q=json.loads(name.read_text())
    q['native_binary_sha256']='0'*64
    name.write_text(json.dumps(q))
    r=mod.build_evidence(ROOT,tmp_path)
    assert r['preparation_source_consistency']['same_native_binary'] is False
    assert r['v03_original_physics_accepted'] is False
    assert r['readiness']['v03']['completed_full_day_runs']==0


def test_cli_writes_json_with_no_original_v03_success_claim(tmp_path):
    out=tmp_path/'v03.json'
    p=subprocess.run([sys.executable,str(SCRIPT),'--prep-dir',str(PREP),
                      '--output',str(out)],
                    cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert p.returncode==0,p.stderr
    x=json.loads(out.read_text())
    assert x['readiness']['v03']['calendar_preparation_verified']==3
    assert x['readiness']['v03']['completed_full_day_runs']==0
    assert x['v03_original_physics_accepted'] is False
    assert x['hypothetical_probe_observation_envelope']['model_sampling_rule_verified_by_city'] is False


def test_original_nonzero_traffic_prefix_replay_matches_fresh_byte_for_byte():
    from tools.research.assemble_v03_nofit_evidence import verify_prefix_replay
    prefix=ROOT/"artifacts/kcmb_v03_physics_20261119/prefix"
    start=json.loads((prefix/"valley_weekday_s7.native_23000.json").read_text())
    fresh=json.loads((prefix/"valley_weekday_s7.native_fresh_25300.json").read_text())
    resumed=json.loads((prefix/"valley_weekday_s7.native_resumed_25300.json").read_text())
    comparison=verify_prefix_replay(start,fresh,resumed)
    assert comparison["status"]=="EXACT_REPLAY_BYTE_IDENTICAL_SCOPED"
    assert comparison["simulated_s"]==25300.
    assert comparison["fresh_checkpoint_sha256"]==comparison["resumed_checkpoint_sha256"]
    assert comparison["ledger_equal"] is True
    assert comparison["nonzero_traffic_verified"] is True
    assert comparison["full_day_24h_accepted"] is False


def test_replay_match_must_reject_malformed_driver_and_checkpoint_binding():
    from copy import deepcopy
    from tools.research.assemble_v03_nofit_evidence import verify_prefix_replay
    prefix=ROOT/"artifacts/kcmb_v03_physics_20261119/prefix"
    start=json.loads((prefix/"valley_weekday_s7.native_23000.json").read_text())
    fresh=json.loads((prefix/"valley_weekday_s7.native_fresh_25300.json").read_text())
    resumed=json.loads((prefix/"valley_weekday_s7.native_resumed_25300.json").read_text())
    for field, value in [
        ("last_valid_checkpoint_sha256","0"*64),
        ("driver_identity","0"*64),
        ("physical_ledger_check","FAILED"),
        ("full_day_24h_acceptance","ACCEPTED"),
    ]:
        corrupted=deepcopy(resumed)
        corrupted[field]=value
        with pytest.raises(ValueError,match="replay|physical|checkpoint|identity|acceptance"):
            verify_prefix_replay(start,fresh,corrupted)


def test_integrated_evidence_preserves_both_replay_and_original_v03_block():
    receipt=mod.build_evidence(ROOT,PREP)
    comparison=receipt["physical_prefix_continuation"]
    assert comparison["status"]=="EXACT_REPLAY_BYTE_IDENTICAL_SCOPED"
    assert comparison["simulated_s"]==25300.
    assert comparison["full_day_24h_accepted"] is False
    assert receipt["readiness"]["v03"]["calendar_preparation_verified"]==3
    assert receipt["readiness"]["v03"]["completed_full_day_runs"]==0
    assert receipt["v03_original_physics_accepted"] is False


@pytest.mark.parametrize("source_field,output_flag", [
    ("native_binary_sha256","same_native_binary"),
    ("candidate_source_sha256","same_candidate_source"),
])
def test_identically_forged_three_city_hashes_are_not_live_source_verified(
        tmp_path,source_field,output_flag):
    # Equal hashes across cases do NOT prove that the bytes are the running
    # binary or source. Verify the hash against the actual connected checkout.
    for f in PREP.glob("*.prepare.json"):
        row=json.loads(f.read_text())
        row[source_field]="0"*64
        (tmp_path/f.name).write_text(json.dumps(row))
    out=mod.build_evidence(ROOT,tmp_path)
    assert out["preparation_source_consistency"][output_flag] is False
    assert out["preparation_source_consistency"]["joint_3city_preparation_eligible"] is False
    assert out["v03_original_physics_accepted"] is False
