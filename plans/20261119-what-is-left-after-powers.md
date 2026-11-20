# What is left after powers

Measured 2026-11-19, after the wide sweep at `c49f5ce2`. Every number here
is counted off `dsl.REGISTRY` or `game.db`, not quoted from an issue.

## The corpus, by category

**Two of these categories were invisible in my first pass because I invented
the buckets.** `x7_` is a **class** value carried by rows whose refs are
`p…` numbers, so *themes were inside the powers count all along* -- they are
not a category here. What I had labelled "themes/terrain" was `x2_`
(**terrain**) and what I had dumped in "other" was `x5_` (**diseases**).
Those two turn out to be the highest-rate categories in the tree, which is
the cost of a bucket nobody checked.

| category | declared | carries a marker | rate |
|---|---|---|---|
| monsters | 13,454 | 233 | 1.7% |
| feats | 2,533 | 205 | 8.1% |
| item blocks | 2,491 | 149 | 6.0% |
| **terrain** (`x2_`) | 24 | **12** | **50%** |
| **diseases** (`x5_`) | 21 | **10** | **48%** |
| class features | 827 | 8 | 1.0% |
| powers | 4,398 | 6 | 0.1% |
| racial traits | 115 | **0** | 0% |

## Powers, class features and races are done, and here is the evidence

