# Ingesting the content, one level at a time

## Context

The engine is built and playable; what it lacks is content. 27 rows are
declared. The corpus in scope is:

- **326 PHB1 powers** across all eight classes, levels 0–10
- **630 MM1–3 monsters** at heroic tier, ~2,700 abilities between them
- **~24 class features**, which are not feats and are what make a class itself

Feats are out — they are the small every-other-level options and they have
their own `Feat` table, which this never touches.

Level 1 alone is **111 powers and 101 monster abilities across 29 monsters**.
So the work is mostly volume, and the plan is mostly about doing volume
safely and without the ceremony that sank the first attempt.

One requirement shapes the storage before any of it: **MM1 and MM2 monsters
should be convertible to MM3 maths later.**

---

## What MM3 maths actually changes, measured

Checked against the corpus rather than taken on faith. Standard monsters,
heroic tier, first at-will attack:

| | published claim | what the corpus says |
|---|---|---|
| standard damage | MM1 `4+level×0.6` → MM3 `8+level` | lvl 1 both ≈7; **lvl 10 MM1 11.5, MM3 17.3** |
| brute attack | `level+3` → `level+5` | `+4.1` → `+4.7` |
| soldier attack | `level+7` → `level+5` | `+5.4` → `+5.2` |
| other roles | — | all converge on `level+5.0` in MM3 |
| solo hit points | ×5 → ×4 | ×3.9 → ×3.4 |
| AC, non-AC defences, standard HP | — | **unchanged between books** |

The direction is right everywhere and the magnitudes are not. Heroic tier
only is part of it; the rest is that a published formula is a design target
and a book is what got printed.

So: **ship the published formulas as the default conversion table, and keep
them checkable.** `scripts/mm3.py` prints the table beside what the corpus
does, per level and role, so the numbers get tuned against evidence instead
of argument.

The headline is that **damage is the thing that changes**. Defences and hit
points come out of `game.db` already and need nothing. Damage lives inside
hand-written power bodies — which is where the storage decision bites.

---

## Storage: three changes, all before any content lands

### 1. `Damage` goes in the header, beside `Attack`

The same move that put the attack line in the header, for the same reason.
A monster's damage has to be *data* if it is ever to be rescaled:

```python
@power("m206a0", level=1, usage=AT_WILL, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE,
       attack=Attack(vs=AC, printed=6),
       damage=Damage("2d8+2"))
def m206a0(c: Cast) -> None:
    if c.strike():
        c.hit()          # the declared damage, under the maths in force
```

`c.hit()` applies it. A body that does something more complicated still
calls `c.damage(...)` directly and simply is not rescalable — an honest
limit, and it will be the minority.

Two further payoffs, both free: a policy can finally forecast damage instead
of learning it from logs, and the power card can print it.

`Damage(kind=...)` carries `normal | limited | minion`, because MM3 scales
those differently.

### 2. `world.monster_math`, exactly parallel to `world.scaling`

```python
world.monster_math = AS_PRINTED   # default: the book as written
world.monster_math = MM3          # MM1 and MM2 rows rescaled to MM3 damage
```

`engine/monster_math.py` holds the table and one function: given a row's
book, level, role, rank and damage kind, return the expression to use.
`AS_PRINTED` returns the printed one unchanged.

### 3. `game.db` learns which book a monster came from

`Source` is a comma-separated list and a row often names five books. The ETL
records `book` as the earliest of MM1/MM2/MM3 that lists it, plus `rank`
(standard/elite/solo/minion) which `monster_math` also needs. Without the
book stored there is nothing to convert *from*.

---

## Layout

```
content/
  powers/<class>/level_0.py … level_10.py     eight classes
  features/<class>.py                          class features
  monsters/level_01.py … level_13.py
```

Class features that have a compendium row use it — `p7419` for the fighter's
marking feature, `p805` for the paladin's, `p1590` for the warlord's heal.
The ones with no row of their own — the rogue's extra damage on combat
advantage, the ranger's quarry, the warlock's mark, the cleric's channelled
power — get hand-written `cf:` refs and are written from the class page.

---

## The loop, per level

1. `scripts/spec.py --class <c> --level N` for each of the eight classes,
   and `--monsters N` for the monsters. Undeclared rows only, so this is
   always a work list.
2. Fan the specs out to subagents in batches of ~15. Each gets: the specs,
   the generated `Cast` reference, the target file, and two worked examples.
3. Agents return files. Anything an agent could not say, it reports as a
   **missing `Cast` method** rather than working around it — I add the method
   once, centrally, and re-run that batch. No stored queue, no essays: the
   list lives as long as the batch and is drained immediately.
4. `scripts/audit.py` fires every newly declared row and reports the two
   failures that matter.
5. `ruff`, `leaks.py`, `replay.py verify`, `api_smoke.py`, `browser.py`.
6. Re-record fixtures, add one at the new level, commit the level.

### `scripts/audit.py` — the new instrument

Autonomy needs one thing the current set lacks: proof that a written row
actually *runs*. It fires every declared row on a fixed board and reports:

- **rows that raise** — a bug, with the traceback;
- **rows that do nothing** — no damage, no condition, no movement, no
  effect. A silent no-op is what a wrong power looks like, and it is the
  failure mode that survives a hundred rows being written at once.

It replaces nothing and adds no per-row ceremony: it is generated from the
registry, like `show.py`.

### `scripts/vocab.py` — what the agents are told

Prints the `Cast` surface from introspection: every method, its signature
and its docstring. Generated, so an agent always sees current capability and
I never hand-maintain a briefing document that drifts.

---

## Order

Level 1 complete — all eight classes plus all 29 MM1–3 monsters — then
level 2, and so on to 10 for characters and 13 for monsters. Each level ends
with a playable fight at that level, which is the point of going in this
order rather than doing all the powers first.

Levels 4 and 8 have no powers (they are score-increase levels), so those are
monsters only.

A monster stays all-or-nothing: fieldable only once every ability on its
stat block is written. `coverage.py` says what is blocking each one.

---

## Verification

Per level, all of it already exists except `audit.py`:

| | |
|---|---|
| `ruff check .` | after every change |
| `scripts/audit.py` | every new row fires, and does something |
| `scripts/coverage.py` | what is left, by class and level |
| `scripts/leaks.py` | no printed name reached the tree |
| `scripts/replay.py verify` | the engine still plays the recorded fights |
| `scripts/api_smoke.py` | 22 wire checks |
| `scripts/browser.py` | the page still plays in a real browser |
| `scripts/fight.py --level N` | a fight at the new level, read by eye |
| `scripts/mm3.py` | the conversion table against the corpus |

The number that says a level worked is `coverage.py` reaching 100% for it
with `audit.py` clean — not a line count, and not my say-so.

## Note

Copy this plan to `./plans/20260924-ingestion.md` at the start, per your
workflow.
