# Where ingest stopped, and how to start it again

Written at the end of the session that finished phases A and B. Everything
below is checkable from the repo — this file is a pointer, not a record.

## Where it is

```
uv run scripts/coverage.py                 # PHB1 powers
uv run scripts/coverage.py --book ""       # every book
uv run scripts/coverage.py --monsters --max-level 13
uv run scripts/progress.py --show          # rows per minute, by level
```

| phase | written | of |
|---|---|---|
| A — monsters, levels 1–13 | 2,596 | 2,629 |
| A — PHB1 powers | 321 | 326 |
| B — the eight classes, books after PHB1 | 1,111 | 1,296 |
| C — the seventeen new classes | 523 | 1,814 |

Phase C has four classes done: druid, avenger, barbarian, sorcerer.

**Thirteen left, largest first:** bard 133, shaman 123, monk 121, invoker
117, swordmage 112, warden 104, battlemind 92, ardent 87, psion 79,
assassin 75, artificer 69, seeker 59, runepriest 46.

## How to start the next one

The brief is `docs/AUTHORING.md` and it is current. Each wave gets that
plus a short note of what changed since the last one — see
`scratchpad/briefs/COMMON.md` for the shape, though the scratchpad does not
survive a new session and that note is worth rewriting from the recent git
log rather than recovered.

```
uv run scripts/vocab.py > <somewhere>/vocab.txt
for L in 1 2 3 5 6 7 9 10; do
  uv run scripts/spec.py --class bard --level $L --book "" >> <somewhere>/B-bard.txt
done
mkdir -p src/combat_engine/content/powers/bard
```

Then one agent per class, two classes per agent at most. A class is 60–180
rows and takes 25–45 minutes.

**Every class already has a chassis and two builds**, derived from the
compendium in `chargen.py` — nothing else is needed before writing its
powers.

## What is deliberately not written

`docs/blocked.json` — every row left out, with the `Cast` method or header
field it wanted and why.

```
uv run scripts/blocked.py --ready     # rows whose gap has since been built
```

Run that after building anything. Three level-5 rows once sat waiting four
levels because the reason lived only in a wave's report.

The large clusters, each worth building before the class that needs it:

* **`c.companion()`** — 26 ranger rows. No companion entity, no `[B]` die.
* **`c.summon`/`c.conjure` taking an inline stat line** — 14 wizard rows
  and 10 druid ones. The spec gives no ref for the creature, and a
  conjuration has no hit points so "if it drops to 0" can never happen.
* **`Keyword.RATTLING`** — 3 rogue rows are wholly this and 19 more carry
  it as a rider.
* **Skill checks** — no event, no DCs. Blocks a scattering everywhere.
* **Action points** — nothing models one. Two warlord rows and several
  clauses.

## Instruments

```
uv run scripts/check.py --all      # all seven, about six minutes
uv run scripts/check.py --history  # what each costs and has caught
```

All seven clean at the last commit. `audit` is the one that matters and is
the expensive one; it runs on every core.

## The shape of almost every bug found today

A thing that is **silently false**: a predicate reading a field its event
does not have, a gate on a key the context does not carry, an event emitted
and never read back, a default that aims at the wrong creature. None of
them raise. `docs/AUTHORING.md` collects the ones that have cost time, and
`scripts/lint.py` catches two classes of them statically.

If a content file grows a private helper, the engine is probably missing
something — that tell found `c.charge_at`, the teleport footprint bug, and
`c.had_advantage`.
