# Story Engine — charter

**This file was 0 bytes and then said "Nothing is built", and both have now
been wrong for a while.** It is a charter rather than documentation, and the
documentation is `src/combat_engine/story/CLAUDE.md`, which exists because
there is code to govern.

What is built, as of 2026-10-27: a module is a graph of scenes
(`module.py`, #789); an adventure you own is split out of a PDF into a draft
worth filling in, **with its italic read-aloud pulled out by font**
(`importer.py`); a scene's opposition resolves by name, then by theme, then
by shape (`cast_list.py`, #790); a stat block can be worn as something else
(`reflavour.py`, #790); a skill challenge runs on a board with nobody to
fight on it (`table.py`, `challenge.py`, `dc.py`, #791); and a campaign is
written down and picked up again (`save.py`, `run.py`, #792).

**And a roleplay scene is now played rather than printed.** A local model
speaks for the NPCs and for the party members nobody is driving, one beat at
a time, inside rails the module lays: `beat.py` runs the loop, `llm.py`
holds a model per job with a per-campaign override, and the judgement stays
in the module -- affordances for what may be tried, `Lore` for what a
character may already know. #800-#804, #807, #829.

`scripts/play.py` plays one, `--god-mode` hands over the fights so the story
half can be worked on alone, and `check.py` runs both.

Not built: human-driven character creation (#793), `/api/day` and any
browser view of a campaign, milestones (#615), a freeform campaign with no
module behind it, and **the knowledge graph that would stop the DM inventing
canon** (#830) -- designed in `docs/STORY_GRAPH.md`, not yet written.

Chapters 2-5 of the one converted module do not exist either: 15 scenes of
65, and ~10 of the remaining 50 are phantoms the importer makes out of the
adventure's own summary section (#833).

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

## Where the knowledge lives

`docs/STORY_GRAPH.md` is the design for what a campaign knows: three layers
(setting, module, campaign), facts tagged by where they came from, lookup by
name rather than by embedding, and secrecy expressed as a DC. It is written
out because the whole of it came out of one conversation and none of it was
anywhere in the repository, which is how a finding gets lost.

Read it before touching `beat.py`'s prompts. The rule it formalises --
**the model may read what the players know and never what the DM knows** --
has been re-learnt four times here under four different names, and each
time it cost a bug.

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
