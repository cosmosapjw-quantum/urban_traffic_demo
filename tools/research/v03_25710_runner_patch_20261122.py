from pathlib import Path
src=Path('tools/research/v03_cohort_cross_native_25700_20261121.py')
dst=Path('tools/research/v03_25710_cross_native_20261122.py')
s=src.read_text()
s=s.replace("Each invocation loads one SHA-bound completed checkpoint, validates binary wire,",
"""The only newly admitted historical cross-native source is the EXACT verified
original 100k Valley 25,710s checkpoint SHA 64b77bae... with retained full
original physics conservation ledger. No arbitrary partial failure is admitted.

Each invocation loads one SHA-bound completed checkpoint, validates binary wire,""",1)
needle='    # Older exact source-bound original 25,650 checkpoint has a different\n'
assert s.count(needle)==1
branch='''    # Narrow, exact 25710 checkpoint produced from a real original 100k
    # physical step and saved twice with matching full original wire.
    cross_native_25710=(
        prev.get("schema")=="V03_ORIGINAL_100K_CONTINUOUS_ESCALATING_HORIZON_V1"
        and prev.get("status")=="EXECUTED_CURRENT_SOURCE_CONTINUOUS_HORIZON"
        and prev.get("case")==CASE
        and prev.get("start_time_s")==25700.
        and prev.get("completed_time_s")==25710.
        and prev.get("requested_duration_s")==10
        and prev.get("valid_advanced_duration_s")==10.
        and prev.get("final_checkpoint_sha256")==
            "64b77baece5ba45fa0928d59b58d9f8f9fc2178bcd93542b05264736978733fe"
        and prev.get("final_checkpoint_bytes")==4011233450
        and prev.get("current_candidate_source_sha256")==
            "272e76339894bfc9215384fa963ef4e68ccdbc50ddbe4755d7bb8fab9e0fa6da"
        and prev.get("current_native_binary_sha256")==
            "e5d36a00b77701db2eb7da0835754cd6f30c48f1aba5772263c37c6ccc7e84b6"
        and prev.get("trace_mode")=="record"
        and prev.get("native_process_cap_bytes")==CAP
        and prev.get("original_full_day_acceptance")=="BLOCKED_0_OF_9"
        and prev.get("previous_checkpoint_full_wire_roundtrip_exact") is True
        and prev.get("current_source_dirty") is False
        and prev.get("completed_mass_ledger") is not None
        and prev.get("error") is None
        and prev.get("trace_counters",{}).get("arc.experimental_paired_credit",[0,1])[1]==0
    )
    # Source and native MUST be different from the old verified original.
    if cross_native_25710:
        prev={**prev,"budget_mode":"DEFAULT"}
'''
s=s.replace(needle,branch+needle)
needle='    if historical_origin:\n        historical_source_identity={'
assert s.count(needle)==1
s=s.replace(needle,'''    if cross_native_25710:
        historical_source_identity={
            "source_sha256":prev["current_candidate_source_sha256"],
            "native_sha256":prev["current_native_binary_sha256"],
            "source_status":prev["status"],
        }
'''+needle)
# A new native needs to be a distinct trusted source; same-source continuation unchanged.
s=s.replace('not (historical_origin or cross_native_25700)', 'not (historical_origin or cross_native_25700 or cross_native_25710)')
s=s.replace('(historical_origin or cross_native_25700) and (', '(historical_origin or cross_native_25700 or cross_native_25710) and (')
s=s.replace('"previous_checkpoint_cross_native":historical_origin or cross_native_25700,',
            '"previous_checkpoint_cross_native":historical_origin or cross_native_25700 or cross_native_25710,\n        "cross_native_original_25710_source":cross_native_25710,')
assert 'cross_native_original_25710_source' in s
assert s.count('cross_native_25710')>=6
dst.write_text(s)
print('CREATED',dst,'lines',len(s.splitlines()),'cross_native_25710 occurrences',s.count('cross_native_25710'))
