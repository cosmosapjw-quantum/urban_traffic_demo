"""One source/binary original native: default block vs opt-in bounded replay.

Research-only admission variant, NOT original production 24h acceptance.
"""
from pathlib import Path
import hashlib
import json
from tools.run_v1_local_acceptance import candidate_provenance
from metroflow.v1.native_engine import native_binary_provenance

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/"artifacts/v03_fifo_unique_accounting_20261120"


def _load(name):
    return json.loads((ART/name).read_bytes())


def test_default_source_native_still_hits_the_exact_original_budget_gate():
    old=_load("C8_ORIGINAL_DEFAULT_25650.json")
    assert old["mode"]=="ORIGINAL_DEFAULT"
    assert old["experiment_env"]=="OFF"
    assert old["status"]=="BLOCKED_BudgetExceeded"
    assert old["reached_end_s"] is None
    assert old["final_checkpoint_sha256"] is None
    assert old["original_native_cap_bytes"]==5242806391
    assert old["error"]["message"]=="native road storage budget exceeded: phase=packet interval packing, required_bytes=5242811264, budget_bytes=5242806391"
    assert old["trace_counters"]["arc.experimental_paired_credit"]==[5,0,0]
    assert old["trace_mode"]=="record_not_observe"
    assert old["original_24h_runs_accepted"]==0


def test_two_optin_replays_reproduce_same_25650_state_and_source_hashes():
    old=_load("C8_ORIGINAL_DEFAULT_25650.json")
    a=_load("C8_PAIR_RUN1_25650.json")
    b=_load("C8_PAIR_EXPERIMENT_25650.json")
    assert a["mode"]==b["mode"]=="PAIR_EXPERIMENT"
    assert a["experiment_env"]==b["experiment_env"]=="source_pair_only"
    assert a["status"]==b["status"]=="EXECUTED_SOURCE_BOUND_25650_SCOPED"
    assert a["reached_end_s"]==b["reached_end_s"]==25650
    assert a["final_checkpoint_sha256"]==b["final_checkpoint_sha256"]
    assert a["mass_ledger"]==b["mass_ledger"]
    for row in (a,b):
        assert row["original_native_cap_bytes"]==old["original_native_cap_bytes"]==5242806391
        assert row["original_8GiB_process_cap_bytes"]==old["original_8GiB_process_cap_bytes"]==8*1024**3
        assert row["original_24h_runs_accepted"]==0
        assert row["original_driver_identity"]==old["original_driver_identity"]
        assert row["original_input_checkpoint_sha256"]==old["original_input_checkpoint_sha256"]
        assert row["loaded_native_sha256"]==old["loaded_native_sha256"]==native_binary_provenance()["sha256"]
        assert row["source_sha256"]==old["source_sha256"]==candidate_provenance()["source_sha256"]
        assert row["trace_counters"]["arc.experimental_paired_credit"][1]>0
        assert row["trace_mode"]=="record_not_observe"
        assert row["peak_rss_bytes"]<8*1024**3
    checkpoint=ART/"C8_PAIR_EXPERIMENT_25650.final.bin"
    h=hashlib.sha256()
    with checkpoint.open("rb") as f:
        for data in iter(lambda:f.read(4*1024*1024),b""):
            h.update(data)
    assert h.hexdigest()==b["final_checkpoint_sha256"]
    assert checkpoint.stat().st_size==a["checkpoint_bytes"]==b["checkpoint_bytes"]


def test_repeated_full_physical_mass_ledger_and_no_fake_release():
    row=_load("C8_PAIR_EXPERIMENT_25650.json")
    ledger=row["mass_ledger"]
    assert ledger is not None
    for field in ("persons","vehicles","cargo_kg"):
        r=ledger[field]
        assert abs(r["requested"]-r["released"]-r["pending"])<1e-6
        assert abs(r["released"]-r["completed"]-r["active"])<1e-6
    assert row["claim_limit"].startswith("opt-in experimental")
    assert row["original_86400s_day"]==86400
    assert row["original_24h_runs_accepted"]==0
