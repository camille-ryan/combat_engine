# Completing milestone 1: the ordered list

`/goal complete the heroic milestone`. Camille's call, 2026-10-10: **#468
stays in the milestone**, so the milestone closes when ~1,815 heroic rows are
finished. That is weeks, and it is accepted. This file is the order.

`20261009-heroic-work-order.md` was the four-phase plan and is done. This
supersedes it.

## The one number that sets the shape

```
1815  marked rows at heroic levels 1-10      <- #468
 185  paragon 11-20   (out of this milestone's scope by tier)
  18  no level declared (items, feats, features)
```

**#468 is the milestone.** Every other open issue together is a fraction of
it. So the order below is not "smallest first" — it is **whatever raises row
throughput**, because throughput is the only thing that finishes #468.

## Order

### 1. Unblock the largest groups first

A group of 47 rows blocked on one missing thing is worth more than 47
scattered singles, because the singles each cost a card read.

| | rows | what it needs |
|---|---:|---|
| `#389` | 47 | the disease table, a ref prefix, `c.contract`, a stage track that outlives a fight. **Camille approved the plan 2026-10-09.** Probe recorded on the issue: the stage track is uniform across all 69 pages, the DC is **four** shapes and 8 pages need a DC-by-level table this engine lacks |
| `#489` | 10 | a recharge condition that is a **state**, not a moment — a predicate re-asked at the start of the turn, beside the d6 |
| `#471` | ~90 | part-landed; the scope bucket |
| `#364` | 544 | `candidates()` puts the caster in its own ally list. **Flipping the one line breaks 156 rows that are correct only because of the bug.** Classification exists in `tmp/ally364.json` |

`#364` is the biggest single number in the milestone after #468 and is a
*correctness* fix, not an unblock — it does not reduce the marked count. Do it
for the 544 rows' sake, not for throughput.

## Camille's adjustment, 2026-10-10

> *"Leak gate things can't continue to be 30+% of dev time. I don't
> understand why we aren't just, when ingesting a new row, checking to make
> sure that the code used localization."*

