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
| `beat.py` | a roleplay scene, one exchange at a time: who speaks, what they try, what they already know, what it changes. |
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
* **`--god-mode` hands over every fight and says so, every time.** It
  exists because the AI policy is the weak half right now and a campaign
  that loses in chapter 1 stops, so reading four scenes of conversation was
  costing four fights. No board is built -- which is the point and not a
  shortcut, because a fast fake fight would still spend powers and surges
  through `harvest` and the party would reach the next conversation quietly
  weaker. Nothing a god-mode run prints is evidence about combat, and the
  banner, the scene line and `Step.notes` all say so.
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

### A bigger model is not the fix either, and reasoning models cost twice

Measured over Tailscale against a 14B reasoning model on another host, same
scene, same facts, same prompt, judged by the local 7B held to controls:

```
qwen2.5:7b local        echo  2/20   covered 15/20    9.6s per beat
deepseek-r1:14b desk    echo  0/20   covered 15/20   18.7s per beat
```

**Identical coverage at twice the latency.** So #809 is not a capability
gap and will not be closed by a bigger model -- the three directions in
that issue are structural for a reason.

Two things to know before pointing a role at a reasoning model:

* **`max_tokens` covers thinking *and* answer.** ollama keeps the chain in
  a separate `thinking` field, so nothing leaks into the reply -- but the
  budget is shared, and the DM role's 200 tokens bought 906 characters of
  thought and an **empty string**. `beat.py` would have printed "The moment
  passes." `_ollama` now raises `NoModel` naming the budget instead. About
  800 is the floor for this model where the 7B wants 200.
* **A cold load is minutes, not seconds.** First call to the 9 GB model was
  **3m26s**; warm it is 5-6s. Do not read a first-call timing as the
  model's speed, in either direction.

## A band cannot keep a secret, and a printed number beats both

Two measurements that settled the design of `Lore` and are worth not
re-deriving.

**Five characters rolling makes a band a router, not a gate.** At level 1,
real party, real modifiers: an easy check is passed by somebody **100%** of
the time, a moderate one 97-100%, and only hard is a real question at
52-89% depending on the skill. So the band decides *who* tells the player,
which is the useful output -- and **a fact that must stay unavailable gets
no `Lore` row at all.** It belongs to an NPC's `knows`, or behind an
affordance. Over 60 campaigns delivery split 41% companion / 38% the player
/ 22% nobody.

**A stated DC wins over a band, because bands are lossy.** The adventure in
hand prints a ladder of 8, 12, 15 and 19; the bands at level 1 are 8, 12
and 19, so **15 has no band** and both rows carrying it were rounded up to
hard -- two facts made materially harder than the author set them. `dc` on
`Lore` and on `Affordance`, with the band as the fallback for a page that
stated nothing.

## Everybody declares at once, which is a rule and not an ordering

Nobody sees anybody else's intent in a beat: the human and each companion
declare blind, and the DM adjudicates the set. That is Camille's design and
it is **load-bearing**, because it is what lets the companions' model calls
start *before* the human is prompted -- `situation` is fixed at the top of
the beat and `declare` reads only previous beats, so a companion's answer
cannot depend on the human's line and never could.

The payoff is the only idle stretch in a beat. `fan_out` buys nothing
against a default ollama, which generates one request at a time, but a
person composing a line is several seconds of a GPU doing nothing.
Interleaved repeats, 6s of simulated typing: **median 23.7s against 26.8s,
so 3.1s saved against a 6s ceiling**, and the ceiling is the think itself --
a real person takes longer than 6s, so both grow. The model's own variance
is wider than the effect (17.9-26.3s within one arm), so treat 3.1s as soft
and the direction as solid; a single uninterleaved pair reported 12.5s,
which is arithmetically impossible as overlap and was mostly drift.

`drivers.py beat_loop` asserts the invariant rather than the speed: a
companion is handed the identical scene whether the human typed nothing or
kicked the table over. Breaking it -- moving the work after the prompt and
feeding the human's intent in -- goes red.

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
uv run scripts/play.py --play <module> --god-mode  the story half, no fights
uv run scripts/drivers.py reflavour_retype reflavour_words skill_challenge \
    challenge_refusal training_bonus challenge_costs_nothing \
    beat_loop scene_audience module_refusals affordance_match
uv run scripts/check.py --only play,drivers
```

Ten drivers cover this component and **each was proven by breaking what it
watches** — the retype, the word grant, the three-failure cap, the refusal of
an unlisted skill, the read of `Skills.trained`, the arming-is-not-spending
rule, the `once` rule, the scene ending, whose text becomes a fact, and both
halves of the brief/sets split. All went red.

`affordance_match` is the one that needs a model and **skips** when none is
serving; the rest run offline.

**`module_refusals` exists because nothing read the validator's messages.**
`module.py` collects every problem and refuses with carefully worded text,
and no driver asserted a single one -- so breaking the `dc` type check to
coerce a nonsense value instead of refusing it left the whole suite green.
A refusal nobody tests is a refusal that can be deleted by accident. The
three it covers are the silent ones: a module that validates and then plays
wrong.

**Clear `__pycache__` between a break and its restore.** A restore that
lands in the same second as the `.pyc` does not invalidate it, so the tree
reads correct and runs broken — two drivers failed that way here and the
first three diagnoses were all aimed at the source. `find . -name
__pycache__ -type d -exec rm -rf {} +`.

One honest limit, because it is the kind of thing that rots: `training_bonus`
asserts the difference equals `TRAINING`, so changing the constant moves both
sides and it stays green. It proves the bonus is *applied*, which is the half
that was actually missing here (#565). Break the read, not the number.
