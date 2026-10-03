# AI Policy

What the AI *chooses*, never what the rules allow. A row is legal or it is not —
that is `engine/`. This component decides which legal thing a creature does, and
it may be wrong without anything being broken.

Global rules are in the root `CLAUDE.md`. This file is what is different here.

## Read fights with subagents before touching a weight

**The practice that has actually found improvements**, and Camille's call: for a
policy issue, spawn a handful of subagents, give each a fight log, and ask them to
name the poor tactical decisions. Then measure the ones that recur.

Why it works better than reading the code: a weight is a number in a table and a
mistake is a creature standing in the wrong square on round 4. The table does not
show you that, and the scorecard's aggregates do not either — they tell you the
median moved, not what the fighter should have done instead.

How to run it:

```
uv run scripts/fight.py --seed 7 --level 10 > /tmp/log7.txt
```

* **Three to five agents, one log each**, different seeds and levels. Independent
  readings; do not give one agent five logs.
* Ask for **specific** criticism — round, creature, what it did, what it should
  have done, why. "The AI plays badly" is not actionable; "on round 3 the wizard
  walked into melee to take a flank it cannot use" is.
* **Treat the output as hypotheses, not findings.** An agent reading a log cannot
  see the scores, so it will confidently explain decisions it has guessed at. What
  it is good at is noticing that something looks wrong, which is the expensive half.
* **A criticism that two agents raise independently is worth measuring.** One
  agent's is worth reading and nothing more.
* Then measure. Every number below.

### Two things a log does not say, both of which have cost a day

**A condition that is re-applied every round looks exactly like a stuck one.** There
is no event when an effect refreshes a condition the creature already has, so the
reader sees one `ConditionApplied`, then silence, then `why='encounter over'` at
teardown. A creature dazed for seven straight rounds was filed as a duration bug on
that evidence; it was being re-dazed every round by a free-action burst, and the
`latch` logic was correct throughout. **Count the applications before believing the
duration** -- grep the attacker's hits on that target per round.

**Two different seeds used to be the same encounter.** `story.opposition` drew the
first four monsters by ref, so `--seed` varied the party, the terrain and the dice
and never the opposition. Three agents reading three "different" level-10 logs all
reported the same elite because it was in all three. Fixed -- the seed draws from
every usable monster now -- but the lesson survives: **check who is actually on the
board before generalising from a log**, and prefer several levels to several seeds.

### Three ways a statistic over a log lies, all three paid for in one sitting

A log is grep-able, which makes it easy to produce a confident number that is about
something else. Each of these produced a paradigm comparison that had to be withdrawn:

* **`PowerUsed` is not an attack.** A turn uses several non-attack rows -- stances,
  marks, features that fire on entry -- so counting uses read **138** where
  `AttackDeclared` read **94**. The first number said a party was idle in a fight
  where it was attacking nine times a round.
* **`Dropped` fires for both sides.** Unsplit, enemy deaths are counted as party
  casualties, which is the opposite verdict. **eids 1-4 are the party**; everything
  from 5 up is opposition, including summons and conjurations that take their own
  turns, so a one-enemy board legitimately shows eid 8.
* **A mean over three fights hides the only fight worth reading.** "6.7 party drops"
  for the solo shape was one fight with 18 and two with 0. Print per fight; let the
  outlier be visible rather than averaged into a property of the paradigm.

And the positive version: read the event's **definition** rather than inferring its
fields from one printed line. `Dropped`'s repr omits defaulted fields, which is what
made it look like an event about something other than hit points.

## Two ways a policy term is silently false

Both cost a day each, and neither showed up as a failure anywhere.

**A term can read a key its source does not carry.** `DoctrinePolicy.explain`
filters to `DOCTRINE`, and `policy.features`' keys are a different table — so
`explain()["allies_caught"]` is always absent. A counter built on it read **0 in
every state**, including with the −7.0 deterrent disarmed, and that zero was taken
as "this does not happen". It happens 93 times a run. Read `weighed()` when you
want everything; `explain()` only promises the doctrine half, and says so.

**A term built as a difference of baselines cannot express "avoid this".**
`reach_gained` is `best_from(dest) − best_from(here)`. Anything netted into
`best_from` lowers *both* ends, so lowering `here` inflates every move out of a bad
square rather than only the moves that fix it — it reads as "anywhere but here".
Netting friendly fire in that way made friendly fire **worse** (party blasts
clipping an ally 20 → 25) and was reverted. A penalty belongs where the choice is
made.

## The currency is small, and that is the usual reason a term does nothing

`threat_removed`, `threat_conceded`, `reach_gained` and four others are shares of a
side's threat pool, weighted by `SHARE`. A share is a small number: a blast catching
three enemies is worth about 1.3 after weighting, against `is_power` at 6.0 and
`allies_caught` at −7.0. **Seven terms are derived this way and 51 are hand-set
constants** (#314).

So **a principled term in this currency routinely cannot carry a decision.**
Measured on a differential threat term built for #266 and then reverted: worth
**0.58** where the decision needed about **7**, and swapping it in for the flat
deterrent broke the acceptance test it was built to satisfy. Before building,
estimate the term's weighted size and compare it with what it has to outrank — and
expect that **converting one term at a time makes the AI worse**, because the two
currencies are an order of magnitude apart. That is #314's subject and it is a
whole-table recalibration, not a sequence of substitutions.

## Isolate a term before believing it

Zero the weight and run the same probe. If the verdict does not change, the term is
not what produced it:

```
both terms on          blast -0.67   single +12.68   PASS
differential off       blast -0.09   single +12.68   PASS   <- the flat term did it
flat off               blast +20.33  single +12.68   FAIL
```

That table is the whole argument. A term that passes a test the old behaviour also
passes has been shown nothing.

## What covers a policy change

**`audit.py` covers nothing here** — deliberately. A policy decides among options
the rules already allow, so no row changes and the audit widens to nothing.
`NARROW`'s docstring records that reasoning. What covers it:

```
uv run scripts/scorecard.py        the numbers. --save is its own commit
uv run scripts/replay.py verify    fixtures WILL diverge; see below
uv run scripts/fight.py            one readable fight
```

* **Fixtures diverging is expected and is not the verdict.** Say which divergences
  are tie-breaks and which are repricings: 14% of decisions are already tied at the
  top, so a small term re-breaks ties and a few hundred events of difference is
  what one re-broken tie costs. Re-record in its own commit, never bundled.
* **Report the mixed result as mixed.** Attrition and rounds move in opposite
  directions often enough that picking the flattering pair is easy.
* **Time it against itself, not against a figure you remember.** A term calling
  `T.expected_vs` per target per decision *looked* like it had tripled the
  scorecard's runtime, and had not: 95s with against 104s without, which is inside
  the 15% run-to-run variance `audit._changed` already documents. The apparent
  slowdown was three `fight.py` runs contending for the same cores. Measure both
  arms back to back on an otherwise idle machine or do not claim a cost.

## Attrition is the metric, not win rate

Camille's call on #267: a party beating a standard encounter from full resources is
the **intended** outcome, so a win rate measures the wrong thing. What a fight
costs is **surges, dailies and action points**, and a day is four fights. The
scorecard prints those, plus "dropped to 0 hp" and "with their second wind still
unspent" — the second of which is half of every drop and is the clearest signal in
the file.

Round counts have a target band (#217) and the scorecard's "lower is better"
default disagrees with it, so the two instruments can call the same change good and
bad. #217 is the one with a stated target.
