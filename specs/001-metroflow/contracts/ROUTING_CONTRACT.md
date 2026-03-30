# ROUTING CONTRACT

## Scope

Defines the deterministic routing baseline for `001`.

For `007-routing-realism`, this contract remains authoritative for the older
deterministic helper and fallback baseline. The explicit OD-bound
network-coupled routing surface is defined separately under the 007 routing
realism contract.

## Inputs

- link generalized costs
- candidate path sets by OD pair
- path-size factors
- reroute policy thresholds
- route event flags

## Outputs

- deterministic baseline route choice inputs
- reroute decision outputs

## Units

- generalized cost: time units
- path-size factor: unitless
- reroute refractory window: ticks

## Admissible Ranges

- generalized cost components are `>= 0`
- path-size factors are positive
- refractory windows are integers `>= 0`
- candidate path K is finite and explicitly bounded per OD

## Invariants Preserved

- deterministic baseline fallback remains available
- candidate path K and path-size correction are both present
- reroute triggers are explicit and testable

## Failure Conditions

- routing that depends only on learning with no deterministic fallback
- negative cost components
- empty or malformed candidate path definitions
- unbounded reroute churn with no refractory rule

## Non-Goals

- no RL-first or LLM-first route choice
- no full dynamic traffic assignment solver in `001`
