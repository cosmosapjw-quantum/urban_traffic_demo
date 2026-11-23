# C8 checkpoint refreeze: Journey decoder validator phase

2026-11-23. This additive note supersedes the three-phase admission interpretation and source freeze in [C8_checkpoint_author_note.md](C8_checkpoint_author_note.md) / [C8_checkpoint_freeze.json](C8_checkpoint_freeze.json). Those earlier source/build/test receipts remain preserved as intermediate evidence.

## Independent review finding and minimal correction

The independent delta review found a concrete missing phase: `NativeJourneyCore::read_state` ends by calling `validate`, whose existing bounded-byte guard requires `3*max(Journey, retained_input)+65536`. The preceding fresh bundle expression charged one decoded Journey plus bundle-validation scratch. Small bundle scratch does not cover the Journey validator's separate three-owner admission floor.

The correction adds exactly this fresh phase, while retaining every previous phase:

```
P_journey_validator =
    actual constructor current road
  + empty constructor event carrier
  + independent decoded road envelope
  + independent event decode upper
  + 3 * decoded Journey upper
  + 65536

required = max(P_current, P_fresh_road, P_journey_validator, P_fresh_bundle)
```

The actual Journey validator, three-owner policy, decode guards, physical values, caps and other source bindings are unchanged. This is a monotone addition to admission, not a reduction of a validator requirement.

## Actual loader regression and final verification

A valid one-leg Journey with 4096 exact binary64 receipt fractions was serialized and decoded through the real `NativeJourneyCore::read_state`, not only a synthetic budget formula.

| Quantity | Bytes |
|---|---:|
| Actual independently decoded Journey storage | 84,992 |
| Source-specific decoded Journey upper | 119,664 |
| Residual allowance predicted by the previous fresh-phase maximum | 185,200 |
| Actual unchanged Journey validator requirement | 320,512 |
| Residual allowance from the corrected explicit validator phase | 424,528 |
| Re-serialized wire, identical byte for byte | 65,632 |

The old residual allowance actually rejects with `native journey stored/working byte budget`. The corrected allowance succeeds and retains the exact wire. The fresh target remains unchanged on rejection. A second regression preserves the independent review's D=E=J=1,000,000 counterexample: the old fresh maximum is 3,000,000+65536+empty shell, whereas the actual validator phase is 5,000,000+65536+empty shell.

Final authority: [C8_checkpoint_journey_validator_fix_lib.log](C8_checkpoint_journey_validator_fix_lib.log), [exit](C8_checkpoint_journey_validator_fix_lib.exit): **285 passed, 0 failed, 2 ignored; exit 0**. This includes the two closure regressions and all prior bounded library regressions. Test execution 0.18 s. `git diff --check` passes. No extra optional sweep was performed.

## Refrozen source

| File | SHA256 |
|---|---|
| journey | `285cf61a9e1339dbf68a0754d1efdd76d8d21a33ceed6931fe29b7b97380f32d` |
| road, unchanged | `01694c9ec17d06b43188a9d8e9d93a4dd099173533642e993631befa5ef3a939` |
| engine, unchanged | `bf078c2d45fda2805531812b3f74a2955a0b4137098c2cc6fc959bf8743f4e93` |

Source is frozen and Cargo released for closure of this specific review finding, followed by the parent-owned build/actual runtime verification. Earlier native build/preparation outputs belong only to the superseded source. They are not final-source runtime evidence.

Drift verdict remains **ALIGNED_WITH_OPEN_OBLIGATION**: the correction preserves the declared computational and physical contracts while making the checkpoint estimate match the real validator. New physical-time credit is **0** at this refreeze; independent fresh restore and the mandatory 43200 s same-engine acceptance remain outstanding runtime obligations.
