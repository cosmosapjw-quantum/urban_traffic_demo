"""C8 source-bound exact physical equivalence of default native bitset transition.

The previous Mark-compressed binary is an independent old-state reference,
and the current code must preserve original checkpoint bytes, no pair-credit.
"""
import hashlib
import json
from pathlib import Path

from metroflow.v1.native_engine import native_binary_provenance
from tools.run_v1_local_acceptance import candidate_provenance

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts/v03_composed_events_20261120"


def test_new_bitset_exact_original_native_valley_25650_checkpoint():
    new = json.loads((ART / "C8_BITSET_ORIGINAL_DEFAULT_25650.json").read_bytes())
    old = json.loads((ART / "C2_ORIGINAL_DEFAULT_25650.json").read_bytes())
    assert new["status"] == old["status"] == "EXECUTED_SOURCE_BOUND_25650_SCOPED"
    assert new["experiment_env"] == old["experiment_env"] == "OFF"
    assert new["reached_end_s"] == old["reached_end_s"] == 25650
    assert new["original_100k_valley"] is True
    assert new["original_86400s_day"] == 86400
    assert new["original_24h_runs_accepted"] == 0
    assert new["original_native_cap_bytes"] == old["original_native_cap_bytes"] == 5242806391
    assert new["original_8GiB_process_cap_bytes"] == 8*1024**3
    assert new["original_input_checkpoint_sha256"] == old["original_input_checkpoint_sha256"]
    assert new["original_driver_identity"] == old["original_driver_identity"]
    assert new["original_matrix_sha256"] == old["original_matrix_sha256"]
    assert new["mass_ledger"] == old["mass_ledger"]
    assert new["checkpoint_bytes"] == old["checkpoint_bytes"] == 1683486650
    assert new["final_checkpoint_sha256"] == old["final_checkpoint_sha256"]
    assert new["final_checkpoint_sha256"] == "89e3230b23b4423509f6036035e9b03c7299204b5d317cdb3f6226c5b0c53e8b"
    assert new["trace_counters"]["arc.experimental_paired_credit"] == [5,0,0]
    assert new["source_sha256"] == candidate_provenance()["source_sha256"]
    assert new["loaded_native_sha256"] == native_binary_provenance()["sha256"]
    assert new["loaded_native_sha256"] != old["loaded_native_sha256"]
    assert new["peak_rss_bytes"] < 8*1024**3
    f = ART / "C8_BITSET_ORIGINAL_DEFAULT_25650.final.bin"
    h = hashlib.sha256()
    with f.open("rb") as stream:
        for chunk in iter(lambda:stream.read(8*1024*1024),b""):
            h.update(chunk)
    assert h.hexdigest() == new["final_checkpoint_sha256"]
