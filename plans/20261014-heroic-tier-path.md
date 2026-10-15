# The path to heroic tier working and correct

Measured 2026-10-14 at `89ab0aa`, not estimated.

## Where it actually stands

```
heroic-tier blocked rows (level 0-10)   1,242
distinct symbols they wait on             743
  of those, wanted by exactly one row     500
```

**70% of it is one component.** 868 of the 1,242 rows wait on a `Cast` verb,
across 549 distinct verbs. Everything else is a rounding error by comparison:
chargen 52 rows, ETL 50, `query` 48, the spec brief 34, a real source gap 22.

So "heroic tier working" is, mechanically, a question about the engine verb
surface and almost nothing else.

## The part that changes the order: a third of it may not need building

`scripts/fixtures/triage.json` already holds verdicts for 883 symbols. Cross
them against the verbs heroic rows are *still* waiting on:

| verdict | symbols | heroic rows | what it means |
|---|---:|---:|---|
| `real` | 379 | 573 | genuinely needs building |
| `probable` | 145 | 229 | likely exists, needs confirming |
| `NOT TRIAGED` | 116 | 291 | unknown |
| `mis-marked` | 103 | **191** | **already exists — re-point only** |

**191 rows are waiting on 103 symbols somebody has already judged to
exist.** The verdict is recorded and the re-point was never applied to these.
Another 229 sit on `probable`, and at the repo's own measured rate another
20–30% of the 116 untriaged will collapse too (~60–90 rows).

Call it **~420 of 1,242 rows (34%) plausibly unblocked without writing any
new engine code.**

Two honest qualifications:

* `probable` is not `exists`. `scripts/CLAUDE.md` records that triage's
  top-ranked candidate was **wrong seven times in ten**, which is why it is a
  ranker and not a gate. Each one needs confirming.
* The 20–30% figure is the repo's unbiased calibration, deliberately measured
  on symbols chosen by row count rather than by looking tractable. It is the
  number to plan on, not the 7-in-14 a hand-reading suggested.

**Why this is cheaper now than when those verdicts were taken.**
`docs/symbols/<category>.md` plus `vocab.py --find` turns "does this exist"
from grep-and-guess into seconds. Today's worked example: #581 recorded
`f6s0` as needing a *moment* that "nothing announces". It needed one line on
an existing verb, and the category files showed that inside a minute.

## The thing no amount of content work fixes

**#597: every character of five classes is dealt two or three different
builds' class features.** 24 of 24 sampled wizards hold more than one family.
Cause is one line — `loadout` selects on `p.cls` and the build family lives
in the ref, unread.

This matters for *this goal specifically*: heroic content can reach 100%
implemented and a wizard still fields the wrong sheet. It is the only open
item where **not** doing it makes already-finished rows incorrect in play,
and it gets worse with every build implemented. It may want #235 first
(`BUILDS` legs are not named for build families); the interim — one family
per character, picked with the leg's rng — is cheap and makes a sheet
self-consistent before the legs are right.

## Recommended order

1. **#597.** Small, bounded, and it decides whether finished work is correct.
   Needs one decision from Camille: interim fix now, or sequence behind #235.
2. **Apply the 103 `mis-marked` → 191 rows.** No new engine code, verdicts
   already recorded, content-only so `audit --changed` stays narrow.
3. **Confirm the 145 `probable` → up to 229 rows.** Same shape, one
   confirmation each against the category files.
4. **Triage the 116 untriaged → ~60–90 more rows.**
5. **Build, densest symbol first.** 379 real symbols over 573 rows; the top
   20 symbols alone are ~190 rows. Batch engine changes — one wide sweep per
   batch, never per commit.
6. **The 500 singletons last.** 40% of the rows and one decision each; this
   is where the token budget goes, and it is agent work partitioned by file.

Steps 2–4 are ~420 rows at almost no engine risk and no wide sweeps. Step 5
is where cost explodes, because every engine change widens `audit --changed`
to the whole tree.

## Deliberately not in this path

* **#467** — nothing verifies what the page renders with the localisation
  absent. That is the tier-1 leak gap and the root `CLAUDE.md` calls it the
  one worth building an instrument for. It is a *legal* risk, not a
  correctness-of-heroic-content one, so it does not belong in this ordering —
  but it should not wait on this goal finishing either.
* **#596** — `audited.json` does not reconcile; 178 rows in an unnamed
  bucket. Affects trust in the measurement, not the content.
* Paragon and epic rows. 1,339 blocked tree-wide against 1,242 heroic, so
  heroic is 93% of the debt and the tier filter buys little.