**Powers.** 6 markers of 4,398, each parked on an issue carrying a ruling or
a live blocker: `p12162` (#1374 -- recommended to stay marked, 1 row of
23,883), `p13611` (#1388), `p15894` (#1386), `p16059` + `p16539` (#1385,
**ruled, see below**), `p16597` (#1367).

The stronger number is the one nobody was watching. `blocked.py --prose`
finds rows whose own docstring admits a dropped clause while declaring no
marker -- rows that **report finished to every gate**. The earlier plan
recorded it at **356 rows, 201 of them powers**, and said no count of the
powers job was trustworthy because of it. It is now **154 rows, 1 of them a
power**. For powers the marker census and the prose check finally agree.

**Class features: all 8 markers are paragon tier** --
`etl.MAX_ITEM_LEVEL(paragon)` on four assassin features (16/19/22/23) and
`etl.MAX_POWER_LEVEL(paragon)` on four warlock ones (14/17/20/22). The ETL
stops at level 10, so no character this project builds can reach them. They
are unreachable by design, not unfinished.

**Racial traits: zero markers.**

**And the prose column must not be read beside those, which is a mistake I
made and should not be repeated.** `blocked.py --prose` is a keyword scan
over docstrings, and this tree's docstrings *argue*. Of its 6 class-feature
hits, at least 2 are false positives: `cf:paladin-cavalier-f4s1` quotes a
marker it **used to carry** and then refutes it, and `cf:wizard-mage-f6s0`
explains a deliberate design choice -- both matched on words like "not
written" inside sentences saying the opposite. So the scanner is *least*
reliable on the rows with the most careful documentation, and its 154 is not
154 jobs. Sample before costing it.

## The order

### 1. `#1385` -- a ruling is waiting, and it is blocked on nothing

Camille, 2026-11-19:

> *"it's a rules change. declining is forbiden."*

So *"you must make every opportunity attack you can"* is a **kernel**
change, not AI policy, and not out of scope. An `OpportunityWindow` under
the compulsion cannot be declined; it is already a `Decision`, so the
refusal path exists and this narrows who may use it.

**The symbol split is three ways, not the two the issue says** --
`policy.must_take_openings()` (`p16059`), `c.must_take_opportunities()`
(`p16539`), `c.must_take_opportunity()` (`x5_51`). The third was missed
because the census that produced the issue walked power rows and `x5_51` is
a disease.

**One nearby family is a different gap**: `c.must_attack(on=, against=)` on
4 rows plus `c.extra_action(must_attack=)` is *compelled to attack a
particular creature*, not *forbidden to decline an opening*. Folding them
together would repeat the fault #1385 exists to record.

3 rows. Posted and the `question` tag dropped.

### 2. The instrument-accuracy slice, before trusting another census

This is the one part of the backlog worth pulling forward, because every
row verdict rests on it. `#1357` is *"The 26 power rows the audit board
still cannot reach, diagnosed"* -- 26 rows whose green verdict means
nothing, which directly qualifies the "powers are done" claim above.
Siblings: `#1362` (`audit.board` pins `SCORED_CHOICES` for the party and
not the caster), `#1359` (a drivers rule pins 122 and reads 121), `#1363`
(type diagnostics from the last batch).

### 3. Terrain and diseases -- 22 rows, and they actually cluster

Unlike feats, these concentrate:

```
diseases (10)   affliction.tick(...) kwargs     5 rows   dies= x4, no_improve= x2,
                                                         rest_choice=, rest_damage=,
                                                         contagious=, fatal=
                c.must_attack(on=, against=)    3 rows
                story.npc_takeover()            2 rows

terrain (12)    a Zone geometry family          5 rows   path x2, defences, depth,
                                                         breach_hp
                a Check family                  4 rows   Check(ability=), Check(skills=),
                                                         Check.sticks, Power.check_alt
```

Three facilities clear most of the diseases; two clear most of the terrain.
One batch at the agreed cadence.

### 4. Traps -- `#1367`, the last real subsystem

```
printed trap rows in game.db       631
  carrying a save-ends rider       303
declared `t:` rows in content        0
```

Traps are driven generically: `content/terrain.printed_trap` reads the
`trap` table and `lay`/`arm` put one on a board from **three columns**
(printed attack, defence, damage). There is no body, so nothing carries a
rider and all 303 are dropped -- `t:5`'s pit damage lands, its ongoing
poison and its prone do not.

**Nothing counts them**, which is what makes this worse than unfinished. A
trap is not in `dsl.REGISTRY`, so it is absent from `never_refs`,
`silent_refs` **and** `blocked.py` -- all three places this project measures
incompleteness. `cards.py` cannot reach it either.

It is additive (attack and damage already play) and it clears two power
markers: `p16597` directly and `p13611` through `#1388`, the AI half, whose
framework already evaluates damage when moving through squares.

### 5. Feats and items -- triage before building

The raw shape reads as an irreducible tail:

```
feats   205 rows over 172 symbols    86% of symbols block exactly 1 row
items   149 rows over 138 symbols    87% of symbols block exactly 1 row
        the ten biggest symbols cover 16% of row-claims, either way
```

**Do not plan against that.** Camille's own warning, 2026-11-19: *"we
THOUGHT that remaining power rows also had singleton symbols and that ended
up being not the case... assume that we will discover similar results"*.
The power queue went 19 markers to 6 and most of the movement was **stale
markers**, not built facilities -- a need already met under another name
(`c.no_reactions()` never existed; `c.no_immediate` had done the job since
#1285), a marker naming the wrong layer, or a marker invisible to `todo.py`
because `blocked._surface` never indexed `Power` fields.

`triage.py`'s unbiased figure, over the 24 symbols with the most rows
waiting: **20-30% of symbols and 15-23% of rows need no engine work at
all.** On 354 feat+item rows that is 50-80 rows of reading.

So: `--drift` first (883 verdicts and nothing reconciles them; its *"live
and unapplied"* bucket is a queue nothing else surfaces), then triage
largest-first **recording `real` verdicts too**, then build only symbols
that still have more than one row behind them. Read the verb the marker
nearly names before reading the row -- the highest-yield move of the power
round, repeatedly.

## The backlog is residue, not a phase

```
163 open (160 after this sweep's three closes), 1,388 all time
 56  are the row queue -- they name a marked row or a blocked symbol
107  independent of it, overwhelmingly engine and instrument findings
      generated BY row work: #1384 ConditionApplied is not a Decision,
      #1362 audit.board, #1359 a pinned count, #1363 type drift
```

**I recommended a triage sweep earlier in this session and that was wrong.**
It was measured in October and refuted: 67% of closed issues close within
24h (median **6 hours**), nothing open is older than 22 days, and
`issues.py --stale` found **1 real close in 31 candidates**. The open set
survived because it is blocked, large, or waiting on a decision -- not
because it is neglected. The lever is **decisions and throughput**, not
triage: two scope answers once unblocked 532 rows in ten minutes.

The backlog also grows +10/day as a byproduct of working, so "clear it then
do rows" chases a target the row work feeds. A third of it closes on its
own as rows land.

What *is* worth doing, per issue and not as a phase: **check a cited
blocker's state before planning around it** (`gh issue view N --json
state`). That is the narrower check behind `CLAUDE.md`'s 9-of-63 finding,
and it is one command.

## Cadence, which worked and should not change

Camille: *"Instructions on the last bout to only do wide instruments on
every 50 or so rows seemed to work well."*

```
per row     lint.py <file>, audit.py <refs>, a drivers rule WITH A PLANT
per ~50     one check.py --all   (~35 min; commit BEFORE launching it)
never       winrate, scorecard -- AI policy only
```

Two habits earned their keep in the power round:

* **a passing plant is the finding.** Six times a plant passed and the
  fault was a fixture that could not tell two implementations apart. Once
  more in this session: an assertion read a row's *marker* instead of its
  behaviour, so a plant removing the behaviour passed.
* **say whether the code or the check is wrong, with evidence**, before
  touching either. `drivers.grant_armor` pinned a correctly-removed marker;
  the check's definition was the stale thing.

## Not in scope

AI policy weights, `scorecard`, `winrate`. Lifting `etl.MAX_POWER_LEVEL`
(which is what the 8 class-feature markers wait on). `#467`, deferred by
Camille until the first distribution.

---

# Handoff, 2026-11-19 late. Read this first

Written because the session ends here and the next one starts with no
memory of it. Everything below is measured in this session unless it says
otherwise.

## What landed

Five rows, in five commits, each with a `drivers` rule and plants:

| row | what | shape |
|---|---|---|
| `f2823` | teleports instead of shifting | written into `p7443` |
| `f1027` | moves `p3773`'s second helping | written into `p3773` |
| `f3209` | marks on a theme attack | its own body |
| `i553p1` | takes one of five printed shapes | `c.as_weapon(base=)` |
| `i1153p1` | becomes any melee weapon | `c.as_weapon(base=)` |

Plus the facility the last two needed: `combat_engine/weapons.py` (the
printed weapon table, below every component), `components.weapon_from_printed`
(the one mapper), `Cast.as_weapon(base=)`, and a third module on
`.importlinter`'s printed-tables contract. Same `#852` argument as
`armour.py`: the reader existed in `chargen` and `engine -> chargen` is
contractually zero.

**Terrain is finished** -- 24 rows, 0 markers. That was step 3's larger
half.

Two issues filed, both real and neither fixed:

* **`#1397`** -- `build._swap_sub_options` keys its map on the printed
  **name**, so a label claimed by two refs silently keeps one. 15 labels
  are claimed across kinds, 53 specs cite one. This is what made `f3209`
  unwritable for two referrals.
* **`#1398`** -- `types.json` holds `scripts/drivers.py: 0` and the file
  reports **166**. Measured both ways by swapping `HEAD`'s copy in: none
  belong to the change in hand. So `types` reds on every commit that
  touches `drivers.py`, which is most of them.

## Three standing qualifications on "powers are finished"

The claim above -- 6 markers of 4,398 -- still holds as stated. These do
not contradict it and do bound it:

1. **`#1357`: 26 power rows the audit board cannot reach.** Their green
   verdict means nothing, because "it fires and does something" was never
   tested on them. Open, unworked.
2. **30 power rows cite a colliding ref (`#1397`).** Measured:

   ```
   cf:druid-f1s0            p2669 p2790 p5041 p5054 p9652 p9663 p12835 p15858
   cf:sorcerer-f0s3         p3162 p3163 p3782 p5260 p5262 p5264 p5271 p5278 p5279 p5511
   cf:warlord-marshal-f4s2  p1064 p1065 p1076 p2444 p4551 p4564 p4569 p10129
   cf:warlock-f1s4          p12887 p12888 p12891 p12894
   ```

   The three **feat** citations were read: two correct, one (`f3209`)
   wrong. **None of the 30 power rows has been read.** A row written off
   the wrong ref audits green -- it fires, it does something, and it is
   about the wrong thing. Mostly these will be the legitimate case (a
   druid power naming a druid sub-option), so this is a reading job, and
   nothing measures it today.
3. **`blocked.py --prose` is a keyword scan** and this tree's docstrings
   argue. Its 154 is not 154 jobs. Sample before costing it.

## The wide sweep: owed, and the cadence was got wrong

**22 commits since the last full sweep (`d6c7b10bf`).** A `check.py --all`
is owed before any push.

A sweep was launched on **5 rows** in this session and Camille stopped it:

> *"I was expecting something like 50 rows per wide sweep, and if I'm not
> mistaken you've done 5 or so?"*

Correct, and it is this plan's own cadence written two sections up. **~50
rows per wide sweep.** Killed cleanly (`pkill -TERM -f scripts/check.py`
takes the workers with it; the tree was clean and nothing was lost). Do
not launch another until the batch is that size.

What is clean right now, so the next sweep is confirming rather than
discovering: `drivers --tries 40` 8,158 hold / 0 fail, `replay` 8 of 8,
`seams` 7 contracts kept, `ruff`, `lint`, `leaks --cited`, `todo`.

## The queue, re-measured. Do not use the old numbers

```
198 marked feat rows      147 marked item rows      477 symbols
130 row-claims sit in symbols with 2+ feat/item rows
```

Biggest multi-row symbols, measured fresh:

```
6  spec.power_ref()                i1690x1 i2801p1 i694x1 + 3 monsters
4  chargen.multiclass_powers()     f1120 f2697 f2698 f2732
4  c.alignment()                   f1351 i2195p1 i3142x1 i3282p1
4  chargen.retrain_on_rest()       f2441 f2443 f2445 f2446
4  chargen.power_choice()          f3582 f3588 f3616 f3646
4  c.item_set()                    i1492p1 i2176x1 i2358p1 i2777x1
```

**`chargen.multiclass_powers()` is already fully designed in `#1161`** --
`Character.multiclass: str = ""`, on `#1029`'s `race2` precedent, with the
reasoning for why all four rows are one gap. Do not re-derive it. Note
`f2698`/`f2732` need a second thing as well: `power_swap` filters both
halves of a trade through **one** `trade.usage`, and those cards take an
encounter power out and bring an at-will in.

## `triage.json` is stale. Run `--drift` before trusting it

Three verdicts were wrong in one session:

```
dsl.powers_of(cls)         said 2 rows, is 1
chargen.power_swap(pool=)  said 4 rows, is 1
c.place_scenery(kind=)     verdict already self-corrected to STALE
```

883 verdicts and nothing reconciles them. `--drift`'s *"live and
unapplied"* bucket is a queue nothing else surfaces. **This is step 0 of
anything that reads the queue**, and it was skipped in this session.

Verdicts read but not worked: `c.surprise_round()` (`i2656x1` -- the real
residual is that `c.waive` refuses `cannot_act` by design, which wants its
own symbol), `falling.drop(check=)` (`i802x1`, a shape question),
`query.knocked_prone()` (`f3507` -- the verdict concedes
`ConditionApplied` does not say whether an *attack* caused it),
`chargen.power_swap(pool=)` (`f2580`), `c.place_scenery(kind=)` (`f3015b`,
leave alone; the live lead is its other symbol `query.wearer_of()`).

## Diseases: 10 marked, and 4 of the symbols are parked on Camille

```
affliction.tick(dies=)            x5_18 x5_66 x5_81 x5_91
c.must_attack(on=, against=)      x5_18 x5_25 x5_34
story.npc_takeover()              x5_51 x5_93
affliction.tick(no_improve=)      x5_65 x5_91
c.hp_ceiling() c.on_points_spent() c.treats_allies_as_enemies()
story.site_radius() affliction.tick(rest_choice= rest_damage= contagious=)
```

`questions.py`: **4 tagged `question`, all 4 parked on Camille with a
plain-language ask, 0 answered and waiting on us.** So the `dies=` family
and `c.must_attack` are genuinely blocked, not neglected. Check
`questions.py` first -- if any now reads **ANSWERED**, that is the cheapest
work on this page.

## The agent fan-out, which is what the next session is for

Camille, this session:

> *"I think we saw that a number of rows are marked as requiring
> functionality that exists now. I was wondering if agents might be a good
> approach to uncover this for the remaining work"*

Yes, and it is the one job here that parallelises cleanly. The 200-agent
session cap is why the session was cleared.

**Why it is the right job.** The highest-yield move of the power round,
repeatedly, was *read the verb the marker nearly names before reading the
row* -- the power queue went 19 markers to 6 and most of the movement was
stale markers, not built facilities. It happened **four more times in this
session**: `c.reshape_weapon()` was a synonym for `c.as_weapon(base=)`;
`f3209`'s marker named a filter that had existed for months; `i1153p1`'s
marker named two gaps and one was not a gap; `f1027`'s marker argued
correctly for a conclusion it then got wrong.

```
me      triage.py --drift          what is already known, and what is stale
me      partition the remainder BY FILE
agents  N read-only agents, one partition each
          per row: the symbol, a verdict, the evidence, the near-miss name
me      pick the confirmed ones
agents  write them -- one file per agent
me      full drivers, replay re-record, ONE wide sweep at ~50 rows, push
```

**Rules for the agents, each from a real cost in this repo:**

* An agent lints **only its own file** (`lint.py <path>`) and audits only
  its own refs. A tree-wide `ruff --fix` has destroyed another agent's
  work.
* **An agent never touches git.** Merge, sweep, baselines and push have one
  owner.
* **Engine, ETL and instrument work is not delegated.** Verification is
  global, so handing it out buys no parallelism and costs a collision.
* An agent is shown **name beside ref** via `scripts/spec.py` and writes
  only refs.
* **"It exists" from an agent is a candidate, not a verdict.** The
  automated ranker's top candidate was wrong 7 times in 10. Every
  un-marking still owes `audit.py <ref>` and a `drivers` rule with a
  plant.

**Two costs land on the controller and must not be delegated:**

* **Un-refusing a feat re-rolls every chargen draw**, so a wave of
  un-markings owes a `replay` re-record -- a baseline write, its own
  commit, every diff proved an insertion rather than behaviour moving.
* **`drivers` rules pin marker tuples.** `retarget_split` went red in this
  session because it still expected `f1027` to carry a marker that had
  been correctly removed two commits earlier -- the full suite had not run
  in between. A wave will red several of these. The call each time is
  *which is wrong, the code or the check* -- there it was the check, and it
  was corrected to an exact empty tuple rather than relaxed to
  `not unfinished`, so a marker returning under any name still reds.

## One thing to avoid repeating

A plant **passed** in this session and that was the finding, not a pass.
`drivers.weapon_shape` compared `chargen.PRINTED` against
`weapon_from_printed` to show the table move changed no field -- and
`chargen.PRINTED` *is* that mapper's output now, so breaking the mapper
broke both sides identically and the plant went green with 19 of 19
assertions. It compares against `weapons.Printed` column by column
instead: 10 columns over all 117 rows, independent of the mapper, and the
same plant now names 102 rows.
