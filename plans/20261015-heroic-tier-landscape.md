# The heroic tier, measured — and why it is a tail, not a batch

Written 2026-10-15 at the end of a long session, so the next one starts from
a number instead of a guess. Supersedes nothing; `20261014-heroic-tier-path.md`
is the previous session's and its appendices still hold.

## The number

```
1,276 unfinished of 23,059 declared  (5.5%)
1,095 of them heroic, across 704 symbols
478 of those symbols are singletons
33 symbols have 5 or more rows; the densest has 9
```

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

1. **#614 `c.reshape_area()` is the best-shaped build left** — 6 heroic rows,
   one real mechanism, and the measurement is already on the issue: one
   funnel line (`dsl.py:1774`), 9 `area_of` callers, ~12 content predicates
   reading `p.reach_of(...).kind`. Needs the design decision first: a
   per-use reshape has to be visible to the header readers, so it probably
   wants a third axis beside `branch=` and `augment=` rather than an effect
   the body lays.
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
