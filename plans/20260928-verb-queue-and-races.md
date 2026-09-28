# The verb queue, and races in play

Two directives from Camille: work the engine issues via the **verb
queue** first, and **flip `DEAL_RACES`** as its own commit.

## Phase 0 — races in play (its own commit, nothing else in it)

`chargen.DEAL_RACES = False`. Races are fully built — 46 dealt-able,
155/155 racial cards written — and no character is ever dealt one.

Its own comment prescribes the procedure: flip the flag and run
`scripts/replay.py record` **in the same commit, on purpose, with
nothing else in it**, because a race is +2 to two abilities, a size, a
speed and traits, so every sheet moves and with it every roll. Six
fixtures diverge at their first attack. That divergence is expected and
is also exactly what a real regression looks like, which is why it may
not share a commit with anything.

Before recording, prove the diff is the races and nothing else:

* every fixture diverges at or after the point a sheet number is read,
  not before;
* `fight.py --quiet` still exits 0;
* `api_smoke` and `browser` still pass;
* no row raises. Racial traits arm at setup, and #204's comment records
  that a level-0 row firing at setup once made every sibling row of that
  race report UNUSED.

Then re-run `audit.py`. #214's comment says the class gate "only pays
once races exist", so the UNUSED count should **fall** here. Record what
it was and what it becomes — that number is the argument for having done
this.

## Phase 1 — the verb queue

`blocked.py --group` is the work list, generated from `todo=`/`dropped=`
symbols, ranked by how many rows asked. Ordered by rows unblocked per
unit of engine change:

| verb | rows | note |
|---|---:|---|
| `c.ability_for(ref)` | 64 | largest single ask in the tree |
| the senses cluster | ~50 | `c.darkvision` 19, `c.low_light` 17, `c.blindsight` 10, `c.tremorsense` — one feature, four verbs |
| `c.instead_of()` | 34 | |
| `c.change_dice()` | 21 | |
| `c.race_option()` | 20 | also `chargen.race_choice()` 13 — same seam |
| `c.attack_ability()` | 19 | likely the same seam as `c.ability_for` |
| `c.on_reroll()` | 18 | |
| `c.draw()` | 19 | |

`spec.power_ref()` (37) and `etl.item.inline_block()` (13) are **ETL**
symbols, not engine verbs — they belong to #221's family and are out of
scope for this phase.

**Per verb, the loop is:**

1. `blocked.py --refs <verb>` yields the refs; the refs are the brief.
2. Read the specs. Decide the signature from what the rows actually
   print, not from the symbol's spelling — #98's re-read found 15 of 21
   wanted verbs already existed under a different name, so **grep
   `cast.py` before building anything**.
3. Build the verb, with a reader. #211's whole tally is modifiers
   nothing consults; a verb with no reader is the signature bug.
4. Sweep the rows that named it. A `todo=` symbol goes red against the
   registry the day the verb lands, which is the point of #179.
5. Verify each swept row by driving it, positive **and** negative
   control — #216 means "fires and does something" is weak for any row
   hanging clauses on a `Hit`.

**Side effect worth tracking:** 37 racial cards carry a marker across 20
races (9 `todo=`, 28 `dropped=`). Most name verbs on this list —
`c.ability_for` twice, `c.darkvision`, `c.blindsight`, `c.race_option`
twice. Finishing the queue finishes the races.

## Not here

* The audit chain (#216 → #204 → #214) and the ETL chain (#221, #218,
  #175). Both were offered and not chosen.
* #213's scorer, #89's policy half, #173, #212, #72's day clock.
* #225, filed this session.

## Gate

`ruff`, `lint.py`, `api_smoke`, `browser`, `replay verify`, `fight
--quiet`. `audit` (869) and `todo` (13.1% against a 10% budget) are the
standing backlog — **the marker budget should fall in this phase**, and
that is the measure of whether it worked.
