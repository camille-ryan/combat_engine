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

### Progress, 2026-10-11

```
closed    #512  c.leash, 6 rows written, 9 re-pointed
          #515  c.expose + exposed/contracted split, 15 rows
          #504  landed, not closed -- 4 rows need two further causes
filed     #511  the beast's independent mode (8 feats)
          #513  c.walk_toward, a compulsion (2 rows)
          #514  the nightly sweep is NOT INSTALLED
          #515  the exposure split
blocked   1950 -> 1893
drivers    289 -> 463 printed rules
sweeps    2 wide, both clean; silent refs held at 199 throughout
```

**#514 is the one to read first.** The cadence rule in the root `CLAUDE.md`
tells a session it may keep per-commit runs narrow *because the nightly pays
the wide sweep*. There is no nightly: nothing in any `LaunchAgents`
directory and `launchctl` has never heard of the label.
`logs/nightly-latest.log` is a manual run from Oct 8. So that sentence has
been quietly false, and `logs/NIGHTLY-FAILED` being absent reads identically
to "the last run was green" when the truth is "nothing ran". Not installed
by me -- it schedules an unattended job on Camille's machine.

### The leash family: 14 rows, and 8 of them were a different gap

The clearest case yet of the marker naming the wrong thing, and the first
where the symbol was **too small** rather than already-present:

```
         rows   finished by the verb   re-pointed   source has no page for it
c.leash()  14                      5            9                         1
```

Eight of the fourteen are ranger beast-companion feats sharing one helper.
Their printed clause is *conditional on the beast acting independently* —
a mode that does not exist, and whose absence `c.leash` does nothing about.
The tether is half of one sentence of a much larger gap (#511), and the
other half waives a default — "need not move adjacent to you" — that is
**not in the compendium at all**: every rules-bearing table returns only
the eight feat cards.

The remaining six split three ways, and only one way was a leash:

| | rows | |
|---|---|---|
| tether | `i2854p1` `m3556a2` `m3557a2` `m5481a0` `m5482a0` | written |
| compulsion — *toward*, opposite sign | `m5452a3` `m6484a3` | #513 |
| per-turn anchor, re-measured each turn | `m5941a1` | 1 row, noted |

`c.tether()` (2 rows) and `query.leash()` (1 row) were the same gap under two
other names, which is the fifth time this session a facility was looked for
under a name it did not have.

**What reading the cards bought, beyond the rows:** `f1708` was marked
`todo` on the grounds that *"nothing keeps a familiar within any distance of
its owner, so there is no limit for twenty squares to be added to."* The
limit is printed — 20 squares, in the compendium's `Glossary` — so the feat's
radius is 40 and the row is now written. The row had been re-aimed once
already on the same false premise.

### The disease family: one marker, three gaps underneath it

Nineteen rows carried `etl.monster.inline_disease()`. The symbol named a real
ETL fault and the rows needed **three** things, of which it was one:

```
 19  rows marked
 15  written       -- after the ETL fix AND a new engine verb
  4  still marked  -- two further causes, neither this
```

1. **The ETL ordering** (#504). `_monsters` runs at `build.py:650`,
   `_diseases` at `:665`, so no `x5_` ref existed when a monster was
   scrubbed. Fixed by handing the monster pass the disease names; `scrub`'s
   longest-first rule then did work it was already written for.
2. **An end-of-encounter saving throw, and `exposed` vs `contracted`**
   (#515). Every card prints a throw when the fight ends, and `c.exposed`
   read `Afflictions.contracted` -- so the model had one state where the
   cards have two.
3. **Position**, for the four that are left: `m4362`'s three rows print a
   creature and its disease with the same name, and `m3273a2`'s disease has
   no page at all.

**What the marker could not say.** `todo=`/`dropped=` name a symbol, and a
row wanting three unrelated things can only name one of them convincingly.
All 19 docstrings had been *corrected once already* -- each carried a
"**Correction:** the contraction mechanism exists" paragraph, right about
#389 and still wrong about what remained. A second reading found the third
gap, and `m6619a2`'s docstring had a **guessed ref** in it (`x5_34` where
the card says `x5_93`), which nothing could catch while no row called the
verb.

**Two rows were wrong rather than unfinished**, and only reading the cards
found it: `m6112a1` scoped its save penalty to nothing, so it helped targets
shake off dazes they should have kept, and read "if this attack bloodies the
target" as the state instead of the crossing.

**And the leak the family was hiding.** Four printed disease names were
sitting in two monster specs, with `leaks.py` green over them on a full
sweep. Three closed with the index; the fourth needed `_unglue`, because
`m5100a2`'s list came out as `Blinding sickness3.` and `\b` finds no
boundary between a letter and a digit. Noted on #494 as a **fifth** class of
gate miss -- and the first where the name was registered, plainly spelled,
and in a covered column. The gate simply did not report it.

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
