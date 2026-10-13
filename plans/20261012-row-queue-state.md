# The row queue, measured at the end of 2026-10-12

`blocked.py` at **1,514**, down from 1,666 at the start of the day's row
work and 1,615 before the eight-agent fan-out. Every instrument green
except the wide sweep, which the 02:07 nightly pays.

This file exists because the goal is "work the entire list of rows" and the
arithmetic in `plans/fizzy-humming-walrus.md` is roughly **800 commits**.
What follows is the measured state so the next session starts from numbers
rather than from a re-read.

## Done today, by family

| family | rows | outcome |
|---|---:|---|
| the mis-marked wave | 174 | written, 96 files |
| `c.zone(exempt=)` | 14 | 10 written, 4 re-pointed (two gaps split out, #535) |
| `c.flat(unpreventable=)` | 11 | 7 written, 3 marked honestly, 1 re-pointed |
| `c.ability_check()` | 14 | 5 written, **5 needed no code**, 4 re-pointed |
| `query.shield_bonus()` | 9 | 8 written, 2 re-pointed |
| `Healed.power` | 10 | all 10 written |
| the other three event fields | 21 | 9 written, 12 re-pointed (#538) |
| `c.recast(reach=)` | 10 | re-pointed 5/5 into two gaps (#536) |
| `Target.living` | 7 | re-pointed to a chargen root cause (#537) |
| **the eight-agent fan-out** | **101** | 97 rows audited, 0 raise, 0 newly silent |

## The fan-out, and what it was actually worth

Eight agents, one bin of files each, ~198 rows apiece. 55 content files
changed. The row yield (101) was the *smaller* half of the value.

**The two findings that paid for it are cross-cutting, and no
family-by-family pass reaches either, because neither is a family:**

* **#539 `World.terrain` is never written.** `ecs.py:45` initialises it to
  `set()` and nothing in the tree adds a word. All **70** `c.terrain()`
  gates are false in every fight — 29 "aquatic", 20 "sunlight", 7 "water".
  A gate on a bonus is merely inert; a gate on a **penalty or a
  Requirement is silently wrong in the stronger-than-print direction.**
  The bonus/penalty split is not yet measured and is the next thing to
  establish, because it decides whether this is 70 dormant clauses or a
  live correctness bug.
* **#540 `c.watch(once=True)` never spent** when the handler's whole effect
  was rewriting a field on its own event. Fixed, with
  `drivers.py once_spent` and a plant test. Three live rows, and the
  sharpest chose that shape *expressly* to avoid shaving every blow, which
  is what the bug made it do.

Both are the engine's signature mode — silently false — and `audit.py`
cannot see either: the rows fire and do something, too often.

* **#541 the brief's name substitution has two opposite faults.** Three
  agents independently referred up an unreadable brief. Over-substitution:
  a hyphenated name is replaced piecewise (23 creatures, 73 occurrences),
  and an ordinary noun inside a creature's name is swapped where the card
  uses it *mechanically* (2 rows, one of them unwritable — the destination
  is gone). Under-substitution: an unindexed proper name stays in the clear
  in a body, which breaks `CLAUDE.md`'s stated guarantee that "the body
  stays safe to copy from".

## What the re-pointing taught, which is the reusable part

**Half the symbols that look like one gap are several.** `c.zone(exempt=)`
was three; `c.recast(reach=)` two; `c.ability_check()` four. Pointed the
other way at fan-out scale: **one gap often wears several symbols**, and
that is worse, because it *understates* demand in the ranking the queue is
worked from. The reroll family is 5 spellings over 4 real gaps; the
grant-action word family 3 over 1; race choice 3 over 1.

**A marker often names a field when the blocker is elsewhere.** #538
records the four shapes, and the one to watch for is *nothing makes the
event at all*. Corollary: **a field nobody populates reads as None for
ever** — which is #539 at scale.

**A marker that names something present can never go green.**
`Cast.condition(ongoing=)` resolves, so `todo.py` read it as ARRIVED and
the row would have reported ready for ever.

**Finishing a row makes pre-existing faults visible.** Today, beyond the
earlier three: a monster's conditional bonus that asked no part of its
Requirement; two creatures that blinded their own maker; a cumulative bonus
paid as three one-shots.

## Head of the queue, as it stands

```
compendium.attack_defence    23   no code can close these -- in the CSV
c.race_option()              24
compendium.silvered          24   likewise; Camille's ruling is recorded
spec.weapon_ref()            16
chargen.pact_blade()         15
spec.monster_ref()           15
chargen.skill_training()     14
etl.item.inline_block()      13
spec.stat_block()            13
spec.feature_ref()           12
c.extend_move(any_of=)       11
Target.ident                 10
c.on_extra_damage()          10
chargen.armor_proficiency()  10
```

## What I would do next, in order

1. **The `spec.*` / `chargen.*` / `etl.*inline_block` block as one batch** —
   ~104 rows, plus **#541's three faults, which are in the same files and
   need the same rebuild**. A rebuild forces a wide sweep and a
   `replay verify`, so grouping is one sweep instead of nine. Largest
   tractable block left.
2. **Measure #539's bonus/penalty/Requirement split**, then dress the board
   in `story/`. Cheap to measure, and it decides the priority.
3. **`c.extend_move(any_of=)` 11** and **`c.on_extra_damage()` 10** —
   ordinary verb families. Note two one-line content fixes unblock three of
   the first: `races/powers_a.py:389` and `powers_b.py:676` hard-code a
   distance where they should read `c.squares_for`.
4. **`c.reroll_*(ev=)`** — all three verbs read `self.trigger` and so are
   unusable from a watch; `AUTHORING.md` already documents that `ev.result`
   can be rewritten from a plain watch, so only the packaged form is gated.
   6+ rows across two bins.
5. **A word list in `actions._granted`** — it reads five words and silently
   eats anything else, so rows that look finished are inert. 3 rows, and
   `AUTHORING.md` already documents the trap.

## Awaiting Camille

* **`c.milestone()` on 5 item rows.** Between-encounter recharge; the engine
  models one encounter, so no symbol can ever land and `todo.py` will never
  go green — but all five play correctly today. Same shape as the Fortune
  Card rows ruled `declined=` in #482. An agent correctly refused to make
  the scope call.

## What not to do

* **Do not run `check.py --all` by hand.** The nightly pays it at 02:07.
* **`audit.py --changed` is not narrow** after a run of commits — it
  measures from the last full sweep's sha, so it silently becomes the wide
  sweep. Pass refs explicitly; derive them from the diff.
* **Do not re-record `replay` without measuring first.** Normalise *both*
  positional event references and effect ids — missing either manufactures
  ~150 phantom replacements.
* **Do not trust an agent's engine-gap list without checking the code and
  `blocked.py --group`.** One bin named a facility that had landed hours
  earlier and gave a row count 7x the real one.
* **Do not trust a marker's wording.** Read the card.
