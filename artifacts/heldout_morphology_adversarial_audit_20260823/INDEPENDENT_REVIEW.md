# Independent Repair-Closeout Review

## Review history

The first read-only review of candidate `0c5648797e472d4fb68cd6ccb7c3f1876a40bae4`
(tree `1da0422699ac197600e010f3bef2dcabcbc99f1e`) found no critical finding and four
blocking major findings. Its decision was FAIL. The four classes were incomplete
result/PNG validation, package/review-gate false-pass paths, a non-portable frozen
validator interface, and an incomplete scoped failure inventory.

The same reviewer then performed the single permitted repair-closeout review of
candidate `844691e5fff1178f888b6bed82837f687c54f61d`, tree
`0b5ea139911742af2f7d6dbbbf71572cc67e4842`. The review was read-only and the
candidate worktree remained clean.

## Closeout evidence

All four former blocking findings are closed for the committed artifact and ordinary
reproduction path:

- `tools/build_heldout_morphology_adversarial_report.py:2098-2165` enforces the exact
  6 x 3 Cartesian partition, 18 scored attempts, zero skips, recomputed scientific
  fingerprint, fixed raw-result/sample/validator/reproducer digests, and exact failure
  set. Independent recomputation produced fingerprint
  `84b2f3657b21c9cedd9fe7723b4edf99ac3f7514cf7128aff6c994ff9da253f1`; failures
  are exactly `grid_core` seeds 503, 701, and 907.
- `tools/build_heldout_morphology_adversarial_report.py:2070-2096,2213-2259`
  enforces recursive membership, generated prose, unique manifest paths, hashes, and
  sizes. The pre-review package had 27 files; the manifest bound all 26 non-self files.
  No recursive extras or unfinished markers were present.
- `evidence/heldout_morphology_reproducer.py:48-55,66-113,120-178` accepts explicit
  repository/package paths, verifies source identity, preserves the frozen validator,
  and returns process success for a byte-identical scientific FAIL. Live results were
  `18/18 bytes re-derived; scientific verdict=FAIL; skipped=0`, followed by `6/6 SVG
  authorities` and matching PNG/contact-sheet digests.
- `FAILURE_INVENTORY.json` contains exactly MF-001 through MF-043 with 43 unique
  records. MF-037 through MF-043 preserve the canonical control leakage/population
  mismatch, strict-importer 6/7 rejection, representation dependence, historical
  replay failure, severed river, nonexistent bypass function, and five-control gate
  rejection with source-consistent classifications.

The scientific boundary is correct throughout the report: FAIL 15/18, zero skips,
unresolved grid construct ambiguity, seed-held-out structural morphology only, no
fresh-OSM validation, traffic-functional work incomplete/negative, no traffic
completeness claim, and runtime promotion blocked.

The owner policy is explicit and consistent: this is sole-developer personal research
code; adversarial means skeptical scientific/code review; hashes are reproducibility
and accidental-corruption receipts only. It is not a hostile-operator threat model and
does not claim security or tamper resistance.

PDF QA passed on the pre-closeout candidate. Both copies had SHA-256
`52d5a5b1d65f33970aebbf2216f951243206c1b42c957ee189605eaa9b9dc9ff`, were
byte-identical, and formed a readable 21-page A4 report. Rendered inspection covered all
pages and six maps; extracted text contained every MF identifier, the 15/18 result,
owner policy, traffic boundary, and final gates.

Commands observed by the reviewer:

- package checker with `--allow-review-missing`: exit 0;
- focused pytest: exactly 11 passed and one failed solely because this receipt was not
  yet present;
- Ruff and source-to-candidate `git diff --check`: exit 0;
- portable protocol, validation, and sample checks: exit 0;
- GitHub runs 32564391135 and 32564393072: successful final `ci gate` jobs with the
  source/head tree identity recorded by the package;
- both supplied harness SHA-256 identities: exact match.

## Nonblocking limitations

1. P2: The review parser checks terminal gate prefixes with `startswith`. Deliberately
   placing valid PASS records earlier and malformed contradictory prefix records last
   can fool that parser. This does not affect the exact unique terminal receipt below
   and is hostile/malformed-content hardening outside the controlling threat model.
2. P2: The PNG helper validates signature, chunks, CRCs, IEND, and zlib decompression
   but not decompressed scanline length. A deliberately crafted 66-byte underfilled
   image can pass that helper while ImageMagick rejects it. Such a case requires
   deliberate byte construction and digest rebinding; all seven committed PNGs passed
   full ImageMagick decoding and fixed-digest checks.

P0: 0
P1: 0
P2: 2
VERDICT: PASS
