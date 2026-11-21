"""Guard durable ten-stage provenance and do not inflate V03 acceptance."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def test_r10_stage_ledger_is_source_bound_and_counts_only_completed_physics():
    root=ROOT/"artifacts/v03_fifo_cohort_20261121"
    d=json.loads((root/"R10_STAGE_LEDGER.json").read_text())
    assert d["stages_completed_as_bounded_research"]==d["stages_planned_as_bounded_research"]==10
    commits=d["stage_commits"]
    assert len(commits)==len({x["commit"] for x in commits})==10
    assert all(x["stage"]==f"R{i}/C{i}" and x["pushed_sha_readback"] for i,x in enumerate(commits,1))
    last=commits[-1]
    assert last["commit"]=="d39d40a8ab05d5eccf1d20d44bc25ced51ac3ff8"
    readiness=d["fresh_current_source_V03_readiness"]
    assert readiness["dag_accepted_or_verified_scoped"]==19
    assert readiness["dag_total"]==21
    assert readiness["direct_v03_dependencies_completed"]==3
    assert readiness["native_whole_city_prepared"]==3
    assert readiness["full_original_24h_runs_completed"]==0
    assert readiness["full_original_24h_runs_total"]==9
    assert readiness["v03_status"]=="BLOCKED"
    ladder=d["physical_elapsed_ladder"]
    assert [x["requested_simulated_s"] for x in ladder]==[10,20,40,80]
    assert [x["actually_completed_simulated_s"] for x in ladder]==[10,20,20,0]
    assert d["same_previous_source_valid_physical_advanced_prefix_s"]==50
    assert d["new_current_candidate_valid_physical_advanced_prefix_s"]==0
    for x in ladder:
        source=json.loads((ROOT/x["receipt"]).read_text())
        assert x["actually_completed_simulated_s"]==source["valid_advanced_duration_s"]
        assert x["checkpoint_sha256_or_none"]==source["final_checkpoint_sha256"]
    blocked=d["R10_phase_specific_result"]
    assert blocked["formerly_blocked_packet_interval_packing_exceeds"]==0
    assert blocked["newly_blocked_transfer_candidates_exceeds"]==1
    assert blocked["newly_blocked_transfer_excess_bytes"]==55473
    assert blocked["new_source_25710_physical_tick"]=="BLOCKED_RESOURCE"
