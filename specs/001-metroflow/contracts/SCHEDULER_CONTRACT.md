# SCHEDULER CONTRACT

## Scope

Defines the multirate scheduling boundary for the `001` baseline.

## Inputs

- `step_idx: int`
- `TickSchedule(fast_every: int, medium_every: int, slow_every: int)`

## Outputs

- `SchedulerDecision(run_fast: bool, run_medium: bool, run_slow: bool)`

## Units

- all cadence fields are integer ticks

## Admissible Ranges

- `fast_every > 0`
- `medium_every > 0`
- `slow_every > 0`
- `fast_every <= medium_every <= slow_every`

## Invariants Preserved

- cadence decisions are deterministic for equivalent inputs
- fast, medium, and slow decisions are computed from explicit tick cadence only
- scheduler does not close same-tick loops across traffic, accessibility,
  land-use, or policy surfaces

## Forbidden Coupling

- same-tick travel time -> accessibility -> relocation / redevelopment
- same-tick accessibility -> demand regeneration -> traffic update
- same-tick policy update -> routing update -> policy update

## Failure Conditions

- non-positive cadence values
- cadence ordering that violates `fast <= medium <= slow`
- any design that mutates non-target subsystems in the same tick without an
  explicit lagged contract
