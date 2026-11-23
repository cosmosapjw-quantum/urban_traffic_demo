#!/usr/bin/env python3
"""Independent integer witness; no native execution or physical-prefix credit."""
import json
S=64*1024
D=E=J=1_000_000
initial_road=empty_event=1024
current=(3*D-2*900_000)+(3*J-2*900_000)+2*E+S
fresh_road=3*D+S+empty_event
fresh_bundle=initial_road+empty_event+D+E+J+S
actual_journey_validation=initial_road+empty_event+D+E+3*J+S
cap=4_800_000
old=max(current,fresh_road,fresh_bundle)
assert old<=cap<actual_journey_validation
result=dict(scope='integer counterexample to omitted fresh Journey 3max validator phase, not native behavioral RED',current_phase=current,old_fresh_road=fresh_road,old_fresh_bundle=fresh_bundle,old_three_phase_max=old,actual_fresh_journey_validator_required=actual_journey_validation,example_cap=cap,missing_bytes=actual_journey_validation-old,original_actual_validator_preserved=True)
print(json.dumps(result,indent=2))
