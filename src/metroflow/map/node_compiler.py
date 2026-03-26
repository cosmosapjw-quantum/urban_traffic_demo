from dataclasses import dataclass


@dataclass(frozen=True)
class NodeRuleSet:
    through_continuity: bool = True
    turn_pocket_separation: bool = True
    conflict_suppression: bool = True
    signal_eligible: bool = True
