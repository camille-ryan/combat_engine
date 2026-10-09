# Finishing the 23 heroic-milestone issues: batch by sweep, not by topic

> The ordered list a `/goal` should follow is
> **`20261009-heroic-work-order.md`**. This file is the reasoning
> behind that order; the other one is the work.

The issues already say *what*. This says **in what order and in what batch**,
because the cost is not the work — it is the verification.

## The one number that decides the whole shape

Six wide sweeps today: audit took **1223, 1426, 1595, 1611, 1731, 1736s** —
mean ~26 minutes, and the `_changed` docstring says that cost has been
measured and cannot be tuned away. Every change under `engine/`, `etl/`,
`chargen/` or `scripts/audit.py` widens the audit to all 23,009 rows.

So the 23 issues cost, worst case, 23 × ~30 min of sweeps = **11½ hours of
waiting**. Batched as below: **5 sweeps, ~2½ hours.** Nothing else in the
plan matters as much as this.

## The split, which is exactly three buckets

```
ETL      339 340 378 379 389 452 456 457 458 459      10   rebuild + re-record
engine   283 364 400 471 474 478 479 480 481 483      10   wide audit
content  449 477                                       2   narrow
programme 468                                          1   the authoring half
```

## Order, and why

### 1. Engine first, in two batches (10 issues, 2 sweeps)

Engine changes need a wide audit and **nothing else** — no rebuild, no
re-record unless a new event enters a fixture's stream. Cheapest per issue.

* **Batch A — the verb families already scoped:** `479`'s leftovers (`480`
  `481`), `483`'s group half, `478`, `474`. All read `Cast`/`Powers`, all
  have their cards read and their row counts measured.
* **Batch B — the engine bugs:** `283` `364` `400` `471`. `364` is 544 rows
  and `283` costs 1.5 rounds, so these move numbers the audit will show.

Do not interleave them with ETL. A rebuild in the middle of an engine batch
forces the audit to re-run for a reason unrelated to the change being made.

### 2. ETL as **one** rebuild (10 issues, 1–2 sweeps)

This is the biggest saving available and the easiest thing to get wrong.
Each of these ten changes `etl/` and so needs `scripts/build.py`, a wide
audit, and a `replay` re-record. Done serially that is ten rebuilds and ten
re-records. Done together it is one.

* **the cross-reference four** — `339` `340` `378` `379`. All four are
  "a name survived where a ref should be", all four touch the same resolver.
  `#339` is already mid-flight (steps 3–5 outstanding: the `cls=` rewrite,
  directory renames, re-record).
* **the five names-only tables** — `452` armour/shields, `456` backgrounds,
  `457` themes, `458` terrain, `459` associates. Each is "the compendium has
  it and nothing extracts it". Independent of one another; same rebuild.
* **`389` is not in this batch.** The disease table is an ETL extraction
  *plus* a new ref prefix in `dsl._SYMBOL` *plus* `c.contract(ref)` *plus* a
  stage track that outlives an encounter. That is the shape of the five in
  milestone 2 — it wants its own session and should be moved there or
  treated as one.

**Re-record discipline, which today proved is not optional.** `replay` went
red on all 7 fixtures from a single new `EffectApplied`, and the
strip-and-compare needed *three* masking passes before the streams proved
identical: the new events, the event indices they shift, and the effect
serials. A bare `record` would have been green either way. Budget for that,
and do it as its own commit.

### 3. Content, which is cheap (2 issues, narrow)

`477` is three copies of one mechanism — do it when something else is
already in those two files. `449` is 1,024 monster rows whose declared
recharge disagrees with the card; it is a sweep of its own and the
measurement already exists.

### 4. `#468` last, and on its own clock

2,073 unfinished rows. This is the authoring half and a content wave is
~50% of a week's token budget, so it is scheduled, never opportunistic.
Everything in batches 1–3 reduces its size first.

## Two taxes measured today that belong in any estimate

**Splitting.** Of four verb families read this session, **three were not one
mechanism**:

| symbol | rows | mechanisms found |
|---|---:|---|
| `c.in_form()` | 43 | 2 |
| `c.pre_empt(ref, clause)` | 30 | 5 |
| `c.draw()` | 20 | 4 — one of them an entire Fortune Card deck |
| `c.reroll_ones()` | 14 | 1 |

So a row count on a symbol is an **upper bound**, and it reads high in
exactly the direction that makes a family look worth doing. Read the cards
before trusting it.

**Re-pointing.** Of 107 rows across those four families, **46 stayed with
the symbol they were marked with**. `todo.py` goes red the moment a named
symbol exists, so every row carrying it must be settled in the same commit
— written, or re-pointed at the gap that actually remains. On `#479` that
was 7 rows written against 21 re-pointed. Budget the second number; it was
larger than the first both times and was not planned for either time.

## What would make this cheaper and is not in the milestone

* **`#466`** — `check.py` reports "12 instruments clean" when audit checked
  zero rows. Every batch above is verified by that summary.
* **`#475`** — `browser` flakes 1 run in 3, so a red sweep has to be re-run
  to be believed.
* **`#476`** — the leak gate waives common words in text the page renders.

None blocks a heroic row, which is why they are out of the milestone. All
three make the 5 sweeps above more trustworthy, and `#466` especially: a
batch plan is only as good as the one line that says it passed.

## Settled: `#453` and `#454` have their own milestone

Camille's call — **"Story engine imports"**, milestone 6. Rituals (360
pages, 20 spec rows cite one) and deities (134 pages, 18 spec rows name
one). So the ETL batch above stays at 10 and neither of these joins it.

Scoped to the **imports** and not to the component: `docs/STORY_ENGINE.md`
is a charter and its first line is "nothing is built". Reflavouring, the
adventuring day (`GET/POST /api/day` is a deliberate `501`) and
`ENCOUNTERS.md`'s five archetypes are unwritten *code* rather than unread
pages, and want a milestone of their own if they get one.

`#389` is the one that could sit in either. A disease has a stage track
that outlives an encounter, which is the adventuring day's territory and is
why it carries the `story` label — but it blocks 45 heroic monster rows, and
milestone 1 is the one that has to answer "is heroic done". Left in heroic
for that reason, cross-referenced from milestone 6, and one command moves it
if the mechanism matters more than what it blocks.

## Milestone state after this

```
1  Heroic tier fully imported   23 open    the 5-sweep plan above
4  Paragon tier imported         1 open    #484, the shared tier filter
5  Epic tier imported            0 open    rows only; gated on 4
6  Story engine imports          2 open    #453 #454
```
