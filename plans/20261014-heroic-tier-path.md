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

> **Revised after the first symbol, 2026-10-14 (`6dfe37c`).** That estimate
> is too high and the correction belongs here rather than in a commit nobody
> re-reads. `c.reach_of(power=)` was `mis-marked` with 6 rows behind it and
> yielded **1**: the symbol named no verb at all, its recorded replacement
> was the *writer* where the rows needed a reader, and the six wanted three
> different facilities. Five were re-marked to their real gaps rather than
> written.
>
> So treat the per-symbol row count as an **upper bound on rows, not a
> forecast**. A `mis-marked` verdict says "this symbol is wrong", which is
> not the same as "these rows can be written". If the 1-of-6 rate holds the
> pass is worth tens of rows rather than hundreds.
>
> It is still the right first step, for three reasons that survive the
> revision: it is cheap, it replaces markers that can **never** go green
> with ones that can, and it is how `p9501`'s live bug surfaced — a ring
> that had always included the creature it was centred on, so the row
> re-attacked whatever it had just missed. That bug was invisible to every
> sweep and only showed up because a driver would not go green.

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

---

# What the session actually did, measured

Appended 2026-10-14 at `2177bda`. Every number here was read off the tree,
not predicted — see the correction at the end for why that distinction
earned its place.

    heroic rows blocked   1242 -> 1223

## The plan's premise was right and its arithmetic was wrong

Step 2 of the order above estimated 191 rows behind the 103 `mis-marked`
symbols. The order held up: re-pointing first *was* cheap and *was* how the
real faults surfaced. The row count did not. Of the symbols opened, the
pattern was consistent and not what the plan expected:

* **a `mis-marked` verdict reliably means the symbol is wrong and
  unreliably means the rows are writable.** `c.reach_of(power=)` had six
  rows and bought one; it named no verb at all, and its recorded
  replacement was the *writer* where the rows needed a reader.
* **the already-written row of a twin pair was the wrong one, seven times.**
  `settle`'s two unmarked callers, `m5625a0` and `m5626a1` and `m6406a1`
  deciding a card needed no code, `m190a4`'s dead terrain label,
  `m4382a3`'s missing `share=True`, `m5857a0` calling a combat rule
  `out_of_combat`.

So the count moves slowly in both directions, and **up is often the honest
direction**: a row that stops lying about itself raises it.

## What the fan-out bought, which the plan did not anticipate

Four authoring agents over 89 rows in eight disjoint files wrote **20 rows**
— more than the main session managed alone — and found bugs in rows that
reported finished, which no instrument looks for because firing and doing
something is all `audit` asks:

* `m1522a1` dealt 2d6+5 to **its own allies**, at will, every turn;
* `_worsen` capped five rust penalties at **-1 instead of -5**, for four
  rows' entire lives — the second instance of a class
  `drivers.penalties_by_source` was built for and whose docstring predicted
  the recurrence;
* three rows printed "fly speed N (hover)" and granted **no fly speed**;
* `m6654a1` let everybody walk through it instead of the reverse;
* four feats required a weapon by naming a **monster power** that shares its
  printed name.

The lesson for the next fan-out: partition by file, verify every claim that
changes behaviour (agents over-call "already exists" by ~20%), and ask
explicitly for pre-existing bugs — that last clause is what produced the
list above.

## Two instruments came out of it

* **`scripts/twins.py`** — blocked rows whose card nearly matches a written
  one. 44 heroic rows have a twin at >= 0.95, 41 of them identical. It is
  the search the symbol queue is not sorted by, and it found three of the
  four clusters worth having. Not a gate, for `triage.py`'s reasons.
* **`docs/symbols/`** plus its staleness gate, from the earlier plan.

## The correction worth keeping

`b363c8c`'s message says the count went 1221 -> 1222. It went to **1223** —
that commit added two markers and I counted one. The number in the message
was a *prediction written in the same breath as the change*, not a reading
taken after it, and the two diverged immediately.

Found by comparing the marked set at that commit against the tree in a
throwaway worktree, which took a minute and should have been the habit from
the first commit. `audit.py`'s own baseline exists because counts drift
silently; a hand-written count in prose has no such protection.

---

# The second session, and what the ETL route bought

