# Encounter objectives in encounter design

Camille, 2026-10-29: *"I'd like these encounter objectives to be represented in
encounter design in this project. Make changes as necessary."* And, on the
translation: *"you don't need to do a 1:1 conversion. This is more of a generic
DM advice thing."*

So: take the **concept** — an encounter has a stated goal other than "kill
them all", and that goal changes how the fight is built, run and judged — and
build it in this project's own terms. No imported currency, no imported
formulas.

## What a fight is today

```
run._fight:  resolve() -> field_encounter() -> Encounter.start()
             while not encounter.finished and world.round <= MAX_ROUNDS: ...
             won = encounter.winner is Team.PC
             step.outcome = "won" if won else "lost"
```

One win condition, one loss condition, binary, and `Encounter.winner` is
*"the one side with a living combatant left"*. A scene can say what the ground
is (`Scene.terrain` -> `run.ground`), how hard it is (`Scene.difficulty`), and
who is in it (`Scene.foes`). It cannot say **what the fight is for**.

## The framework

Every objective, in the source, carries six things. Four of them are data this
project can hold and two are advice for an author:

| | ours |
|---|---|
| success condition | **code** — a watcher that reads the board |
| failure condition | **code** — same watcher |
| difficulty modifier | **one step along `module.DIFFICULTY`**, applied before the budget is spent |
| what creatures suit it | advice; goes in the module brief and the docstrings |
| what map suits it | advice, and partly unreachable — every board is 16x12 (#974) |
| reward | **deferred to #967**, which is where XP will land |

So the deliverable is `Scene.objective`, a closed set of kinds, a watcher that
runs during the fight, and a verdict that replaces the `winner is Team.PC`
line.

## Translations, stated once

* **Stamina -> hit points.** Camille's note. Nothing in this slice needs a
  stamina formula, but the deferred ones do and this is the conversion.
* **Encounter Value -> XP.** `story.budget` is the XP budget; one hero's share
  is `budget(level) / SIDE`.
* **Victories -> nothing, yet.** A per-encounter reward currency with no
  4e analogue. The *grade* is worth keeping, so a met objective records
  whether it was met cleanly; the payout waits for #967.
* **Organization (minion/horde/platoon/solo) -> rank.** We have
  `standard/elite/solo/minion`; horde and platoon both collapse onto
  `standard`, so a success condition **declares** its threshold rather than
  inferring it from the cast's organization.
* **Difficulty categories.** Four either way: easy/standard/hard/**deadly**
  where the source says extreme. One step along our own ladder.

## What lands now, and why these six

The dividing line is whether the board can already answer the question.

| kind | success | needs |
|---|---|---|
| `defeat_all` | one side has no living combatant | nothing — this is today's behaviour, named |
| `diminish` | living enemies fall to `share` of their starting count | a count at `start()` |
| `defeat_foe` | every designated enemy is down | a way to designate; refs are already in `dressed.refs` |
| `survive` | the party lasts `rounds` rounds | a round count |
| `hold` | lasts `rounds` **and** fewer than `leaks` enemies reached the position | a position, checked per round |
| `assault` | the party holds the position for `rounds` consecutive rounds with no living enemy in it | the same position |

A **position** is a word from a closed set, resolved against the real grid —
`west`, `east`, `north`, `south`, `centre`. Not coordinates: a module author
cannot know our board is 16x12, and `Scene.terrain` already sets the precedent
for a closed vocabulary the loader validates. The party spawns in the west
(`chargen.spawn` at `(2, 3 + i*2)`), so `hold` defaults to the party's own end
and `assault` to the far one.

## What is deferred, and the one engine finding behind it

Four of the source's objectives need a **thing on the board that is not a
creature and can be destroyed or carried**: destroy the thing, get the thing,
escort a ward, save another.

Measured while scoping: `Scenery` is already a legitimate target
(`query.targetable` — *"Scenery has none and is still a legitimate target"*)
and has **no writer anywhere** (zero `Scenery(` call sites outside its
definition). Giving one `Health` would make it destructible — but
`query.creatures` is `world.having(Health, Position)`, so it would land in
`combatants`, which is the initiative roster, and take a turn.

`combatants` already subtracts three things for exactly this reason, with the
comment: *"An attackable conjuration [...] has `Health` so that it can be aimed
at and killed, and that is the only reason; it takes no turn and does not
decide the fight. #714."* A destructible objective object wants a fourth
subtraction. That is a one-line `engine/` change with a tree-wide audit
attached, so it is **filed, not built here** — and it unblocks four objectives
at once, which makes it the right next step rather than a loose end.

The remaining two — stop the action, complete the action — need an action a
character can take *inside* a fight that is not an attack, which is #964's
other half and does not exist.

## Steps

1. `story/objective.py`: `KINDS`, `POSITIONS`, `Objective`, `Watch`, `judge`.
2. `module.py`: `Scene.objective`, validated against the closed sets.
3. `cast_list.py`: the difficulty step, reported in `Dressed.notes`.
4. `run.py`: build the watcher, bound the loop with it, take the verdict.
   **No objective must be bit-for-bit today's behaviour.**
5. `scripts/drivers.py`: one rule per kind, each proven by breaking it.
6. The module brief gains the field, so a converted adventure can state one.

## Verification

```
uv run scripts/drivers.py <the new rules>
uv run scripts/check.py --only drivers,play
uv run scripts/replay.py verify            # must stay 7/7 -- no fight moves
```

The risk to watch is step 4: a scene with no objective must field, play and
judge exactly as it does now, or every fixture diverges. The driver for that
is the control.

## Out of scope, filed instead

* a destructible / carryable board object (the `combatants` finding above)
* stop-the-action and complete-the-action, which want an in-fight action (#964)
* reinforcements priced in XP during the fight (#962, #978)
* map advice, which is mostly unreachable while every board is 16x12 (#974)
* the reward for meeting an objective (#967)

---

## What landed, 2026-10-29

**Five objectives, not six.** `defeat_all`, `diminish`, `defeat_foe`,
`survive`, `hold`. `assault` was built, measured, and removed -- see below.

| | |
|---|---|
| `story/objective.py` | new. `KINDS`, `POSITIONS`, `Objective`, `Watch`, `area`, `watcher`. |
| `story/module.py` | `Scene.objective`, `_as_objective`, and the field refused on the three kinds that cannot use it. |
| `story/cast_list.py` | `_stepped`, the one-band difficulty move, reported in `Dressed.notes`. |
| `story/run.py` | the watcher built before `start()`, the loop's third exit, the verdict, `Step.objective` and `Step.clean`, the campaign-log row. |
| `story/importer.py` | the brief tells a converter when and how to state one. |
| `scripts/drivers.py` | `objective_verdict` (12 assertions), `objective_budget` (5). |
| the fixture | `loft` carries a `defeat_foe`, so `check.py --only play` runs one end to end. |

**Verified**: 194 assertions across the 21 story drivers, `replay.py verify`
8/8 unchanged, the whole fixture module plays, `leaks.py --modules` clean.
Six breaks, each landing on the right assertion and nowhere else -- the
no-objective control, the unfielded-designation guard, the loop's watcher
check, the budget step, the stated-`xp` override, and the name lookup.

### Four faults it had before a driver existed

All four found by probing by hand and reading the output, which is this
component's own rule:

1. **the `diminish` denominator was counted after round one**, so the party
   was asked to halve an already-reduced cast -- *"2 of 4 are down"* on a
   fight that began with six.
2. **winning early read as failing** for `survive` and `hold`.
3. **one fight reported two round counts** on an early exit.
4. **`defeat_foe` was unusable from a module file.** It matched database refs
   and an author writes the page's own word. Worse, fixing that by filling the
   name map at *judgement* time left `_decide` matching nobody, so the fight
   resolved at the **end of round one** and still printed a correct-looking
   verdict.

### And the assertion that took three attempts

Fault 4's driver is worth recording because the first two versions **could not
tell the two implementations apart**. With the name lookup deleted,
`_left_standing` matches nobody, the objective declares itself met, and the
verdict text is *identical* to a real success. Both "the word resolves" and
"the word and the ref agree" stayed green against the break. What separates
them is **when the fight stopped**: a broken build ends every `defeat_foe`
fight in round 1, so designating the creature that falls last must take
exactly as long as killing them all -- 4 rounds against 1.

### `assault`, built and removed

Every arm reported `0 of N consecutive rounds`, including the one where the
party stood in the area having killed everything. `Encounter.finished` ends
the fight the moment a side is gone, so there is at most one boundary at which
the party holds a cleared area; and a round cap as a resolve condition cuts
the fight short before the area can be taken. One field was serving as a
deadline *and* a hold counter. It wants reinforcements (#962).

### Still out of scope, and filed

* a destructible or carryable board object -- the `combatants` finding in the
  section above, which unblocks four objectives at once
* `assault`, on #962
* stop-the-action and complete-the-action, which want an in-fight action (#964)
* the reward for meeting one, on #967 -- `Step.clean` is recorded and unspent
