# Combat Engine — v2 architecture

## Context

This is attempt two. `~/proj/4e` is attempt one: 143k lines of Python, 595 commits, powers and monsters authored up to level 13, plus 29k lines of verification scripts.

**The frontend there is good and comes over. Everything else is a clean slate.**

The thing that went wrong, in your words: *ingesting monsters and powers was too cumbersome.* The old repo's own last plan says the same in numbers:

- 546 distinct op shapes; **328 used by exactly one row**
- **1,717 rows declared empty** with an essay explaining why — 928 of them citing a blocker already fixed
- a bespoke hand-written check owed per row, ~an hour each
- two content paths — a regex compiler and hand declarations — disagreeing with each other
- a docstring "claims" checker, a name-leak audit, ~50 gate instruments, a git worktree and a GitHub issue per agent

The op vocabulary was the root. Every power that didn't fit needed a new op, a new builder, a new gate, and a new check — so the marginal cost of a power never fell. Then anything still unwritable needed a formal excuse, and the excuses outnumbered the powers.

**This plan's single goal: writing one power costs about six lines and nothing else.**

---

## The core move: a power is a function with a declarative header

```python
@power("p289", level=1, cls=FIGHTER, usage=ENCOUNTER, action=STANDARD,
       keywords=[MARTIAL, WEAPON], reach=Melee(1), target=ONE_CREATURE,
       requires=SHIELD)
def p289(c: Cast):
    if c.attack(c.str_ + 2, vs=REFLEX):
        c.damage("1d10", c.str_mod)
        c.push(1)
        c.prone()
```

**Header is data. Body is code.**

The header carries what the UI and the rules need to know *without running it* — action type, range, target, usage, keywords, prerequisites. That drives the legal-action list, the power card, and greyed-out reasons.

The body is plain Python against a `Cast` context. That kills, in one stroke:

- the op registry and its 546 shapes — there is nothing to extend
- the regex compiler — there is only one path
- the blocked-row queue — **nothing is ever unwritable**, so there are no essays and no stubs
- the per-row bespoke check — the body *is* the specification

A weird power gets an `if`. A unique power gets its own three lines and costs nothing extra. The 328 one-off ops become 328 ordinary function bodies.

Monster abilities use the identical decorator against the identical `Cast`, per the README's "share ops" requirement. A monster's numbers (HP, defenses, speed) load from data by id and are never hand-written.

### Triggered and ongoing effects

Not everything is one-shot. Marks, auras, stances, and "whenever an ally within 5 is hit" register listeners instead of resolving immediately — still plain Python, with closures holding the state:

```python
@power("p1234", ..., usage=DAILY, action=STANDARD)
def p1234(c: Cast):
    if c.attack(c.wis_, vs=WILL):
        c.damage("2d6", c.wis_mod)
        @c.until_eont(c.target)          # expires on its own clock
        def _(): c.target.defense(AC, -2)
```

### The trade-off, stated plainly

Function bodies are **not introspectable**. The engine cannot report "what would this do" without running it, and there is no automatic op-coverage audit.

That is the price, and it is the right one — that audit machinery is exactly what made v1 expensive. Two things cover the gap: the header holds enough for the UI, and `scripts/show.py` *fires* a power on a fixed board and prints the resulting event log, which tells you what it does more honestly than a static read ever did.

---

## Ingestion: three steps, no ceremony

1. `uv run scripts/spec.py p289` — prints only the mechanical lines. Strips the name header, the italic flavor line, and the "Published in…" tail. The agent never learns the power is called anything.
2. The agent writes the function.
3. Done. No issue, no worktree, no bespoke check, no queue entry.

Batch it: `scripts/spec.py --class fighter --level 1` emits every undeclared row's spec at once, and one agent writes the file.

---

## Rules core

ECS, per the README, kept deliberately thin — components are dataclasses in dicts, systems are plain functions. Ten entities on a board does not justify a framework.

**Event bus, three beats.** Everything is an event. Interrupts run before resolution against a mutable event (may change it or cancel it); the event resolves; reactions run after.