Appended 2026-10-14 at `5d498f0`. Read the correction at the end of the
previous section first: every number below was taken off the tree after the
change, not written in the same breath as it.

## Step 5 of the recommended order was not where the value was

The order above put "build, densest symbol first" fifth and the ETL at 50
rows — a rounding error beside the 868 waiting on a `Cast` verb. That
reading was right about the counts and wrong about the **kind** of row an
ETL gap holds up.

`etl.item.inline_block()` had 13 rows behind it, which by the plan's own
arithmetic is nothing. Opening it found **four live bugs in rows that
reported finished**, which is a higher yield per row than any verb family
this session has opened:

* **`i1663p1` summoned `m324` and had for its whole life.** The item's own
  entry prints a reduced block — HP 13 against `m324`'s 82 — so the row put
  a level-7 soldier with **six times the printed hit points** on the board,
  with a mark rider the card does not grant. Found by comparing the two
  blocks, not by any instrument.
* **`i1663p2` could not fire either way**: it searched for `m324` and
  filtered `c.expended` to `Usage.RECHARGE` where the block prints
  "encounter".
* **`i3263p1`'s docstring had its card backwards.** It said a summon has no
  initiative slot; the card says the creature "takes its turn on your
  initiative count".
* **`p14193`'s marker named an item gap on a theme row**, and its stated
  reason — "that block has no ref of its own" — was false. `p14193b` exists
  and has for 154 powers' worth of precedent; it simply had no content row.
  Writing it then exposed a fifth: `p14193` laid its form with a `label`
  and no `name=`, so `query.in_form` could not see it at all. The #477
  state, two years of commits later.

**The lesson for the remaining order**: a symbol's row count predicts how
many markers come off, and predicts nothing about how many *wrong* rows are
sitting beside them. The ETL groups are small and dense in both.

## A reader that is right in one place and a trap in another

`query.in_form` is **permissive when nothing has been recorded**, documented
and reasoned: a monster that has not changed shape is in whatever shape it
was found in, its block does not say which, so a Requirement must not rule
an attack out.

`p14193b`'s first draft used it as its `requires=` gate and the gate
answered **yes before the form had ever been taken** — a character starts
humanoid, always. `audit` reported the row fine, because the harness waives
a Requirement to exercise a row.

The fix is to ask the answerable question: does a hold that row laid still
stand. The distinction is pinned in `drivers.forms` rather than only in the
content file, because the mistake is available to all 58 rows printing a
shape Requirement.

## Three measurements worth keeping

* **The inline-block threshold is not a guess.** Over every second-or-later
  `<h1>` tail in the heroic range: 2× 0/5 marks, 53× 1/5, 15× 2/5,
  **nothing at 3/5**, then 10× 4/5 and 2× 5/5. Four marks has a two-mark
  margin on both sides. The issue's own first comment said eleven blocks;
  it is twelve, and that comment was a sample read rather than a sweep.
* **`_read_nothing` in one of two callers reports nothing.** Moving it into
  the extracted `_write_monster` found `m509c0` on the first run — a block
  whose every number is an expression in its conjurer's, which
  `loader.spawn` would field with 1 hit point and AC 0. #603.
* **A verb with no caller still needs both controls.** `c.summon(after=)`
  has zero callers until the content lands, so `audit --calls` is 0 rows and
  the driver is the only evidence. Its positive assertion passes by luck one
  time in twenty — `join` rolls a d20 — so `rng.loaded` fixes the die and
  the negative control carries the claim.

---

# The overnight session, 2026-10-15

Sixteen commits from `3bc12d5` to `a9cb878`, certified by one wide sweep:
**all 20 instruments clean at `f4d86c2`**. Heroic blocked rows 1,318 →
1,314, which is the least interesting number here.

## What the session was actually worth

The plan above put "build, densest symbol first" fifth and the ETL at 50
rows — a rounding error. That ordering was right about the counts and
wrong about the **kind** of thing a small symbol holds up. Opening three
of them turned up **nine faults in rows and instruments that reported
clean**:

