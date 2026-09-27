# The remaining waves, ready to fan out

Written so that a session with the subagent cap raised can start
dispatching immediately rather than re-deriving the work list.

## Why this file exists

The plan sized stage 4 at ~34 agents. This session hit the
200-subagent cap with the waves unstarted and hand-wrote eight batches
instead — good rows, four real bugs found, but not a rate that finishes
2,587 units.

Restart with the cap raised:

```
CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION=600 claude
```

Then point a fresh session at this file.

## What is left, measured

Counted from `data/game.db` against `content.declared()`, not estimated.

**Feats: 1,291 heroic undeclared.**

| rows | bucket |
|---:|---|
| 697 | no class gate (race, ability, skill, level, feat-ref or nothing) |
| 45 | fighter |
| 43 | invoker |
| 37 | rogue |
| 37 | artificer |
| 36 | paladin |
| 35 | warlock |
| 34 | shaman |
| 29 | warden |
| 27 | warlord |
| 27 | ranger |
| 25 | assassin |
| 23 | battlemind |
| 22 | druid |
| 20 | cleric |
| 19 | barbarian |
| 19 | ardent |
| 18 | psion |
| 17 | sorcerer |
| 16 each | bard, wizard, avenger |
| 12 each | swordmage, monk |
| 5 | seeker |
| 4 | runepriest |

**Item blocks: 1,296 heroic undeclared.**

| blocks | category |
|---:|---|
| 204 | Implement |
| 194 | Alternative Reward |
| 129 | Consumable |
| 117 | Weapon |
| 113 | Neck |
| 99 | Arms |
| 86 each | Head, Hands, Feet |
| 77 | Alchemical Item |
| 58 | Waist |
| 21 | Ammunition |
| 12 | Mount |
| 7 | Ring |
| 5 | Companion |
| 2 | Familiar |

## The dispatch

The brief every agent reads is
`scratchpad/brief.md` — copy it into the repo as `docs/FEAT_BRIEF.md`
before the first wave so it survives the session. It already carries
the no-flavour-text rule, the hand-write rule, the marker grammar, the
"check the verb does not already exist" rule, the `_who` trap, the
per-agent verification loop and the 150-call budget.

Two lines to add to it per wave:

* the class or category, and the `--limit`;
* the file to write and which existing file to read first for house
  style. Every class with a batch already written has one: write
  `<class>_c.py` and read `<class>.py` and `<class>_b.py`.

**Wave A — feats by class, 24 agents, one per class**, limit set to
that class's count above. Classes with 12 or fewer can be paired.

**Wave B — the 697 unclassed feats, 7 agents at 100 each.** Sort by
ref so the batches do not overlap; `spec.py --feats --limit N` already
returns only undeclared rows, so agents must run **sequentially within
this wave** or be given explicit ref lists. Explicit ref lists are
safer: generate them first with one query.

**Wave C — items, 11 agents**, one per category, splitting Implement
into two. Skip Mount, Companion, Familiar and Alternative Reward on
the first pass — 213 blocks that are not equipment a heroic character
holds, and the plan already names them first to cut.

**Wave D — the second pass**, one agent per symbol with ≥20 waiting
rows, briefed with `blocked.py --refs <symbol>` and nothing else.

## What the waves must not do

* No agent runs `check.py`, `replay.py` or `fight.py`. Those are
  per-wave and mine.
* **No tree-wide `ruff check . --fix` while agents are writing.** It
  stripped an import another agent was about to use, once already.
* `git add -A` between waves sweeps in-flight work. Add by path.

## Symbols the second pass should tackle first

Counted by waiting rows at the end of this session
(`uv run scripts/blocked.py --group`):

* `c.class_feature()` — a feature named in prose with no ref. The
  largest group, and part of it may be an ETL fix rather than an
  engine one: `_named_powers` already swaps `<name> power`, and a
  `<name> class feature` pass would be the same argument. **Measure
  before building the verb.**
* `c.on_second_wind()` — second wind is an action rather than a power
  and announces nothing. One event closes it.
* `c.on_granted_basic()` — a granted swing is announced as `mba` with
  nothing recording who granted it.
* `c.as_basic(ref)` and `c.ability_for(ref)` — both fell out of the
  style family once the associated-power lists resolved.
* `c.beast()` — 18 ranger rows, and `companion` is already an ETL
  table with the full stat blocks in it.
* `c.bonus(dtype=)` — a damage bonus cannot carry a type, so every
  "extra fire damage" rider rolls untyped.

## Still open from this session

* **#204's second half.** 27 of 43 triggered feats report `UNUSED`
  because the audit board never carries a polearm, a versatile axe or
  a bow, and never swears an oath. Gear variants on the board would
  buy more verification than any other single change.
* The `f2071` list is empty on the page, so it is the one style feat
  whose associated set really is unknowable.
