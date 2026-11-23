# C5 native verification notes

Behavioral baseline: checkpoint decode of 8,193 original EventRows retained 524,480 bytes and failed the new persistent-storage assertion. The command selected one real test; an initial overly strict short-name filter selected zero tests and was not counted as RED.

The first full library run after the representation change returned 228 passed, 3 failed, 2 ignored. The failures were:
- exact_shared_event_source_budget_tests::only_pointer_identical_old_event_backing_can_be_counted_once: 271072 vs legacy 270576.
- workspace_accounting_tests::road_step_event_charge_has_no_sink_terms: 790568 vs legacy 789816.
- persistent_event_page_contract_20261123_tests::existing_page_backings_survive_persistent_candidate_growth: the proposed assertion storage <8193*64 was false at a partially occupied third fixed page.

The first two expected values omitted the newly charged persistent carrier, allocation padding and descriptor growth. They were updated to the new conservative page-accounting contract while retaining the old-sharing distinction. The third was an incorrect test generalization: an append store at 8,193 rows reserves 12,288 slots, so compact page storage need not beat an exact flat allocation at every small page boundary. It now checks actual 3*4096*48 payload capacity, unchanged old page pointers and the large 20,270,113-row decode bound. No cap or source population was changed to satisfy the checks.

Final command:
CARGO_TARGET_DIR=/home/cosmosapjw/worktrees/urban-traffic-v03-unique-accounting-20261120/target RUSTFLAGS='-C link-arg=-lpython3.12' cargo test --offline --workspace --lib --quiet

Actual final result: 231 passed; 0 failed; 2 ignored. Existing unused/dead-code warnings remain. Full repository CI and original 100k physical experiments were not executed by this worker.
