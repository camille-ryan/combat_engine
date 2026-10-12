# Getting to zero blocked rows

Measured 2026-10-12 at `8569e9c`, straight off `blocked.py`, not off any
issue body.

## Zero is reachable, and it is 1,842 rows away

```
1842  still blocked        <- the target
  45  waiting on the compendium
```

The 45 are reported **separately already** (#467-era work split them out), so
they are not in the 1,842 and never were. Nothing in the 1,842 is permanently
stuck: every row in it names something code can do. That is a better position
than I expected before measuring — the floor is a real zero.

## The shape of it

1,874 queue lines over **1,105 distinct symbols**, 2,064 row-wants (a row can
want two things).

**By who has to fix it:**

```
1387  a Cast verb
 337  an engine type or header field
  90  engine internals (query/turns/dsl/actions)
  78  chargen
  67  spec / brief rendering
  55  an ETL parser
```

**By how many rows share the symbol** — this is the number that decides the
strategy:

| the biggest group a row sits in | rows | cumulative |
|---|---:|---:|
| 10+ rows | 297 | 297 |
| 5–9 rows | 385 | 682 |
| 3–4 rows | 331 | 1013 |
| 2 rows | 273 | 1286 |
| **1 row — its own symbol** | **588** | **1874** |

**861 rows sit in groups of one or two.** That is 46% of the queue needing
roughly its own piece of engine work each.

## The three tranches, cheapest first

### 1. The verb already exists — 491 row-wants, 306 symbols

```
491 row-wants over 306 symbols   VERB EXISTS, a kwarg or a reading is missing
896 row-wants over 424 symbols   verb absent entirely
677 row-wants over 268 symbols   not a Cast verb at all
```

A third of the queue is `c.foo(bar=)` where `c.foo` already has a `def`. The
biggest: `c.zone(exempt=)` 14, `c.recast(reach=)` 12,
`c.extend_move(any_of=)` 11, `c.flat(unpreventable=)` 11,
`c.aura(difficult=)` 9.

Each is a parameter **and a reader** — `lint.py`'s `UNREAD_MODIFIER_KEYS`
exists because a modifier nothing consults is this component's commonest bug,
and I hit that exact failure twice today.

### 2. The dense families — the ≥3 cut, 1,013 rows

What this session did five times over. Rate observed: **~8 rows per family**,
one commit each, including the driver and plants. ~125 commits for the
tranche.

### 3. The tail — 861 rows, ~900 symbols

At 1:1 this is roughly 1–2 rows per piece of engine work. Call it 500+
commits for *less* than the first two tranches combined. **The cost per row
inverts here**, and that is the argument for the ≥3 cut not being arbitrary.

## The lever that changes the arithmetic

**Of fourteen families I examined closely, seven needed no engine work at
all** — the facility already existed under another name:

`c.contract`, `rage.raging()`, `c.extend_move`, `Build.choices`' `race:<ref>`,
`_holding_ref`, `Sheet.per_day`, and today `c.fell_might()`.

Two more were one symbol over three different gaps (`c.lend_augment`), and
one had a marker that had been stale for several commits
(`events.ShortRested`, nine rows).

If that rate holds across 1,105 symbols, **several hundred of them are
mis-marked rather than unbuilt.** Every hour spent on a mis-marked symbol
builds something that already exists.

### Built and calibrated, 2026-10-12

`scripts/triage.py` exists. The calibration ran on the 24 symbols with the
most rows waiting — chosen by row count, not by looking tractable:

```
10 judged    2 mis-marked (19 rows)    1 probable (10)    7 real (97)
```

**20–30% of symbols, not 50%.** The hand-reading's seven-in-fourteen was
biased by picking families that looked workable. Plan on 20–30%, which over
1,105 symbols is still roughly 300–500 rows marked for work already done.

**It must be judged, never believed.** Its top candidate was wrong seven
times in ten — `query.stat_block` for `spec.stat_block()` is a same-name
near-miss across two layers, and that shape will keep recurring. So the pass
is: rank, then read, then record. Verdicts live in `fixtures/triage.json`
and `real` verdicts are worth as much as `mis-marked` ones.

**It paid for itself on the first run:** `c.aura(difficult=)`, 9 rows, was a
parameter `Zones.create` already took and `Zones.aura` did not pass on.
Eight written, one re-pointed to the narrower gap it actually has.

### What the triage is, for the next reader

`scripts/vocab.py --find <words>` already searches docstrings rather than
names, which is exactly the question ("does anything already do this?").
What does not exist is running it over the whole queue.

Proposal — `scripts/triage.py`:

1. for each of the 1,105 symbols, feed its words to `vocab.py --find`;
2. emit a ranked candidate list per symbol;
3. a person or an agent judges each: **mis-marked / real gap / wrong
   granularity**;
4. record the verdict in a fixture so it is judged once, not re-derived.

That turns 1,105 open questions into a ranked list, and every "mis-marked"
verdict is rows closed for the price of re-pointing a marker.

**Measure before committing to it:** run it over the 24 symbols with 10+ rows
first. If it flags a third of them the way the hand-reading did, it pays for
itself immediately. If it flags none, the false-premise rate was a property of
*which* families I happened to pick and the instrument is not worth building.

## What I would do, in order

1. ~~Build and calibrate the triage~~ — **done**, 2026-10-12. Rate is
   20–30%, and the instrument found 9 rows' worth on its first run.
2. **Re-point whatever it finds**, in one pass. Cheap, and it stops later work
   building things twice.
3. **The verb-exists bucket**, largest first. 491 row-wants and the smallest
   engine change per row in the queue.
4. **The ≥3 families**, as this session did them.
5. **Stop and decide about the tail** rather than walking into it. 861 rows at
   1:1 is the bulk of the remaining calendar for the minority of the rows.

## The thing this plan does not cover, and it is bigger

A sampled audit of 20 rows that **report finished** found 2 confirmed faults
and 1 probable — about 10%. Against ~21,000 finished rows that suggests
**~2,000 wrong rows**, which is larger than the entire blocked queue.

`blocked.py` cannot see those: they carry no marker. The machine-checkable
slice is tiny (of 3,599 monster abilities with a parseable target line, 2
disagree — 0.06%), so an instrument will not find them; the faults live in
bodies.

Camille's own suggestion is the only approach measured so far: *"a QA pass and
have agents test out each row, then mark it as clear."* Zero blocked rows and
zero wrong rows are two different programmes, and the second is the larger
one.
