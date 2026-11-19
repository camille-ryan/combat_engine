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
