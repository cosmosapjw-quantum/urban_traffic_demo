# Theory-only calculations, 2026-11-23

This directory contains reproducible small mathematical calculations.
It is not a production module, native integration test, city simulation, or
runtime benchmark. Original demand, source code and V03 thresholds are unchanged.

From this directory, using Python standard library:

    python check_controlled_routes.py
    python check_reconstruction_examples.py

The first imports the pre-existing exact-rational PL fluid-server helper
check_causal_service_stability.py. That helper is preserved unchanged; its
standalone historical main concerns fixed capacity, but the new caller changes
both E and C in 128 pairs. It compares the full PL reflection curve including
internal emptying knots against a queue-balance recurrence.

The second checks operator-overlay and quotient examples, initial stock,
the Mixed joint-clock and jump-reset counterexamples, positive atom elimination,
and 60-digit Decimal flux-mark refinement. It writes R7_reconstruction_examples.json.
The first writes metroflow_controlled_routes_checks.json.
metroflow_exact_routes_calculation.json preserves the author's original exact
worked-example result. R7_WOLFRAM.json contains the two actual evaluator inputs
and outputs; reproducing those symbolic checks requires Wolfram Language.

Observed Python version:3.12.14. Both caller commands exited0 in the scratch
research environment. These finite checks support the displayed examples;
the analytic proofs and all validity conditions remain in the research notes.
The calculation's wall time is not a city-performance result.

Theoretical artifacts are tied to source baseline
492e27618696df2514b088a64de450cf69746647. New source code execution and all
full-day V03 runs are NOT_RUN for this theory-only session.
