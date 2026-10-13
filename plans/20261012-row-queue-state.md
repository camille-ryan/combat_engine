# The row queue, measured at the end of 2026-10-12

`blocked.py` at **1,615**, down from 1,666 at the start of the day's row
work. 50 commits. Every instrument green except the wide sweep, which the
02:07 nightly pays.

This file exists because the goal was "work the entire list of rows" and
that is not a one-session job: the arithmetic in
`plans/fizzy-humming-walrus.md` is roughly **800 commits**, and Phase 2c
alone is ~480 of them for a quarter of the rows. What follows is the
measured state so the next session starts from numbers rather than from a
re-read.

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

## What the re-pointing taught, which is the reusable part

**Half the symbols that look like one gap are several.** `c.zone(exempt=)`
was three; `c.recast(reach=)` was two; `c.ability_check()` was four. The
`c.move_through()` lesson at larger scale, and the cost of getting it
wrong is a symbol that cannot go green correctly for any of its rows.

**A marker often names a field when the blocker is elsewhere.** #538
records the four shapes seen today, and the one worth watching for is
*nothing makes the event at all* — the field looks like the answer right
up until you look for the caller. Corollary, now written at several
sites: **a field nobody populates reads as None for ever.**

**Finishing a row makes pre-existing faults visible**, which is the right
direction and will keep happening. Today: `f1534` declared `ENCOUNTER` on
a triggered trait (spent on its first firing), four shield rows correctly
silent on a board whose fighter holds no shield, and a `None`-able
`Effect` read without narrowing in `drivers.py`.

## The head of the queue, as it stands

```
compendium.attack_defence    26   no code can close these -- in the CSV
c.race_option()              24
compendium.silvered          24   likewise; Camille's ruling is recorded
spec.weapon_ref()            16
chargen.pact_blade()         15
spec.monster_ref()           15
chargen.skill_training()     14
Usage.RECHARGE(when=)        13
etl.item.inline_block()      13
spec.stat_block()            13
spec.feature_ref()           12
c.extend_move(any_of=)       11
Target.ident                 10
c.on_extra_damage()          10
chargen.armor_proficiency()  10
```

**50 of the top 15 are the two compendium symbols**, which no engine
change reaches — they are in `plans/20261012-compendium-blocked.csv` with
page URLs, awaiting inspection.

## What I would do next, in order

1. **The `spec.*` and `chargen.*` block as one batch** — `spec.weapon_ref`
   16, `spec.monster_ref` 15, `spec.stat_block` 13, `spec.feature_ref` 12,
   `chargen.skill_training` 14, `chargen.armor_proficiency` 10,
   `chargen.power_choice` 9, `chargen.pact_blade` 15. **104 rows.** These
   need a rebuild to take effect and a rebuild forces a wide sweep and a
   `replay verify`, so grouping them is one sweep instead of eight. This
   is Phase 2b of the plan and it is the largest tractable block left.
2. **`c.extend_move(any_of=)` 11** and **`c.on_extra_damage()` 10** —
   ordinary verb families, the shape done five times today.
3. **`Target.ident` 10 + `Target.creature_kind` 8** — but read #537 first:
   a character carries no kind words at all, and the ETL does not import a
   race's origin. That may be a hand-kept table of 46 races rather than a
   parser, which is Camille's call.
4. **`Usage.RECHARGE(when=)` 13** — a recharge condition that is a state
   rather than a moment, already filed as #489.

## What not to do

* **Do not run `check.py --all` by hand.** The nightly pays it at 02:07.
* **Do not re-record `replay` without measuring first.** Twice today the
  divergence was explainable and once it was a behaviour fix hiding inside
  a repr change. Normalise *both* positional event references and effect
  ids — missing either manufactures ~150 phantom replacements.
* **Do not trust a marker's wording.** Read the card. The one family I
  declined today for "the rows don't say" turned out to have ten cards
  saying exactly the same thing in the same words.