| | |
|---|---|
| `i1663p1` summoned `m324` — **six times the printed hit points** (82 against 13) plus a rider the card does not grant | content |
| `i1663p2` searched for the wrong ref *and* filtered the wrong usage; it could not fire either way | content |
| `i3263p1`'s docstring had its card backwards: it said a summon takes no turn, the card says it takes one on your count | content |
| `p14193`'s marker named an *item* gap on a *theme* row, and its stated reason was false — `p14193b` existed with no content row | content |
| `p14193` laid its form with `label` and no `name=`, so `query.in_form` could never see it — the #477 state, still in the tree | content |
| `m6481a7` tracked its form in a **module-level `set[int]`** that outlives the world, so a creature drawing the same id later began winged with no fly speed | content |
| six ref patterns in `scripts/` could not match `m<id>c<n>a<n>`, so `audit` graded 23 rows **on a fighter** and `cards.py` refused them outright | instruments |
| `audit` called a sibling of a defective row *silent* when it is *refused* | instruments |
| the nightly skipped with **nothing running**: `pgrep -f "scripts/check\.py"` matched a shell that merely mentioned the path | instruments |

The last three are the ones to take forward. **Three of this session's
nine findings were in the instruments, not the content** — and each had
been quietly wrong for as long as the thing it measures existed.

## Four things I got wrong, and how each was caught

Worth more than the fixes, because the catching is repeatable and the
mistakes are the kind that recur.

1. **A green verdict from a blind instrument.** `audit` said *21 of 21
   rows fire and do something* before and after the regex fix. The
   sentence did not move, which is exactly why it was worth nothing
   before: it was grading a fighter. Caught because an authoring agent
   read the regex rather than the verdict.

2. **A probe that waits for the outcome it is testing for.** The first
   `printed_regeneration` driver advanced the clock "until hit points
   move" and reported the engine broken. Hit points always move — one
   round later, because the clause suppresses exactly one tick. Rewritten
   to read per own-turn.

3. **A convention inferred from one directory.** Two commit messages
   assert that `AT_WILL` is the convention for a NONE-action trait
   "without exception". **2,326 rows** use `ENCOUNTER`. Corrected in
   `content/CLAUDE.md`, where a reader will find it, rather than only in a
   commit nobody re-reads.

4. **A probe that missed a duplicate.** Chains written into `p992` for
   `f3188`, `f2356` and `f2714` all passed — because the probe put the
   feat in `Powers.known` without *arming* it, so the feat's own rider
   never ran. All three are already written as riders, so the chains paid
   every clause twice; `f2714` would have given a critical on 18-20.
   Reverted before committing.

And one plant that **stayed green**, which is a finding too: I had claimed
`blocks_entry` must be asked before the `overhead or ghost` waivers.
Moving it after left the driver green, correctly, because both branches
return independently. The comment now says the order is a style choice.

## The verdict on markers, sharpened

The earlier appendix said a `mis-marked` verdict reliably means the symbol
is wrong and unreliably means the rows are writable. Three more cases, and
the pattern is narrower than that:

* **`c.blocks_entry()`** — real, 8 rows, all 8 written. The clause is
  *entirely about the waivers*: an occupied square is already closed, so
  a row written as `pass` would have audited identically. `m5625a0` had a
  hand-written `KNOWN_SILENT` excuse arguing exactly that, and it was
  wrong — collision does not cover a phasing enemy.
* **`c.lose_mode()`** — real, 5 rows, 2 finished and 3 left with one
  honest clause each. One of the five was *mis-marked in the opposite
  direction*: it wanted `c.mode`, which exists.
* **`c.forgo_damage()`** — **not a verb at all**, and one symbol over two
  gaps. Split 3/3 (#606), and reading the four adjacent `forgo` symbols
  showed **8 of 10 rows in that family name a specific power** and are
  #550 work with nothing missing.

So: before building a verb for a dense symbol, read every card it carries
*and* the symbols next to it. Two of the three I opened did not want a
verb.

## Still owed

* **#607** blocks `f993`'s clause: `doctrine.benefits`' `heals()`
  shortcut skips the no-attack-line guard, so **274 attack rows read as
  support**. The content is written and driven; it is reverted because
  landing it means re-recording four fixtures for the wrong reason.
* **#605** `PowerRecharged` on both paths — `m1032a1` and `m6180a3` want
  it, and it costs a 7-fixture re-record, so it is its own commit.
* **#603** `m509c0` belongs in the associate table, not `monster`.
* **#602** needs nothing further for play; a reader for the stored
  suppression outside `_lay_regeneration` is the open half.