**Adjacency is derived.** On `EnterSquare`/`LeaveSquare` the movement system diffs the adjacency set and emits `AdjacencyGained`/`AdjacencyLost`. Opportunity attacks, aura entry, and "when a creature moves next to you" all hang off those two rather than each re-scanning the grid.

**Relational effects are not components.** `grabbed by`, `marked by`, `hidden from`, `dominated by` involve two entities; a `(kind, source, target)` store with duration handles holds them. Marked enforces one source per target. Flanking and combat advantage are *computed on demand*, never stored — too many things grant them.

**Durations** record the round *and* whose turn applied them. Without that, "until the end of your next turn" applied on your own turn expires one turn early — the most common bug in 4e implementations, and worth building right the first time.

**Action economy:** standard/move/minor with the downgrade chain; immediate 1/round; opportunity 1 per other creature's turn.

**Determinism.** An encounter is `(seed, setup, events)` and replays exactly. This was v1's one genuinely load-bearing property and it carries over.

---

## Layout

```
combat_engine/
  engine/          ecs, components, relations, events, grid,
                   turns, conditions, durations, resolve, zones, cast
  content/
    powers/        fighter/ cleric/ rogue/ wizard/  — level_1.py, …
    monsters/
  data/            game.db, built from compendium.sqlite
  etl/             HTML parsers  (rewritten, not carried over)
  api/             FastAPI, REST + SSE
  web/             the frontend, copied from ~/proj/4e
  scripts/         four instruments (below)
  plans/
```

`p<compendium ID>` and `m<compendium ID>` for ids — stable, already unique, nothing new to maintain. Names live only in `localization/`, generated from your compendium and gitignored.

---

## Frontend

Copied from `~/proj/4e/src/dnd4e/api/static/` unchanged: vanilla JS, no build step, ~3.7k lines including CSS, talking REST + SSE.

Its contract is 18 small models in the old `dto.py`. I'll read that file **as a specification** and reimplement the models against the new engine — reading the old repo is not the same as carrying its code, and the page is the consumer that defines the contract.

Two notes:

- **Staying vanilla JS.** Answering your question below — the honest answer is TS isn't worth a port here.
- **Day mode is deferred.** The page has an adventuring-day UI (rests, multiple encounters). That's past "combat engine," so those endpoints come later and that part of the page stays inert until they do. Flagging so it isn't a surprise.

---

## Verification — four instruments, not fifty

No test suite, per your rule. Instruments you read instead:

| Command | What it says |
|---|---|
| `scripts/replay.py verify` | Re-runs recorded seeded fights, exits non-zero on the first diverging event. The regression net. |
| `scripts/show.py p289` | Fires one row on a fixed board; prints the sanitized printed text beside the event log. The read-it-yourself check — generated, never hand-written per row. |
| `scripts/leaks.py` | Greps the whole tree against every display name in the compendium. Exits non-zero on a leak. This is the README's legal requirement, enforced. |
| `scripts/coverage.py` | Which rows are declared and which are not, by class and level. The worklist. |

Plus `ruff check .` after every Python change.

One thing worth revisiting later: with no tests, a power that silently breaks months from now won't surface on its own. `replay.py` catches engine breakage, not content rot. Your call whether that ever needs more.

---

## Milestones

**M0 — Scaffold.** `git init`, `pyproject.toml`, ruff, package dirs, gitignore (compendium, localization, data).

**M1 — Rules core, no content.** ECS, relations, event bus with both windows, grid/LOS/cover/flanking, turns + action economy, conditions, durations + saves, attack/damage pipeline, zones/auras, and the `Cast` context that power bodies are written against.

**M2 — ETL + spec tool.** Parse the compendium HTML into `data/game.db` for monster and power numbers. `scripts/spec.py`. `scripts/leaks.py`.

**M3 — Walking skeleton.** One at-will per class, three low-level monsters, a scripted fight that runs end to end and prints its event log.

**M4 — Web.** FastAPI + SSE serving the DTO contract; copy the frontend in; play a fight in a browser.

**M5+ — Content by level.** All of level 1 across the four classes, then monsters 1–3; then level 2, and on to PC 10 / monster 13.

The first real measurement of whether this worked is at M5: **how long one power takes to write.** Target is minutes.
