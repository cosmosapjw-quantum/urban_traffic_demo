#!/usr/bin/env python3
"""One tiny exact arithmetic check for the bounded native source-owner review.

This does not execute Rust or construct a native state. The extreme case is an
abstract usize-expression counterexample, not a reachable 100k fixture.
"""
import json

U64_MAX = (1 << 64) - 1
V03_CAP = 6 * 1024**3

def sat_add(a, b):
    return min(U64_MAX, a + b)

def sat_sub(a, b):
    return max(0, a - b)

# Observed RED fixture: new discovery equation only, not a rerun of its test.
old_census, shared_events, fixed_cap = 77_123_790, 328_552, 76_959_514
corrected_census = old_census - shared_events
assert corrected_census <= fixed_cap < old_census

# New expression's full-usize limitation, with no allocation attempted.
# A single shared event owner is still astronomically larger than V03_CAP.
fixed, scratch, ei, ec = 65_536, 4_096, U64_MAX, U64_MAX
uncredited = sat_add(ei, ec)
charged_live = sat_sub(uncredited, ei)
production_expression = sat_add(sat_add(fixed, charged_live), scratch)
exact_required = fixed + ei + scratch
event_union_first = sat_add(sat_add(fixed, sat_add(ei, sat_sub(ec, ei))), scratch)
assert production_expression <= V03_CAP < exact_required
assert event_union_first == U64_MAX > V03_CAP

# If a saturated total is reduced by at most the ordinary 6 GiB owner size,
# it necessarily still rejects. No sweep or full-range proof is claimed.
safe_saturated_lower_bound = U64_MAX - V03_CAP
assert safe_saturated_lower_bound > V03_CAP

print(json.dumps({
    "status": "EXACT_ARITHMETIC_CHECKED",
    "native_code_executed": False,
    "observed_fixture_arithmetic": {
        "old_census": old_census, "shared_events": shared_events,
        "corrected_census": corrected_census, "fixed_cap": fixed_cap
    },
    "abstract_extreme_counterexample": {
        "event_owner_bytes": ei, "cap": V03_CAP,
        "production_expression": production_expression,
        "exact_required": exact_required,
        "event_union_first_saturated": event_union_first,
        "reachable_native_fixture": False
    },
    "safe_if_credit_le_v03_cap": safe_saturated_lower_bound
}, indent=2))
