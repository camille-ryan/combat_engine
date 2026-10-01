# Story Engine — charter

**Nothing is built.** This file was 0 bytes. It is a charter, not
documentation, and there is no `CLAUDE.md` for this component because there is
no code to govern.

Written down so the next person does not have to rediscover where the job
currently lives, or mistake the log renderer for a story engine.

## What it is meant to do

From `README.md`: select monsters for an encounter and **reflavour** them —
generating names and descriptions, sometimes changing damage types — so the
same stat block can be a gang of bandits or a pack of ghouls. Above that, the
adventuring day: several encounters against one party, with rests between.

`ENCOUNTERS.md` holds five encounter archetypes with compositions and
tactics, plus guidance on what is not fun (too many controllers, too many
soldiers) and how to theme a mix. **Nothing reads it.** It is design notes
waiting for this component, and its own first line says it should probably
move here.

## Where its job lives today

Scattered, and this is the useful part of the charter:

* **Monster selection, the party, the spawn positions and the terrain call** —
  **done, and this component now exists.** `story.field_encounter` is the one
  place that fields an encounter; `api/session.create` and
  `scripts/fight.build` both call it. #229.

  It was the same six steps with the same constants in two files, with the six
  replay fixtures pinning the `scripts` copy — so changing composition in
  `api/` diverged silently. The cut was worth making for more than tidiness:
  the two had already drifted twice, and the second drift was live. `api/`'s
  own pick returned `loader.pick(level)` raw, so the path a player actually
  plays fielded **three brutes and a lurker** at level 5 where the scripts
  copy fielded soldier, brute, artillery, skirmisher.

  A "character" is still constructed fresh each time; nothing is saved.
* **The adventuring day** — `GET/POST /api/day` is a deliberate `501` in
  `api/app.py`, and `web/app.js` already calls it. The endpoint exists to be
  filled in.
* **The day's mechanics already exist** — `turns.short_rest` and
  `turns.extended_rest` both work and `fight.py --rest` calls them. What is
  missing is a `World` that outlives one fight (#72), which is this
  component's first real task.

## What is *not* this component

`api/render.py`'s `narrate()` / `narrate_span()` and `transcript.py` are a
**log renderer** — they turn events into prose a player reads, and write
JSONL to `logs/`. Useful, unrelated. Do not extend them into story
generation; a transcript is forensic, and nothing reconstructs a `World` from
one.

## Constraints it inherits

* **Reflavouring must not import a printed name.** Generating a name is the
  opposite problem from the rest of the project — here the engine *invents*
  prose rather than being kept away from it. Keep generated prose out of
  `data/game.db` and out of any spec, so `leaks.py` stays meaningful: a
  generated name that lands in a column is indistinguishable from a leaked
  one.
* **Encounters must stay reproducible from a seed.** Everything else here is,
  and `replay.py` depends on it.
* Round counts are the measure to watch, and the target is **7-8 rounds** —
  established from actual play, correcting an earlier assumption of 3-4 that
  several issues were written against.
