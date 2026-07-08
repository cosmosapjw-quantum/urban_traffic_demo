from __future__ import annotations

from enum import Enum


class Severity(str, Enum):
    INFO = "info"
    WARN = "warn"
    HARD_FAIL = "hard_fail"


class RealismRuleID(str, Enum):
    FR_006_INTERSECTION_CONTROL = "FR-006"
    SC_001_HARD_FAIL_RATE = "SC-001"
    SC_002_ENVELOPE_COVERAGE = "SC-002"
    SC_004_ORIENTATION_COLLAPSE = "SC-004"
    SC_006_RING_RADIAL_CONNECTIVITY = "SC-006"
    SC_010_DOWNTOWN_UPTOWN = "SC-010"
    SC_011_INCIDENT_STRESS = "SC-011"
