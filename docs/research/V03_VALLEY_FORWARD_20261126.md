# Forward onset holdout

The surgical arm's original 10 s clock, activity access marks, fixed routes, zero entry speed, kinetic characteristic and transfer rule were frozen before inspecting the subsequent native receipts. A separate prediction command, which does not open native receipts, produced `FORWARD_BEFORE_RECEIPTS.json` with SHA-256 `7ff4d01b8dcd596723a56efa00cba5a9def0c8557fc636e93fc6900c2cd4625d`. Its file identity was reported before the first receipt was opened. Computing both future clocks took 25.13 s and 104,484 KiB peak RSS. These are near-term temporal holdouts in the same city and morning peak.

At 25,730 s the diagnostic native policy arm validated one source-bound step. Four single-segment scheduled buses had finished and zero buses remained on the road. The native car admissions were 996.911855 veh and exits 165.674144 veh. Frozen predictions were 996.911855 and 172.524528, giving an admission residual of +1.89e−11 veh, an outlet excess of +6.850384 veh (+4.135%), and a subsystem stock error of −0.824%. This outcome replicates the earlier direction and scale of the outlet bias. The 25,740 s prediction of 1,023.219240 admissions and 182.467086 exits was frozen in the same file. `FORWARD_SCORE.json` names each scored clock and keeps clocks without a validated native physical receipt explicit.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python forward_onset.py "$REPO" "$PREPARED" fresh-prediction.json 25730 25740
python compare_forward.py FORWARD_BEFORE_RECEIPTS.json score.json "$ARM75_JSONL" "$COMBINED75_JSONL"
```

The native validation here uses an explicitly changed diagnostic policy. It supplies an observable for comparison. Eligibility for the original V03 release contract is evaluated separately.

The completed combined-policy trial independently produced the same 25,730 s observables, then rejected its 25,740 s step. A subsequent indexed-receiver run at the same 7.5 GiB diagnosed budget passed 25,740 s. At that clock the frozen prediction gave 1,023.219239805250 car offers and 182.467086401585 car exits. Native recorded 1,023.219239805230 car offers and 174.946827474881 exits. The outlet error is +7.520259 veh (+4.299%) and the road-stock error −0.887%. The indexed receiver also matched the two earlier physical reports at 25,730 s. The scored file contains the native row hashes at both clocks. Re-run compare_forward.py with the indexed-wide.jsonl path appended to the two prior arm paths.
