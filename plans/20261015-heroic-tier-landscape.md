# The heroic tier, measured — and why it is a tail, not a batch

Written 2026-10-15 at the end of a long session, so the next one starts from
a number instead of a guess. Supersedes nothing; `20261014-heroic-tier-path.md`
is the previous session's and its appendices still hold.

## The number

```
1,273 unfinished of 23,059 declared  (5.5%)
1,093 of them heroic, across 707 symbols
479 of those symbols are singletons
30 symbols have 5 or more rows; the densest has 9
```

**Heroic now means levels 1-10 and nothing above.** Camille's call,
2026-10-15: a step change at the tier boundary makes level+3 monsters right
*within* heroic and wrong across into paragon, so a heroic fight never fields
a paragon creature. `loader.pick` clamps the band to the tier, and every
paragon row defers wholesale rather than counting as near-term work.

**That shape is the finding.** It is not a handful of blocked families
waiting on a few verbs — it is a tail. Any plan that reads "drain the dense
symbols and the tier is done" is wrong by about two orders of magnitude:
the 33 symbols with 5+ rows cover maybe 200 rows between them.

## What the dense heads actually turned out to be

Four were opened this session by reading every card. **None of the four
wanted what its symbol said**, and that is now the expected outcome rather
than a surprise:

| symbol | rows | verdict |
|---|---|---|
| `compendium.attack_defence` | 28 | **not a gap.** An importer-pasted line. Retired, #612 closed |
| `spec.monster_ref()` | 15 | 9 written; the rest were four unrelated gaps. #609, #610, #611 |
| `c.deals(when=)` | 7 | **four mechanisms**, not one gate. Re-pointed, #613 |
| `c.reshape_area()` | 7 | one real mechanism, but the **header** is what reads it. #614 |
| `c.milestone()` | 6 | needs an adventuring day. Story Engine's. #615 |

So of 63 rows under the five densest symbols: **31 were already finished or
became writable**, 6 are structurally blocked, and the rest are now pointed
at honest names. The hit rate on "the marker was wrong" was far higher than
`triage.py`'s measured 20–30% — because these were the *dense* symbols, and
a wrong symbol attracts rows.

## The rule that paid for itself twice

**A marker may describe the author's reach rather than the tree's gap**, and
only the main session can tell the difference. A content agent may not read
a printed name, so "the creature this card names has no ref" means *it*
could not look one up. One query against `monster` by name resolved six
rows. Saved as a memory.

The same shape, pointed at the compendium: "the extraction lost this
defence" was 28 rows describing text the importer *added*.

## What to do next, in order

1. **#614 `c.reshape_area()` is the best-shaped build left, and the design is
   settled** — 5 heroic rows (not 6; `f3782` subtracts a square rather than
   swapping a shape, and `i526p1` moves a wall, so it is three mechanisms).

   The pattern is `durations.keywords_of`: a `(world, actor, p)` reader that
   every site uses instead of the header field, because a feat altering one
   character's power is exactly what a header cannot say. Its docstring
   carries the trap too — 22 sites, and a grant honoured at 21 is a modifier
   nothing consults at the 22nd.

   **The size looks much worse than it is.** 97 `.reach_of(` sites and 282
   bare `.reach` reads is the scary number and it is misleading: the content
   `kind` readers are overwhelmingly melee tests (27 of ~44), and all five
   area predicates treat area as **one class** — not one separates blast
   from burst, so every one gives the same answer before and after. What
   must consult the override is the funnel (`dsl.py:1774`, 9 `area_of`
   callers), the render path already going through it, and the ranged/provoke
   test at `dsl.py:1331`/`1354` — which legitimately *changes* its answer,
   since a close blast does not provoke the way an area burst does.

   Do **#616** first (the five duplicated area-shape tuples, one of which
   disagrees about `"wall"`), because this change leans on them being one
   thing.
2. **#612's upstream half** — teach the ETL to prefer the damage expression
   *after* a pasted line. Moves all 109 blank-defence lines. **Blocked on
   Camille confirming the `m2085a1` reading** (`1d8+5` over the pasted
   `2d6+5`); if she does not, revert that row and drop the `cards.KNOWN`
   waiver.
3. **`c.on_extra_damage()`, 7 rows** — read but not opened. 6 of the 7 want a
   racial or class extra-damage payout *announced* so a rider can read it,
   which is the "unobservable effects get an event" shape. Additive and
   low-risk; the rows are the bulk of the work, not the event.
4. **Then stop picking by density.** After these, the heads are all 5–9 rows
   and the tail is 478 singletons. The question becomes which *mechanisms*
   are worth having, not which symbols are biggest — and that is Camille's
   call, not a measurement.

## Two standing cautions

* **`types` baselines are stale in at least two files** and only surface when
  an edit brings the file into `_changed()` scope. `scripts/drivers.py` was
  47 against 45, `level_10/controllers_sa.py` 16 against 15 — both at HEAD,
  neither mine. Fixed one real error in each rather than blessing. Expect
  more of this; do not bless.
* **Never `git checkout <file>` to revert a plant.** Done once this session
  and it threw away a rewritten check along with the plant. Copy the file
  aside first. There is a memory about exactly this and I still did it.


## Added at the end of the same session

Four more things landed after the first draft, and two of them reverse things
written above.

