# Story Engine

The campaign runner. It decides what the fights are *for*: roleplay, skill
challenges, encounter setup and teardown, persistence, and the party carried
between all of them. The combat engine is a thing this drives.

`docs/STORY_ENGINE.md` is the charter. Global rules are in the root
`CLAUDE.md`. This file is what is different here.

## What is where

| | |
|---|---|
| `__init__.py` | fields **one** encounter: `field_encounter`, `opposition`, the XP budget, `Party`/`Sheet`/`harvest`. Predates everything else here. |
| `module.py` | a module is a graph of scenes. Schema, loader, validator. |
| `importer.py` | an adventure you own, out of a PDF and into a draft worth filling in. |
| `cast_list.py` | *four of something goblin-ish* → refs. Name, then theme, then shape. |
| `reflavour.py` | wearing a stat block as something else. |
| `table.py` | a board with nobody to fight on it, so a conversation can roll. |
| `challenge.py` | successes against three failures. |
| `dc.py` | what a check has to beat, by level and band. |
| `beat.py` | a roleplay scene, one exchange at a time: who speaks, what they try, what it changes. |
| `llm.py` | the model. A `Role` per job, two backends, a URL that can be a Tailscale host. |
| `dm.py` | the Anthropic DM. Predates `llm.py` and is **unexercised live** (#794). |
| `maker.py` | a character built by answering questions instead of being dealt. |
| `save.py`, `run.py` | the campaign, written down and played one scene at a time. |
| `scripts/play.py` | the way in. `check.py` runs it. |

## The failure mode this component produces

**A party that is quietly weaker, or a fight that is quietly the wrong one.**
Not a crash. Every bug found while building this had the same shape — a number
that moved when nothing should have moved it, and output that read as correct:

* A **skill challenge spent the party's encounter powers.** `table.py` needs a
  started encounter so feats arm, `Encounter.start()` fires every
  once-per-fight trait, and harvesting that carried it into the campaign. Four
  characters walked out of a conversation having spent 6, 4, 5 and 10 rows.
* A **role hint emptied a pool.** 253 of 384 minions carry `role = 'minion'`
  rather than a tactical role, so asking `loader.pick` to filter on
  `skirmisher` returned nothing where `role=None` returned 120.
* A **plural resolved to the wrong word.** Applying the first matching
  de-pluralisation rule turned anything ending in `les` into `...l`; 45 of 400
  names silently fell through to the theme tier.

So: **after a change here, play a whole module and read the party line between
scenes.** `scripts/play.py --play <module>` prints it. A number that moves
when nothing happened is the bug.

## Rules

* **A module is the user's own and never enters the tree.** `modules/` and
  `saves/` are git-ignored. Everything this component writes about a specific
  adventure goes there. The fixture in `scripts/fixtures/modules/` is ours,
  invented, every word — it has to be, because `check.py` plays it.
* **Check invented prose against the localisation by hand.** Authoring flavour
  text into a tracked file is a third way to leak a name and neither gate
  covers it: `--cited` needs a cited ref and invented prose cites none, and
  the wide walk waives two ordinary words. The fixture's first draft invented
  a creature name that turned out to be printed. One query over all 37k names
  finds it; guessing which of your own inventions to doubt does not.
* **Read the compendium glossary before writing a rules table from memory.**
  Two tables here came out of it — the DC-by-level numbers and the skill
  challenge complexities — and the remembered drafts of both were wrong. It
  is `select Txt from Glossary where Name = '...'`, the entries are mechanical
  vocabulary rather than prose, and it is on every contributor's machine.
* **Do not reach into `engine/`.** A change there widens `audit.py` to all
  12,197 rows, about forty minutes. Nothing in this component needed one:
  `c.set_origin`, `c.deals`, `c.resist` and `skills.check` already existed.
  When something is genuinely missing, file it — #795 is the pattern.
* **`--no-dm` and `--no-llm` are load-bearing, not fallbacks.** `check.py`
  runs `--solo --no-llm`, and the `--solo` half matters: without it every
  character defaults to human, nobody declares, and the beat loop spins
  empty exchanges -- driven without being exercised. An instrument that
  needs a network goes red for the wrong reason. Any feature added to the
  model path needs an answer for the path without one.
* **A driver that does need a model reports a skip and counts it.**
  `affordance_match` is the pattern: `llm.reachable()` first, `out.skip()`
  with the reason, and the arithmetic still reconciles. `scripts/CLAUDE.md`
  is explicit that a quiet skip is not a check.
* **A secret is withheld from a prompt, never forbidden in one.** `Npc.hides`
  is not in the prompt at all; a transition's `win` text is not in the fact
  list at all. A 7B told a secret and told not to tell it is one unlucky
  sample from telling it -- and the field *beside* a guarded one is where
  this has actually gone wrong (#805).
* **A clamp is printed.** When the budget cuts a module's stated count, or a
  creature is deferred for being out of tier, it goes in `Step.notes` and the
  CLI prints it. `scripts/CLAUDE.md`: a silent cap reads as "covered
  everything" when it did not.
* **Every scene draws from its own stream.** `Random(f"{seed}:{module}:{scene}")`.
  A single stream threaded through a campaign would make adding a conversation
  change the monsters in the fight after it.

## The model is good at voice and unreliable at judgement

Measured before anything was built on it, and every design choice in
`beat.py` follows from it. Asked to **adjudicate** three declared intents
freely, `qwen2.5:7b` got **one of three** right, and the wrong one broke an
instruction that was in its system prompt verbatim. Asked to **match** the
same intents against a closed list, it got **3 of 3, three runs of three**,
at temperature 0.

So: the module carries the judgement, the model carries the voice. An
affordance is matched by an enum-constrained call, the DC comes from
`dc.py`, the roll from `skills.check`, and the fact the DM may then state is
the affordance's own `win`/`lose` text. **Nothing the model writes becomes
true.**

### What playing it then found, which no instrument could

Five faults, all from reading a live chapter-1 transcript, none of them a
crash and none of them red anywhere:

* **The scene's brief was printed to the player**, and an adventure's prose
  is written for the DM. Chapter 1 opened by stating its own plot. `sets`
  against `brief`, #805.
* **The DM was copying its notes back** -- 20 of 20 word for word, 10 of 10
  samples identical. A list restated is not a DM.
* **A transition's `win` is a stage direction** and was in the fact list, so
  the DM wrote three party members acting in one reply, against two
  prohibitions it had been given. #807.
* **`once` was not once within a beat**, so two characters took the same
  affordance and the DM was handed contradictory facts.
* **A character at 0 hp kept talking and rolling.** #808.

**Read a transcript after changing anything here.** The component's failure
mode is output that reads as correct.

### Two rules about measuring a model

Both were learnt by getting it wrong first, in one session:

* **A metric that cannot tell the two behaviours apart is not a
  measurement.** Word overlap scored coverage while the arms under test
  differed precisely in how much they re-worded; a word search scored a
  person being *mentioned* the same as a person being put in the room. Both
  produced plausible numbers and both were noise.
* **A judge needs a positive and a negative control before any arm runs.**
  The first judge here scored a *verbatim* restatement at 6 of 12. The
  controls are one call each and they are what makes the arms mean
  anything.

And a third, about fixing a model rather than measuring it: **a prompt
addition is not free.** The clause that recovered two dropped facts relapsed
the echo five-fold. Start from a reproduction, not from a paragraph.

## The name is tried first, and that is the measurement to keep

`cast_list` resolves a module's own word for a creature against the
localisation before it tries anything else. On the module in `modules/`: **39
of 39 high-confidence names resolve, 37 of them inside the heroic tier, and
all 37 pass `loader.usable` with no missing abilities.** A hand-converted
chapter came out at 12 of 13.

The component was first designed the other way round — match on theme, dress
the result — and that design is now the *fallback*, for creatures we do not
have and for modules from editions whose creatures we never will. If a change
drops the name tier's hit rate, that is the number that matters, not the
elegance of what replaced it.

## Seams

* **`story/__init__.py` is not edited by this work.** Arcade mode is being
  built in parallel and the two are deliberately non-interacting. Import from
  it; do not change it.
* This component reaches into `chargen`, `content.loader`, `engine` and
  `policy`. It is the only one that touches all four, which makes it the
  integration point — the same position `api/` is in. Prefer pushing a rule
  down to where it belongs over adding a fifth thing this layer knows.
* Nothing imports `story/` except `api/session.py`, `scripts/fight.py`,
  `scripts/replay.py` and `scripts/drivers.py`.

## Checking

```
uv run scripts/play.py --validate <module>        every problem at once
uv run scripts/play.py --play <module> --seed 7   a whole adventure
uv run scripts/drivers.py reflavour_retype reflavour_words skill_challenge \
    challenge_refusal training_bonus challenge_costs_nothing \
    beat_loop scene_audience affordance_match
uv run scripts/check.py --only play,drivers
```

Nine drivers cover this component and **each was proven by breaking what it
watches** — the retype, the word grant, the three-failure cap, the refusal of
an unlisted skill, the read of `Skills.trained`, the arming-is-not-spending
rule, the `once` rule, the scene ending, whose text becomes a fact, and both
halves of the brief/sets split. All went red.

`affordance_match` is the one that needs a model and **skips** when none is
serving; the rest run offline.

**Clear `__pycache__` between a break and its restore.** A restore that
lands in the same second as the `.pyc` does not invalidate it, so the tree
reads correct and runs broken — two drivers failed that way here and the
first three diagnoses were all aimed at the source. `find . -name
__pycache__ -type d -exec rm -rf {} +`.

One honest limit, because it is the kind of thing that rots: `training_bonus`
asserts the difference equals `TRAINING`, so changing the constant moves both
sides and it stays green. It proves the bonus is *applied*, which is the half
that was actually missing here (#565). Break the read, not the number.