She is right and it is measured in **#494**. `leaks.py` is a blocklist search
over free text, and every hole it has ever had is a consequence of that shape
rather than a bug in the matcher — hyphens (578 names, #336), non-ASCII
letters (332), punctuation (247, #493), whole unregistered tables (#492).
Four, each found by accident.

```
27,089  scrubbed specs scanned
 2,256  distinct capitalised multi-word phrases surviving
    77  are in names.json   <- all today's gate can ever evaluate
 2,179  are NOT               <- outside its reach, forever
```

So: **no further matcher work on `leaks.py`.** #476 is parked pending #494's
decision. The replacement is an allowlist on the shape of the output — a
scrubbed spec may hold only known rules vocabulary and `x_<ref>` tokens —
which cannot be defeated by spelling and costs a converging one-time
curation instead of an unbounded series of holes.

Fix a leak when it is found. Do not generalise the finding into another pass.

### Progress, 2026-10-10

```
closed    #389  the disease table, c.contract, 38 rows written
          #487  c.forbid by keyword, 7 rows
          #477  the shape fold, 105 rows          (earlier today)
          #449  1,024 recharge thresholds         (earlier today)
          #378 #379  the ETL resolvers            (earlier today)
landed    #452  armour: 408 rows, 4 kinds
          #459  associate: 88 blocks, 2 defence shapes
          #489  recharge_while, 10 rows
          #492  three tables added to the leak gate's specs walk
          #495  c.boost_roll, 8 rows written, 10 re-pointed
          #496  the Rerolled family, 13 rows written, 5 re-pointed
filed     #485 #486 #488 #490 #493 #494 #497
blocked   2051 -> 1950
```

### The roll family, and what it cost per row

Two issues, 36 marked rows between them, and the split is the lesson:

```
         rows   written   re-pointed   already done   wanted something else
#495       18         8            -              2                      8
#496       18        13            -              -                      5
```

**Half of #495's rows were not blocked on #495.** Six were the artificer
banked-charge family, waiting on `events.ShortRested` first; two were
finished and carrying a stale marker. Of #496's, five wanted a different
mechanism once the cards were read.

So the per-row cost of a marked family is not the engine work. It is reading
36 cards to find which 21 of them the verb actually finishes.

**The marker named the wrong gap three times in one day**, and #489 is the
clearest case: of its ten rows, **five had their predicate already written
and wired to `requires=`** — a usability gate, which refuses the power while
the condition holds and is a sentence no card prints — and **two were
finished outright**. Three of ten genuinely wanted the new field.

The wrong wiring was invisible because nothing ever put the row back, so the
row was once-per-encounter either way and read as "waiting on the engine".
Re-reading the cards is cheaper than trusting the symbol, every time.

**The probe-before-parse discipline paid three times in a row**, and each
time the count that looked right was the one hiding the fault:

* `disease` — the first parser matched **nothing on all 69 pages** because
  `PlainTxt` is line-structured and the probe had flattened `Txt`'s tags. 69
  rows written, every field empty.
* `armour` — a substring test for "Armor" called a *base* an enchantment,
  because `Cloth Armor` carries the word in its **name**. The counts were
  right by accident.
* `associate` — `^Defenses` lost all 12 elemental companions, which print it
  on the same line as `HP`; they came back as "neither", which reads like
  data. And `HP ... Initiative equal to yours` is one line, so 8 hp values
  swallowed the initiative while all 88 reported populated.

So: **check field populations against a prediction, not the row count.**

And one asymmetry worth keeping: `armour` has **no slug column**.
`weapon.slug` is exempt from `leaks.VOCABULARY_COLUMNS` because no weapon is
in `names.json`; all 408 armour rows are, so a slug would hold a printed name
on every one. That is `racial_trait.slug`'s case and #433's answer was to
drop it. `armour.type`/`armour.base` are gated instead — and adding them went
**red on two values**, both read and both coincidences.

### 2. The ETL batch — one rebuild, one sweep

Every one needs `scripts/build.py` and a wide sweep, so they go together.

| | what |
|---|---|
| `#488` | 440 conditional-recharge cards store a die threshold of 6 no card prints. `NULL`, not 6. `m4356a2` prints **both** and is the test case |
| `#340` | the ~50 residue with no positional anchor. Its recommended fix is **refuted** on the issue — do not re-derive that |
| `#452` | armour and shields: 95 bases, 309 enchantments |
| `#456` | backgrounds: 817 rows |
| `#457` | themes, half-ingested |
| `#458` | terrain: 145 pages, and `content/terrain.py` invents its numbers |
| `#459` | `Associate`: 88 stat blocks for summons, mounts, companions |

The five tables are each a parser **plus** a table **plus** a content reader.
They are the largest non-#468 work in the milestone and none is blocked.

### 3. The class migration, now unblocked

`#235` is in this milestone as of 2026-10-10, which was the blocker.

```
#235   re-model the build legs, keyed by their cf: ref
#339   then steps 3-5: the cls= rewrite (9,254 sites), 27 directory
       renames, the re-record
```

In that order. 76 `cf:` refs embed a build name and #235 re-models them, so
#339 first writes the leg work twice over the same headers.

### 4. #468, continuously

Not a phase — the thing the others exist to serve. Run a family per batch,
engine and rows together, and read the cards before trusting a row count.

**The tail is the shape of the work from here.** After the recharge family,
the largest remaining group is `#389`'s 47. Beyond that it is 1,011 symbols
over 2,315 row-wants: small groups and singles, which is slower per row than
a 181-row family. Do not estimate the remainder at today's rate.

### Two issues held open by Camille's own decisions

`#283` — the fix is one line and costs 1.5 rounds at level 5 until `policy/`
can price a weak at-will against a strong one a move away. Its comment names
what to re-run.

`#400` — "keep it open at one row."

**Completing the milestone means these two resolve as well**, and that is a
call rather than a task.

## Rules that apply throughout

Carried from the work order because each was paid for:

* **`check.py --all` once before a push**, not per commit. Seven sweeps in
  the last session; audit is a flat ~1,700-1,800s.
* **Never start a sweep and then edit the tree.** `scripts/build.py` counts as
  editing it — `etl.build` unlinks `game.db` first.
* **A plant that stays green means the check or the code is wrong**, and say
  which. Two plants in the last session failed on the *test's* assumption, not
  the code — that is a finding too.
* **Read every comment on an issue before working it.** `#389`'s premise is
  corrected in its first comment; `#340`'s recommended fix is refuted in its
  last.
* **`audit --calls` is evidence a verb works, never that nothing broke** —
  and it is blind to a gate that starts *passing*, which was proven by plant
  on `#477`.
* **A check comparing two derived values cannot see a fault they share.**
  `recharge_debt.json` held 392 rows it was built to find, because content and
  column agreed on the same wrong number.
