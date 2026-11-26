"""Source-specific arithmetic of the observed next refusal; not an admission override."""
import json,sys
from pathlib import Path
p=Path(sys.argv[1])
r=json.loads(p.read_text().splitlines()[-1])
assert r['phase']=='rejected'
s=r['trace']['sites']
k=s['journey_commit:checkpointability']
t=k['terms_at_max']
road=t['input_road']+t['current_road']+max(t['candidate_road'],t['decoded_road'])
journey=t['journey_retained_input']+t['old_journey']+max(t['new_journey'],t['decoded_journey'])
events=t['input_event']+t['current_event']+t['candidate_event']
assert (road,journey,events)==(t['phase_road_charge'],t['phase_journey_charge'],t['phase_event_charge'])
owners=road+journey+events
scratch=k['max_required']-owners
assert scratch==t['road_decode_scratch']
validation=max(0,t['validation_scratch']-t['call_binding_reserve'])
limit=k['limit_at_max']
print(json.dumps(dict(owners_bytes=owners,road_bytes=road,journey_bytes=journey,event_bytes=events,
    charged_decoder_scratch_bytes=scratch,nondecoder_validation_bytes=validation,
    allowed_bytes=limit,required_bytes=k['max_required'],
    excess_bytes=k['max_required']-limit,maximum_scratch_if_owner_terms_unchanged_bytes=limit-owners,
    conditional_required_if_only_validation_scratch_remained_bytes=owners+validation,
    conditional_headroom_if_only_validation_scratch_remained_bytes=limit-owners-validation,
    interpretation='conditional arithmetic only: must bound actual uninterned decoder and restore; no cap or admission changed'),indent=2))