* **`compendium.attack_defence` is not a retirement, it is a drop.** Camille:
  *"If an attack says '+X vs. BLANK' it's malformed."* The 26 rows I had
  retired as already-finished are `defect=` instead, 86 rows across 83
  entries, and `etl/build._malformed_attack` writes `monster.defect` so the
  67 entries with no row written are caught too. 150 on the page, 85
  imported, all 85 marked. **The retirement was mine and it was wrong**:
  knowing *why* a line is junk does not make the row writable.
* **#616 landed** — one `AREA_OR_CLOSE` set, and four of the five copies were
  missing `"wall"`.
* **#614 is three mechanisms, not one, and nothing is built.** Two designs
  built and backed out; see the issue and the
  `read-every-card-before-building-a-verb` memory. The split is by *when* the
  alteration lands — standing option, one-shot before use, triggered on a use
  already in flight — and the last of those cannot be a modifier at all,
  because targeting precedes the body.
* **`types.py` was two bugs, not a backlog.** The "48 errors in `content/`"
  figure in an earlier note was an artifact of a subset invocation nothing
  else runs. `shaman.py` really was 201 and is now 0 (a `TypedDict` for its
  `**TRAIT` splat). `--bless` was deleting every baseline entry outside the
  run; fixed. #618.

**One honest note for whoever reads this next.** The last third of this
session produced four self-inflicted errors — a baseline wiped, a count
measured off a filtered report, and two speculative designs built before the
cards were read. All four were caught, none shipped, but the rate was
climbing and that is the signal to stop rather than the thing to push
through. The commits are small and separately verified for that reason.


## The dense head, worked through

Nine of the densest heroic symbols opened by reading **every** card in each.
The result is the useful number: **the mis-marking rate collapses once the
flattened symbols are past.**

| symbol | rows | verdict |
|---|---|---|
| `compendium.attack_defence` | 22 | **dropped** on Camille's ruling; `monster.defect` catches the rest |
| `c.familiar_state()` | 8 | **five** questions; the mode was never missing. #620 |
| `c.on_extra_damage()` | 7 | **three**; the announcement and the die count both exist. #619 |
| `c.deals(when=)` | 7 | **four** mechanisms. #613 |
| `c.reshape_area()` | 7 | **three**; nothing built, two designs backed out. #614 |
| `c.milestone()` | 6 | structural -- needs an adventuring day. #615 |
| `c.race_option()` | 9 | **accurate.** The build choice is recorded nowhere; one gap, right component |
| `chargen.armor_proficiency()` | 9 | **accurate**, and `f3779`'s penalty half was writable and is written |
| `c.beast_independent()` | 8 | **accurate.** `+2` saves written; the independent mode genuinely absent |

**Six were wrong, three were right, and the three right ones are the three
that were never bundled.** Each of those carries a shared constant with a
note explaining the one gap -- `RACE_OPTION`, `PROFICIENCY`, `LEASH` -- and
each row's docstring names what *does* exist beside it. That is what an
accurate marker looks like, and it is distinguishable from a flattened one
before you read the cards: a flattened symbol's rows disagree with each other
about what is missing.

So the heuristic for the next pass: **read the rows' docstrings against each
other first.** If three rows on one symbol give three different reasons, the
symbol is the bug. If they give the same reason and name different adjacent
facilities, the marker is right and the gap is real.

**It does not automate, and I checked.** Built it as a `triage.py
--agreement` mode scoring vocabulary overlap between a symbol's docstrings,
and withdrew it: two of the three symbols confirmed accurate by hand scored
**0.000**, the same as the flattened ones, and the one that scored 0.673 did
so because its eight docstrings come from a single `_leash` helper. The
reason it cannot work is the reason the judgement is worth making — an
accurate symbol's rows each name a *different* adjacent facility, which is
low overlap too. Same failure as the `spec.*`/`etl.*` check withdrawn on
#608 for flagging 69 of 73 rows.

One thing the attempt did surface before it was withdrawn, and it stands on
its own because the cards were read, and it grew when the thread was pulled:

## #614 is 25 heroic rows under five symbols, and that is the finding

**Replace a named power's `Range` for one use, visibly.** Marked five ways,
which is exactly why it never looked dense enough to build:

```
 7 heroic  c.reshape_area()
 5 heroic  c.recast(area=)
 5 heroic  c.recast(as_ranged=)
 5 heroic  c.as_melee(ref=)
 3 heroic  Power.reach_alt
25 heroic rows
```

`c.recast(area=)`'s cards are the issue word for word -- "you can choose to
make it an area burst 2 within 10 squares **instead of** a close blast 3".
And `Power.reach_alt`'s three rows name the fix from the header side, which
is the **fourth** independent arrival at the same design: *"there is no field
for an alternate reach the way `attack_alt`/`damage_alt` carry an alternate
branch"*. `Range.alt` already carries a *numeric* alternative; what is
missing is one of a different **kind**, and `attack_alt`/`damage_alt` are the
shape the header already uses for it. Much smaller than the `Form` axis built
and backed out earlier.

**The five symbols are deliberately not merged** -- they describe different
printed effects, and merging rows that disagree is the fault this session
keeps relearning. Five names, one mechanism, recorded on the issue.

Three of the 25 trigger on `f1028`, which is itself one of the 25, so build
order is not free: `f1028` and `f1239` first, then the riders.

So the next session's answer to "what is worth building" is this, and it is
not close: 25 rows against a head whose next entry is 9.

The head is now 28 symbols at 5+ rows, and the top of it is the accurate
ones. Which means the cheap wins from re-pointing are largely spent, and what
is left is building: `c.race_option()` and the two `chargen.*` nines are a
chargen block (#125 on the task list), and `c.reshape_area()` is #614's three
mechanisms.
