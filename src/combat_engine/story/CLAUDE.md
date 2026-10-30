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
| `objective.py` | what a fight is *for*, and what counts as failing it. |
| `loot.py` | what a scene hands the party, and the item refs they carry away. |
| `formation.py` | where the party is standing when a fight starts. |
| `tension.py` | the party's recent record, read back into the next scene's numbers. |
| `dc.py` | what a check has to beat, by level and band. |
| `beat.py` | a roleplay scene, one exchange at a time: who speaks, what they try, what they already know, what it changes. |
| `graph.py` | what a campaign knows: entities, facts, and where each fact came from. `docs/STORY_GRAPH.md` is the design. |
| `scripts/ingest.py` | an adventure's pages into a graph, locally, every fact quoted and checked against the page. |
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

### A synthetic probe does not reproduce a fault this component produces

**Eight for eight**, across six rounds of play-and-fix. Every fault found
by reading a transcript, put to an isolated probe, came back zero:

| fault, seen in play | probe said |
|---|---|
| the DM stages an off-stage person | 0/20 |
| the DM grants an impossible action | 1/9, and the 1 was a judge error |
| the DM narrates the player's character | 0/8, both arms |
| the DM uses the wrong pronoun | 0/30, three arms |
| the DM invents a party member | 0/8, and see below |

A live beat carries four companion declarations, eight lore rows, three
beats of recall and a cast of three. A probe carries one intent and one
NPC, and the fault lives in the difference. So **the transcript is the
instrument** -- `logs/<module>.campaign.jsonl`, read by eye -- and a probe
is only good for something already deterministic.

**And replaying the real beat is not enough either**, which is stronger
than the paragraph above and was learnt on #919. A DM that invented a bard
and a paladin in a party of five, 5 mentions over 18 live replies:

```
live playthrough, 18 replies                               5
synthetic beat, same NPC and intent, 8 samples             0
the 4 real logged beats, inputs read back from the log     0
the real beat with its real 3-beat history, 8 samples      0
```

Two traps in those rows. **A history-free replay is not an identical-input
replay**: `react` reads `playing.recent()`, which appends `"They answered:
{previous reaction}"`, so a fresh `Playing` silently drops part of the
prompt -- I claimed inputs were identical when they were not. And the
hypothesis that followed -- the DM is shown its own invention and repeats
it, which would explain four mentions from one origin -- is **refuted**:
the same beat with the bard in its history, against the same history with
the bard scrubbed, gave 0 in 8 either way.

So for a rare live-only fault there may be **no way to tell whether a fix
worked**, and that is a reason to ship nothing rather than to ship on
faith. See the next section for what the attempt cost.

What probes *are* good for, and it is not nothing: measuring a quality that
varies rather than a fault that is rare. The pronoun arms found 2/10 against
8/10 on *whether the DM refers to a character at all*, which is real and
shipped, while finding nothing at all about the fault that prompted it.

### A list of names is an invitation, and that outweighs the rule beside it

`Playing.cast()` says it about NPCs -- *"a name in a cast list is an
invitation to write them a line, and no instruction above it outweighs
that"* -- and #850 acted on it by keeping spare NPCs out of the prompt.
**The same thing is true of the party, and #919 proved it by doing the
opposite.**

The DM was never told who the party is: it gets `WHO IS HERE` for the NPCs
with a closed-set rule, and for the party only whoever declared something
*this beat*. A party of fighter, cleric, rogue, wizard and ranger was given
a bard in three places and a paladin in one. The obvious fix is to state
the roster. Measured, same seed, same 18 beats:

```
                  ghost mentions   real members named who did nothing
roster withheld          5                   1 / 18 replies
roster supplied          0                  36 / 18 replies
mean reply length      899c                1166c
```

Party members named per reply went 0.72 to 2.67, max 5 -- the whole party,
every beat, mostly doing nothing. The prompt forbids exactly that in two
places. Isolated on one beat the regression is **16 against 0 in 8
samples**, so unlike the fault it is reliably measurable, which is what
makes the trade legible.

A closure with **no list** -- one sentence pointing at the blocks already
present -- looked free on a synthetic beat (0 ghosts, 833c against 849c)
and was worse than the baseline on the four real beats: 1 ghost against 0,
16% longer. Both reverted; nothing shipped.

**What stands is a structural lead, not a prompt.** `chargen` deals
unnamed characters (#793), so the party's own names *are* class nouns and
the DM is already writing "the cleric", "the wizard". *"The bard"* is not
reaching outside the scene's vocabulary, it is continuing it. The
prediction is that this dissolves when characters have names, and it costs
one run on one seed to check.

### A judge is not always buildable, and six tries is enough

The faults in this component are found by **reading a transcript**, and
every real one this session was found that way. An automated judge was
tried six ways for one question -- did the DM narrate the player's own
character -- and the sequence is the argument against trusting one:

* a boolean judge failed both of its own controls, twice;
* an enum of `"the Fighter"` against `"somebody else"` scored 3/4 on a 7B
  and **3/5 on a 14B, failing identically** -- the tell that the model was
  not the problem. One option was a name and the other a description, and
  it reaches for the name. Naming both sides: 6/6;
* that judge then scored **0/8 on both arms** of the fix, because a probe
  with one intent and no companions cannot reproduce what a live scene
  with four declarations and eight lore facts does;
* pointed at the real transcript it reported **11%**, every instance a
  false positive on an NPC acting *toward* the player;
* given a category for that, it passed 5/6 synthetic cases and reported
  **22% on the same data it had called 11%**, top hit still plainly an NPC.

0%, 11%, 22% on one transcript, by prompt wording. That is not a
measurement, and the instrument was deleted rather than tuned -- the same
call `scripts/CLAUDE.md` demands for a check that cannot give a stable
answer. **Hand-reading found the real result in one pass**: the fault did
not recur in 11 replies.

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

### A prompt *reflow* is not free either, and it is invisible

Worse than the rule above, because an addition shows up in a diff and this
does not. Measured on `qwen2.5:7b`, temperature 0, the same classifier:

```
probe wrapping     5/5   "a rule for running the game session"
f-string wrapping  5/5   "something true in the world of the story"
```

The two prompts are **word for word identical** --
`" ".join(a.split()) == " ".join(b.split())` is `True` -- and differ only
in where the lines wrap. Each is **perfectly stable**, so this reads as two
different correct answers rather than noise from either side.

It happened innocently: the classifier in `scripts/ingest.py` was measured
with its prompt written as a literal, then shipped as an f-string
interpolating the two enum values, which reflowed the paragraphs. The
shipped version was **unmeasured**, and 2 of the 8 facts the measurement
was about flipped back to canon -- a graph built with it kept a sentence
about bringing a character sheet as a fact about the game world.

So: **keep a measured prompt a verbatim literal.** Never assemble one by
interpolation, `textwrap` or `dedent` over a reflowed source. When a
constant has to appear in both the prompt and a schema, write it in both
and have a driver assert the prompt still names it -- `drivers.py
graph_administration` does. And when two runs of "the same" prompt
disagree, diff the **raw** strings before concluding the model is
unstable; stable-but-opposite is this bug's signature.

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

## The DM writes to its budget, not to its instructions

Measured, and it settles a question that looked like prompt tuning:

```
200 tokens, as now         135 words   1/5 cut off
200 tokens, firmer ask     128 words   1/5 cut off
 90 tokens, as now          68 words   4/5 cut off
 90 tokens, firmer ask      67 words   5/5 cut off
```

The prompt already asks for "two or three sentences" and a "short
paragraph"; firming that up is worth seven words, which is noise. Halving
the budget halves the length and **breaks four replies in five**. So reply
length is not promptable here and a smaller cap only produces more ragged
endings -- 11% of the DM replies on record end mid-word, one of them on a
servant saying `"Father,`.

`_whole` cuts a reply back to its last finished sentence on the way out.
No length threshold: a first version kept the text whole unless the trim
left over 40 characters, which refused exactly the cases it was for.

## Invention is wanted; contradiction is not

**The ruling is in a comment on #830 and reverses the issue's own body**,
which is the failure the root `CLAUDE.md` opens by warning about:

> *"it's actually intended behavior for the DM to make things up and them
> to become canon. However, the made up facts MUST be consistent with the
> rest of the story."*

So the job was never to make the DM say "I never met him". The knighthood
it invented was not wrong for being invented -- it was wrong for killing a
man the party is hired to rescue alive. Three mechanisms, and the pattern
is the one that works everywhere else here: **supply the constraint, do
not request it.**

* **What the pages say is handed over.** `Standing` puts the adventure's
  own sentences in the prompt under "already true, do not contradict". A
  DM holding *"a man named Gordi who worked for the banker"* writes him
  missing, not dead -- verified end to end, and the same across beats.
* **A guard runs before invention.** `Director.would_know` asks how well
  *this* speaker would know *that* subject, as a three-way enum.
  `not at all` tells the DM to say so plainly rather than improvise; the
  other two licence it and set the register. Measured on twelve obvious
  cases, six each way: **12 of 12, balanced 6/6**.
* **What gets invented is written down**, tagged `invented`, so the next
  beat is bound by it too. Only for subjects that had nothing on record --
  a subject with page facts is not re-recorded, because the DM was told
  not to contradict those and storing its paraphrase beside them blurs the
  two.

**Only the player's line is mined.** A companion's intent came out of the
same model that is about to answer it, so resolving it feeds the model its
own output back as a thing to be consistent with. That is a loop, not
consistency.

Naming both failure modes in the guard's prompt was load-bearing. The first
version said only *"not at all is a common and correct answer"* -- written
to stop a tavern cook explaining a distant city's politics -- and it made a
gate sergeant ignorant of who runs her own keep.

## The graph answers "no", and that is what it is for

`docs/STORY_GRAPH.md` has the design; the short version of why it is not a
vector store. Top-k retrieval **never returns nothing** -- it returns the
nearest thing, which is "do not stretch an intent to fit an affordance"
recurring one layer over. A lookup that resolves to `None` is what makes
*"I never met him"* a true answer instead of an invented biography (#830).

So `Graph.find` is exact after folding case, accents and a leading article,
and a near miss **misses on purpose**. Breaking that -- making a miss fall
back to any entity -- turns four assertions red.

**Every fact carries where it came from**: `page` with a verbatim quote and
a page number, `earned` for a module fact paid for with a die roll, or
`invented` for something the table made up. Three things follow and all
three are the point: an invention stays consistent on the next mention,
stays distinguishable from canon, and stays reversible. A provenance the
loader cannot read is **refused**, not defaulted -- guessing would launder
an invention into canon or throw away a citation.

**An empty `told_by` withholds.** The first draft read it the other way and
a lookup handed back the chapter's twist, because nothing was marked
unsayable. Knowing and telling are different; only telling reaches a
prompt.

Measured on the module in hand: **96% of what the extractor offers can be
pointed at the page**, the 4% that cannot is paraphrase rather than
invention, and the quote is stored as the page's span rather than the
model's text. Two pages give 21 entities in 74 seconds on the desktop 14B.

**The quote is the fact.** Asking for a one-sentence gloss as well got the
entity's own name back in **38 of 38** cases, so the gloss was deleted
rather than argued with: the page's own sentence is better than a
paraphrase of it, is already validated, and removes the only place in the
stage where the model could write something the adventure does not say.

## What the party already knows is ranked by the page, not by the dice

`Lore.after` stopped the tavern ladder firing before the player had
spoken. It did not stop it arriving **all at once**: over 25 seeds the
unlocking beat delivers **7.7 of the 8 rows**, all eight in 17 of 25.
Eight unheaded "You know:" lines is a wall a reader cannot rank.

**Nothing is capped**, and that is not timidity: each row rolls against
its own DC, so the number arriving is the dice and the party's skills
rather than a number to choose. What changed is the order and a heading
with the count in it.

**Two rankings were tried and the obvious one is wrong.** How many of the
party knew a fact separates beautifully -- 28 facts known by one character
of five against 14 by all five -- but it is *this run's dice*, so the same
scene reads in a different order every campaign and no fixture can pin it.
Measured: two seeds printed the seven facts they shared in different
orders. The **DC** is the author's own statement of obscurity, it is
stable, and on this adventure it is literally a printed ladder -- 8, 12,
12, 12, 12, 15, 15, 19 -- so walking it upwards is the escalating detail
the page intends and it ends on the one somebody had to be good to find.

The same mistake lives one level down: four rows share DC 12, so a
dice-dependent *tiebreak* reorders that tier every campaign. `sorted` is
stable and `_recall` walks `scene.lore` in order, so a **one-key sort**
leaves each tier in the order the adventure prints it. Knower-count
survives only where it says what the DC cannot -- "Only <name> knows", for
a fact exactly one character got.

**A scene carrying only `lore` used to be skipped entirely.** `_roleplay`
returned early unless the scene had affordances or NPCs, and `lore` is a
third thing an author can write -- so its facts never rolled and the
player was never told them, silently. Isolated by adding one NPC to an
otherwise identical scene: 0 recall lines against 3. It never bit because
the one converted module puts all 8 of its rows on a scene that has NPCs.
#918.

## What the DMG has that we do not

Read 2026-10-29. Three gaps found by reading it against what is built,
each filed rather than fixed:

* **the complexity table has an `Advantages` column** -- 2 at complexity
  3, 4 at 4, 6 at 6 -- and `module.COMPLEXITY` drops it. Latent: both
  converted challenges are complexity 1 and 2, which grant none. #939.
* **quests are a third of a level's XP structure** -- the DMG budgets
  "six to eight encounters, one major quest, and one minor quest per
  character" -- and nothing models one. The converted chapter prints two
  with XP and awards neither, so its stated total is unreachable by
  construction. #940.
* **a challenge inside a fight is a printed shape**, not an oddity of the
  one adventure: *"for challenges that work as part of a combat
  encounter, set the complexity lower."* On #922, with the action
  economy answered too -- the adventure's three skills are each a
  standard action and two require being adjacent to a specific object,
  neither of which a scratch board can express.

One thing the DMG **confirms rather than contradicts**: Camille's #830
ruling that the DM may invent and the invention becomes canon is the
book's advice as well -- *"when you say yes, you open more
possibilities."* The constraint we add on top, that an invention may not
contradict the page, is ours and remains right.

And one number worth not re-deriving: the DMG's printed complexity table
gives complexity 1 **two** failures, while the compendium's errata'd
version drops the failures column entirely and the converted adventure
says three. `challenge.py`'s "three failures, and that number does not
move with complexity" matches the compendium and the adventure, which is
the right pair to follow.

## Monster knowledge is deliberately not implemented

Camille's ruling, **2026-10-29**, verbatim, on #987:

> *"For now, I think I want to leave monster knowledge checks unimplemented
> and have the combat board provide omniscient information."*

The printed rule it declines is in the Player's Handbook's Knowledge Skills
section: Arcana, Dungeoneering, History, Nature and Religion each identify
certain kinds of monster, and *"the DM might also use your passive check
result with skills such as Arcana or Dungeoneering to decide **how much to
tell you about a monster** at the start of an encounter."*

So the board shows what it shows regardless of who is looking. **Do not
build a gate in front of it**, and do not file this as a gap -- it is a
decision, not an omission. Recorded here because nothing else would stop a
later reader finding the printed rule and "fixing" it; there is no issue
open against it to carry the note.

What this does **not** rule out, and the distinction matters: `beat._recall`
already rolls knowledge skills against `Lore` rows to decide what a
character *remembers about the story*. That is the same five skills doing a
different job -- facts an adventure wrote down -- and it stays.

## A fight can be for something other than killing everything

Camille's call, **2026-10-29**, after reading another system's
encounter-objective rules:

> *"I'd like these encounter objectives to be represented in encounter
> design in this project. [...] you don't need to do a 1:1 conversion. This
> is more of a generic DM advice thing."*

So `objective.py` is the concept, not a port: **a stated goal, a stated way
to fail it, and one step along the difficulty ladder.** No imported
currency, no imported formulas. `plans/20261029-encounter-objectives.md`
records every translation that was made.

Five kinds, and the dividing line for which exist is **whether the board
can already answer the question**: `defeat_all`, `diminish`, `defeat_foe`,
`survive`, `hold`. All five read counts, rounds and squares. None needed a
new component, a new action or a change under `engine/`.

**`None` and `defeat_all` are different answers and both are legal.** A
scene stating no objective builds no watcher and keeps the original
`winner is Team.PC` line, bit for bit; naming `defeat_all` runs the watcher
and has to agree with it. That is the only reason the control in
`objective_verdict` can exist -- collapse the two and there is no way to
field a fight that does *not* go through the new code.

### Three faults it had before any driver was written

All three were found by probing it by hand and reading the output, which is
this component's own rule and worked again:

* **the denominator was counted after round one.** `began_with` was taken at
  the first `RoundEnd` and its docstring argued that was better. Anything
  that died during round one had already left the count, so `diminish`
  asked the party to halve an *already reduced* cast -- reported *"2 of 4
  are down"* for a fight that began with six. Counted at `attach` now.
* **winning early read as failing.** `survive` and `hold` were `rounds >=
  aim.rounds` alone, so a party that wiped the cast in round 4 of a
  five-round hold was told it had failed. You cannot fail to outlast a
  fight you have already won, and on these boards winning early is the
  *common* case because `Encounter.finished` ends the loop the moment a side
  is gone.
* **one fight reported two round counts.** `world.round` has rolled over by
  the time the loop head sees `watch.resolved`, so a two-round `survive`
  printed `rounds=3` beside a verdict reading "2 of 2".

### And one objective was built and then removed

**`assault` -- take and hold a position -- could not be met on these
boards**, and the measurement is the whole argument: every arm reported
`0 of N consecutive rounds`, including the one where the party stood in the
area having killed everything. Two reasons that compound.
`Encounter.finished` ends the fight the moment a side is gone, so there is
at most **one** boundary at which the party holds a cleared area and never
the three a duration asks for; and a round cap as a resolve condition cuts
the fight short before the area can be taken at all, so one field was doing
duty as a deadline *and* as a hold counter.

What it wants is a fight that continues around the party -- reinforcements
arriving while the position is held, #962. **An objective that cannot be
met is worse than one that does not exist**, which is the same call
`a-selected-feat-must-take-effect` makes about a drawable-and-inert feat.

### The difficulty step is one band, and it is printed

An objective may declare `harder` or `easier`, and `cast_list._stepped`
moves the scene one place along `DIFFICULTY` before the budget is spent --
so an objective can only ever buy what the module could have asked for by
writing a different band. Both flags together is refused at load rather
than cancelled out, because an author who wrote both meant one of them.

**A scene that states its own `xp` is not re-priced**, which is the same
call #798 made for party size: a module that prints a number for its own
encounter is more trustworthy than our curve. And the step goes in
`Dressed.notes`, because a budget that moved in silence is the fault this
component is told not to commit.

Two numbers worth not re-deriving. At level 4 a roster of three standards
and four minions is **affordable at `standard`**, so `harder` buys nothing
and the cast is identical either way -- the band only orders a roster big
enough to be clamped, and at six and six it is strict: 4 / 5 / 8 / 12
across the four bands. That is why `objective_budget` uses the larger
roster.

## A skill challenge never stops the plot

Camille's ruling, **2026-10-29**, verbatim:

> *"Skill challenes should never prevent the plot from progressing."*

The code obeys it by one `or` in `run.step` --
`made.next_id = wanted or module.next_of(scene, choice)` -- so a module
that names a success branch and no failure branch falls back to the
ordinary exit instead of stranding the party. Nothing asserted that until
`drivers.py challenge_progresses`, and deleting the fallback ends the
campaign silently on any failed challenge.

**The book says it too**, which settles that this is the rule rather
than a house preference. The DMG, on a failed challenge:

> *"at worst, failure at the challenge should send the characters on a
> long detour, thereby creating a new and interesting part of the
> adventure."*

A **route** consequence, not a stop: more scenes, not fewer.

**And the adventure agrees.** Both of its challenges continue either
way:

| | success | failure |
|---|---|---|
| chapter 1 | the fires go out, every token removed | the fires burn through the whole fight -- and the module awards the challenge's experience either way, which it says in as many words |
| chapter 4 | good time, they reach the stones by mid-afternoon | rough going, **each character loses a healing surge**, and they reach the same stones late |

Chapter 4's two outcomes name **the same next encounter**. A challenge is
a toll on the way through, not a gate.

**What a failure costs is a resource, a condition or a longer road, never
the road itself**, and
neither of those is modelled: chapter 1's result should add or remove a
spreading fire hazard *in the fight it runs during*, and chapter 4's
should take a healing surge from each character. Today a challenge's
outcome changes nothing but a line of text.

**And the validator only checks reachability inward.** It reports a scene
nothing leads *to* and says nothing about one nothing leads *out of*, so a
challenge can be authored that is entered and never left -- measured on a
two-scene module that parses clean.

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

**Knowledge the module gates behind doing something uses `Lore.after`.**
The tavern ladder is introduced as *"checks around the taverns that
evening"*; ungated, all eight facts fired on the opening beat before the
player had spoken. Won, not attempted -- a failed check unlocks nothing,
and with a gate the party always passes `found` and `spent` are the same
set, so that distinction needs an unreachable DC to test and the break
stayed green until it got one.

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

## A book is not all adventure, and the extractor must say where it stops

The PDF carries three kinds of page and only one of them is the module:
the **adventure**, the **publisher's own voice** (credits, trademarks,
photocopy permissions), and **organized-play administration** (how to
award renown, what to do when a character dies, pre-generated character
sheets). All three are set in the same fonts and all three read as prose.

Both stages were taking all three, and each needed its own fix because
**they read different inputs**:

* `importer.read_aloud` reads the PDF and filtered italics by length
  alone. 9 of its 80 blocks were a credits line repeated on three pages
  and the character sheets at the back -- 153 to 791 characters, so length
  was never going to separate them. Now `CREDIT_MARKS` (two or more of
  `(TM) (R) (C)` in a block) and `HANDOUT` (a page that offers itself for
  photocopying yields nothing). 80 blocks to 71, and the #902 baseline in
  `leaks.py` went from three waivers to **none**. #909.
* `scripts/ingest.py` reads `pages/*.txt`, **not** `read-aloud.json`, so
  the fix above does nothing for it. Administration was ingested tagged
  `page` -- the provenance that means *canon, do not contradict* -- and
  `beat.standing` hands those to the DM under "already true". The words
  that reached it were not obscure: **"the characters" resolved to a
  sentence about which character sheets to bring to the table**. Now an
  exact `CONTENTS` test plus a closed-list classifier, `_about_the_world`.
  #915.

  **The issue's own census was a 3x over-count, and the proxy is why.** It
  said "44 of 126 entities", measured as *entities sourced only from pages
  0-9*. Pages 6-7 are the **Adventure Synopsis** and pages 8-9 the session
  overviews -- the keep's legends, its cast, the cult, the villain's plan --
  which is story. Acting on the page range would have deleted about 35 real
  facts to remove 16. The real figure is ~10% of facts, and the exposure the
  issue reported is real and is caught. A page range was wrong twice here:
  once because the publisher nested administration inside the chapter, and
  once because the synopsis sits in the same pages.

Three things learnt that are worth not re-deriving:

* **A filter here cannot name what it filters.** The credits line is
  trademarks, and the root rule binds a filter pattern as much as a
  column. Match the marks, not the products.
* **Page spans do not separate administration from adventure.** `draft()`
  computes them correctly from the outline and the publisher nested the
  administration *inside* the chapter -- the depth-0 span is pages 1-7 and
  swallows three admin sections.
* **Register does not either.** Admin addresses the reader, so a
  second-person test looks promising and measures **44% against 22%**,
  with false positives like *"you arrive at the keep"*. A 2:1 ratio is not
  a separator.

And one about repetition, which is the signal that looks cleanest and is
wrong: three read-aloud blocks repeat across pages and **one of them is a
real item description**, printed twice because the item appears twice.

### A third kind: a span on an adventure page that claims nothing

Separate from both of the above, because it fires on pages that are
unambiguously the adventure. **18 of the chapter-1 graph's 188 facts were
page furniture** -- six treasure-table rows, two section headings, nine
map-key legends, and an artist's credit held as a `person`. `_a_claim`,
three exact shapes, 126 entities to 115 and 188 facts to 170. #916.

**An exact shape beat a verb test, and the reasoning generalises.** "A
fact is a claim and a claim has a verb" sounds righter and measured worse
on both counts: less complete, because a map key and a table row usually
end in a plural noun so `[a-z]+s` saved seven of them, and it had a false
positive on real prose -- a five-word sentence whose only verb was a bare
infinitive. 14 with one wrong against 18 with none. When a pattern is
exact on the page, prefer it to a rule about language.

What it drops that is a real loss: seven creature entities whose only
fact was a map key. That is **encounter composition** -- which tokens
start on which map -- and it belongs to the module's fight definition
rather than to a record of what the pages say. `MECHANICAL` argues the
other way for a creature and is a different case: there the creature has
a sentence and only its *name* looks mechanical.

## A board can be borrowed, and the party on it has to be found

`table.lay` builds a board with nobody to fight on it. `table.borrow`
wraps one somebody else built -- a fight's -- so a challenge and a fight
can share one world and one bus, which is what a trait firing when a
challenge ends needs. `lay` is a caller of it. #911.

**Finding the party on a board you did not spawn repeats `harvest`'s
rule, and cannot share it.** `harvest` lives in `story/__init__.py`,
which is arcade mode's and which this component imports and does not
edit, and `table.py` already imports from it -- so the dependency cannot
run the other way. `characters()` carries the same `c:` ident filter and
`drivers.py borrowed_board` is what keeps the two from drifting.

That guard needed two attempts and the first was useless: it asserted
only that no sheet took the familiar's hit points, which tests `harvest`
and not `characters`. Breaking the ident filter left it green, because
the two rules are separate copies and only one had been broken. **Assert
the pairing** -- sheet *i* must describe the entity `characters` puts at
*i* -- and the same break turns it red.

Nothing uses the shared board yet; no scene kind can say "this fight also
runs a challenge". #922.

## A challenge is no harder than the party is numerous

> *As a guideline, make skill challenge complexity no higher than 1 above
> the number of characters in the party.*

**DMG2 page 52, read in the file rather than taken from the quote** — and
the quote was exact, word for word. Everything needed already existed:
`Scene.complexity`, `Module.party_size`, and a `validate` that already
refused a complexity outside the table.

Checked in `parse` rather than `_as_scene`, because the party size is the
**module's** and a scene does not know it — which is why the harder
refusal has existed longer than this easier one. The boundary is asserted
on both sides at three party sizes, since "no higher than 1 above" is
exactly the shape that gets implemented one off.

### Reading the page found a rule the quote did not carry

This is the root `CLAUDE.md` rule about quoted tables paying off on its
first use. **Page 85** carries a second, tighter bound that no issue
mentions: an in-combat challenge is capped at complexity **2**, and it
*replaces* monsters rather than adding to them — so a combined scene's
budget subtracts the challenge's worth from the roster. Filed as #1011,
to land with #922's combined scene kind rather than before it.

Also worth knowing: **DMG2 is in `resources/`**, 226 pages, extracting
cleanly. The filenames differ in an apostrophe — `Dungeon Master's
Guide.pdf` for DMG1 and `Dungeon Masters Guide 2.pdf` for DMG2 — so a
search for the apostrophe form finds nothing, which is probably why a note
on master says DMG2 cannot be checked. It can.

## A recurring character is the same person each time

> *Keep track of the way you have important NPCs act so you can maintain
> consistency if the same character appears again.*

We could not: `Npc` lived on a `Scene` and nowhere else, so the same
person across three scenes was three independent entries and nothing made
them agree. Only invisible because one session authored all six scenes and
kept them consistent by hand.

`Module.cast` holds the half that travels. The split is #944's own:
**`wants`, `voice`, `looks`** are the person's; **`knows`, `hides`,
`unseen`** stay on the scene, because what somebody tells you depends on
where you meet them. It is also the half `graph.py` deliberately does not
carry — a graph records what is *true* about a person, and how they are
*played* is presentation rather than fact.

Two calls:

* **A contradiction is refused, not resolved.** Preferring one side is how
  the drift stayed invisible: whichever value won, the other was written
  down and ignored and nothing said so. The message points at the cast
  entry as the thing to change. A scene restating the cast's own value is
  fine — the refusal is about disagreement, not repetition.
* **A name not in the cast is a walk-on, not an error.** #944 hoped a
  refusal would fall out for free; it only does if the cast is
  exhaustive, which would refuse every one-scene character. So a **typo
  still makes a second person quietly**, and that is asserted rather than
  left to be found.

### Two findings from one green plant

* **The `if not cast` fast path was dead** — with an empty cast every npc
  takes the walk-on branch and returns unchanged. Fifth guard of this
  shape on this branch; I keep writing one for a case the general path
  already handles.
* **And the control crashed rather than failing.** Checking what covered
  it showed the walk-on plant raising an uncaught `ModuleError` from the
  control's own `build`. Red either way, but a crash does not say which
  rule broke, so the control is two assertions now — accepted, then
  unchanged.

## The scene's text is read once, and details are spent

Camille, playing: *"I'm still seeing some repetition ... [the host] said
(again) that I can ask around about his reputation."* `react` opened its
prompt with `THE SCENE: {scene.seen}` **every beat**, and that text
contained a one-time offer — so the model was asked four times running to
react to a speech containing an invitation.

Measured on the finished chapter, **verbatim repetition was essentially
zero** (0 four-word phrases across three or more replies). So this is
topic recurrence with a structural cause, and the answer is to shrink what
the DM is holding rather than to instruct it harder.

The book's own model is a pool: *"you don't need to pile atmospheric
details into your very first description [...] break them out to add some
flair to your narratives as the adventure progresses."* So `sets` is read
on the opening beat and `Scene.details` is spent one per beat, each once,
through the same `playing.spent` mechanism `Affordance.once` uses. **A
spent detail leaves the prompt** — the offer stops being re-made because
it is not there to read.

`details` is roleplay-only, because nothing else runs the beats that would
spend them, and a pool written and never read is worse than no pool.

### What this asserts, and what it does not

The issue warns that this component has failed **eight times** to
reproduce a fault of this kind in isolation. That warning is about *model
behaviour*, so the assertions here are structural: the offer appears in
exactly one prompt, each detail in exactly one, and a pool smaller than
the scene goes silent rather than looping. Whether the prose repeats less
needs a live model and the issue's own count, which `check.py` cannot run.

And one green plant worth its own line: the refusal of `details` on a
combat scene was **verified by hand** while building the schema and never
asserted, so a plant that removed it passed. A check that exists only in a
past shell session is not a check.

## Losing a scene costs something, and the plot goes on

Camille's ruling — *"skill challenges should never prevent the plot from
progressing"* — was honoured, and that was the whole problem: a lost
challenge progressed **identically** to a won one. `on_failure` is a scene
id, so a module could branch or say nothing.

DMG2's answer is the same scene and a worse party, and `Scene.cost` is
that: a declared penalty charged on a loss with the **exit unchanged**.

Four calls:

* **Any kind of scene, not just a challenge.** #975's own comment makes
  the case — DMG2 names *"fewer healing surges or daily powers"* for a
  costly **combat** win and the body proposes the same list for a lost
  challenge, so keying on `Scene.kind` would build it twice.
* **The stake is said first.** DMG2's framing advice is to show the
  consequences of failure, so the cost is stated before the scene runs: a
  cost discovered afterwards is a punishment, one stated beforehand is a
  stake.
* **The exit is untouched**, asserted against the no-cost run's exit,
  because that is the ruling itself.
* **A `rest` cost is spent, not sticky.** It is the only cost that is not
  a number, so it sets a campaign flag — and the flag is cleared by the
  rest it denies. One rest is forfeited, not every rest; a flag nothing
  clears is a party that never rests again.

### Three green plants, three different mistakes of mine

* **Dead code** — `if outcome != "lost" or not scene.cost` had a second
  test that never mattered, because the loop below is empty when no cost
  is declared. Fourth instance of this pattern in a day.
* **A vacuous comparison** — the save round-trip used a campaign whose
  `denied` was already `False`, so `False == False` passed while a plant
  dropped the field on load. Same family as the `< 12` threshold in #971.
* **A plant placed where it could not stick** — twice. First
  `next_id = next_id`, which asserts nothing; then a real reroute set
  *before* `run.step`'s "Where next" block, which promptly recomputed it.
  A plant has to survive the code that runs after it.

And one assertion I kept knowing no local plant reddens it: a control that
surges stay `None` was wrong, because a challenge lays a board and
`strike` harvests concrete numbers onto every sheet. The baseline is the
same scene without a cost — which is a stronger claim anyway.

## A fight reached without a rest is scaled back

The sidebar offers two levers and **the page chooses between them by
saying who is deciding**:

> *If you're **designing** encounters in which you expect characters to
> move from one to the next without a rest, treat the two events as a
> single encounter. If the characters **surprise you** by running on to a
> new encounter without resting, it might be worth scaling back the new
> encounter a bit.*

A module is the authority on where its rests are, so a fight reached
without one is exactly that surprise — the second lever, and the smaller
intervention. `rested_since_the_last_fight` walks back through `visited`
and answers on whichever comes first: a rest means yes, a fight means no,
neither means this is the party's first fight.

Three calls:

* **Short or extended both count.** The phrase is *"the benefit of a short
  rest"* and an extended rest is strictly more, so distinguishing them
  would make a night's sleep worth less than five minutes.
* **A conversation is not a rest**, which has its own assertion because it
  is the case a module actually produces.
* **It composes with #977 and the product is clamped.** A losing *and*
  unrested party would take 0.72 — a third of the fight gone — and an
  unclamped product is the unbounded loop `tension.py` exists to avoid.

It needed no new state, which is what the issue predicted: `visited`
already holds the sequence and the module already knows each kind.

**Still unmodelled from the same sidebar**, both noted on #947: an
encounter-long effect lasting *"about 5 minutes"* across a second fight —
ours end with the `World`, which does not outlive one — and the reading
that an unrested pair *is* one encounter, which is the designer-side
lever this deliberately did not take.

## The party's recent record pitches the next scene

The printed system is a closed loop — *"adjusting DCs or encounter levels
to reflect the party's recent record of loss and gain"* — and this engine
ran it open. Every lever already existed and a campaign passed nothing to
either.

`Campaign.record` holds decided outcomes, `tension.footing` reads the last
`RECENT` of them, and two levers move: the `pitch` on an unstated-XP
fight's budget, and the primary band of a skill challenge.

**Bounded is the design, not a safeguard on it.** `footing` is only ever
-1, 0 or +1; twenty losses are no more generous than two; the window is
short so old losses stop counting once newer wins push them out. An
unbounded loop that eases after every loss converges on a game nobody can
lose, which is the opposite of tension and release.

Three things it does not touch: a module's **stated `xp`** (asserted
byte-identical whatever the record, so a published encounter stays the
encounter the page describes), `Scene.difficulty`, and `api.day.scales`.
And nothing silently — every adjustment is a `note`.

### Two faults my own probe caught, both of which read as working

* **The band shift was inverted.** `BANDS` runs easy→hard, so tightening
  must *raise* the index; subtracting gave a cocky party easier checks and
  a struggling party no change at all. Invisible until both directions
  were printed side by side.
* **The fight note overstated.** It claimed the scene was pitched harder
  when the roster had not moved, because **the budget is a ceiling**: a
  module asking for fewer creatures than it allows is unaffected. Measured
  — a 10-creature ask fields 3/4/5 by footing, a 3-creature ask fields 3
  regardless. The note says so now, and only the fight note carries the
  caveat, since a pitched band moves every primary roll.

And one green plant worth copying as a lesson: comparing **twenty** losses
to **two** tests nothing about the window, because both ease. The
discriminating case is old losses with newer wins on top.

## The party stands where its marching order says

Placement was `chargen.spawn` at `(2, 3 + i*2)` — a column at x=2, two
apart, in whatever order `party.sheets` happened to be in. The players
never chose, and the rules say they should.

`Campaign.formation` is a band per slot from `formation.BANDS` plus a
`spread`, resolved against the real starting corner by
`formation.squares`. An order and a number, never coordinates — the same
reasoning `objective.POSITIONS` is built on: a player knows "front" and
does not know the board is 16x12.

Four calls:

* **The default is byte-identical to the old expression**, which is what
  keeps the eight replay fixtures still. That is load-bearing rather than
  polite: a placement change moves every fight, so getting it wrong would
  look like a placement feature and land as eight re-recorded baselines.
* **`by_role` is offered, not imposed.** The page's advice — defender
  front, leader back — is a classmethod nothing calls by default, because
  imposing it would move every existing party and that is a balance change
  wearing a fidelity fix.
* **A controller goes middle**, though the passage does not name one: the
  same sentence calls a front defender *"protecting your controllers"*,
  which puts them behind the defender rather than at the back where the
  leader is wanted.
* **A spread of zero falls back to the printed default**, not to one. Zero
  is an unset value; a player wanting shoulder to shoulder writes 1.

### The two green plants were both faults from earlier the same day

* **Dead code.** The `if plan.bands else 0` guard did nothing, because
  `band()` already answers `middle` for an unset slot and middle's offset
  is 0. Removing it changed no behaviour — the same shape as #970's
  parallel `matched` list.
* **The wiring hole from #945, verbatim.** The board assertions called
  `field_encounter(squares=)` directly, so a plant that computed the
  squares and fielded the old column anyway **stayed green**: `_fight` is
  what has to pass them. `Step.stood` records where the party actually
  stood, off the board, and three assertions go through `run.step`.

The transferable part is not "remember the wiring". It is that a
helper-level assertion and a wiring-level assertion are **different
claims**, and writing the probe against the helper is the path of least
resistance every time.

## Hours in the cold cost healing surges

A surge could only ever be lost to a fight, and the rules have another way
to spend one — which **six content rows across six files already said in
their own docstrings**: an inert racial trait, a level-4 daily with an
empty body, a marked item power, and two monster traits noting there was no
rule for them to switch off.

`Scene.exposure` names dangers from `DANGERS`, `Scene.hours` says how long,
and `run.weather` rolls Endurance every `EXPOSURE_HOURS` against each.
A failure spends a surge; with none left it costs hit points equal to level.

Four calls:

* **Fixed DCs, not a level band.** `dc.py` scales with level because a
  challenge is pitched at the party; weather is not, and the page prints
  one DC per condition. Reading these off `dc(level, band)` would make
  frigid cold *easier* for a stronger party.
* **A check per danger**, so a mountain in a snowstorm rolls twice as
  often as a still mountain.
* **+2 while sheltered**, which is the only reason the scene kind is
  consulted — an extended rest is *"resting and not exerting himself"*.
* **Rolled on the board, spent after it is struck.** `Table.strike` calls
  `harvest`, which writes the board's own surge count back over every
  sheet, so a surge subtracted while the board was live is silently undone.

**Deprivation is not here.** The rule of three — three weeks without food,
three days without water, three minutes without air — needs a surge pool
that remembers *why* a surge went, because one lost to thirst does not
return until the character drinks and `Sheet.surges` is a single integer.
That half stays on #971, as does the per-round breath-holding check, which
is the engine's.

### Four of ten plants stayed green, and every one was a weak assertion

The clearest set of examples this file has, so they are worth keeping:

* **A guessed threshold.** `surges < 12` passes for any class whose pool is
  smaller than twelve. It now measures against a pool harvested the same
  way, and additionally asserts that every surge the notes *claim* was
  spent is one the sheets actually lost.
* **Matching the wrong line.** The per-danger assertion looked for the
  danger's name anywhere in the output, and the summary line carries it
  either way. The note states the **product** now — checks × dangers —
  which a one-danger implementation cannot print.
* **An `or` escape hatch.** `hp < max_hp ... or any("takes" in notes)` let
  a plant print the line and skip the subtraction.
* **And one plant was simply wrong**: setting a surge count before
  `strike()` proves nothing, since `harvest` overwrites it either way.
  Never striking the board is the real test of "harvest before spend".

## A name nobody has heard of still reaches the DM

Camille, playing 2026-10-29:

> *"I asked about the relationship between Khellis and Orveth and got no
> answer, not even an 'I don't know'."*

`one_beat` built `Standing` from `layer.mentions(said)` — entities the
graph already holds — so a name it has **never heard of** produced no entry
at all. `would_know` never ran and its `not at all` register, *"say so
plainly rather than improvise"*, could not fire. That branch worked only
for an entity that exists and has no facts, which is the case a player
needs it for least.

`unresolved(text, known)` picks the proper nouns the graph could not
account for, and they go through the same `standing()` call — which finds
no facts and asks `would_know`, exactly as intended.

Three things to know before touching it:

* **A capitalisation heuristic, not a model call.** `check.py` runs this
  loop with no model, so an extractor needing one would be untested on the
  path that matters. The failure direction is the mild one: a false
  positive costs one "nobody here has heard of that"; a false negative is
  the silence being fixed. Two driver assertions pin what it deliberately
  misses — a lower-case name, and a two-word name arriving as two subjects.
* **Two guards above it are deliberate** and both broke the first probe:
  the whole block is skipped when there is **no graph at all**, and it
  mines **only the player's own line**, because a companion's intent came
  out of the model about to answer it.
* **One dedupe layer, not two.** A plant that emptied `one_beat`'s list of
  graph-matched names **stayed green**, because the caller's `seen` set did
  the same job one line later. Dead bookkeeping no plant can redden is dead
  bookkeeping; `unresolved` takes names now and `seen` is what it filters
  against.

## A module can say the opposition did not see the party coming

The engine has had the surprise round since `Encounter.start(surprised=)`,
and **nothing in `story/` or `api/` ever passed it** — so every campaign
fight began with both sides equally ready while the converted adventure's
own read-aloud describes a creature dozing by a fire.

`Scene.readiness` takes the DMG's four states. `asleep` and `distracted`
surprise the defenders; `ready` is the default; `alert` is accepted and
**does nothing yet**, which is asserted rather than implied.

Three calls:

* **The Stealth contest is skipped.** The module states the state, because
  a converted adventure states it in prose rather than asking the DM to
  roll. So the printed Perception modifiers that only feed that contest
  are not carried, and a driver asserts their *absence* — a modifier
  nothing consults is this component's commonest bug.
* **A free round is a balance lever**, not just flavour, in a fight the XP
  budget sized for a fair start. So it is printed.
* **`Step.surprised` counts off the board after `start`**, never from the
  list handed to it.

### The plant that proved the last one necessary

`Step.surprised` first recorded `len(caught)` — what `_fight` *intended* —
and the driver's far-end assertion built its **own** encounter to check
`start(surprised=)` applies the condition. Both passed, and a plant that
computed the list and then called `start()` with no argument **stayed
green**: the one link the design rests on was the one nothing covered.

Counting the creatures that actually carry `SURPRISED` is the version that
can tell an intention from an effect. The general form, since this has now
happened three times in a day: *an assertion written from the passing case
tends to cover the passing case.* The plant is what says whether it was
ever load-bearing.

## The DM is told how narrowly a check went, never the numbers

The DMG names this failure and prints our own output as its example —
*"That's 26 against AC," "You hit, now roll damage," "31 points"* — and
prescribes using the numbers as narration material instead. `react` was
handed the module's facts and nothing else, so it could say *what* was true
with nothing to write *how* from.

A ruling that rolled now reaches the DM as `fact (barely)`, from the closed
set `MARGINS`. Three calls:

* **Derived, not asked for.** `margin()` computes the word from numbers the
  engine already produced, so it cannot be wrong the way a model's guess
  can. Same discipline as matching an affordance against an enum.
* **The arithmetic is still withheld**, and this is the assertion the issue
  is about rather than the margin itself. No total, no d20, no DC reaches
  the prompt — a number in a prompt is a number the model quotes back,
  which is the rut the chapter describes. Fixing *"26 against AC"* by
  handing over 26 would have been the obvious wrong fix.
* **`CLOSE = 3` covers both directions**, so a near miss is not narrated as
  a rout. The fact itself says which way it went, so "barely" is never
  ambiguous beside it.

The prompt also says the bracketed word is a margin to write into the
picture and must never be printed — which has its own plant, because an
instruction nothing checks is an instruction a reflow can delete.

**Not done: the combat half**, which is bigger and still open on #943. A
story fight prints `Won in 4 rounds` and sends the blow-by-blow to a
transcript nobody reads during play; there is a whole encounter of this
material and none of it is narrated.

## The budget clamps to what the database holds, and says it did

`story.budget` reads a standard monster's XP out of `game.db`, which stops
at level 13 by deliberate ETL decision. Above it the function returned
**0** — and every division downstream guards itself with `max(aim, 1.0)`,
so a module validated for a paragon party got a budget of nothing and the
fight fielded nobody without raising. `budget` clamps to `ceiling()` now
and `cast_list.resolve` reports the clamp.

Three calls:

* **The ceiling comes from the database, never from `etl`'s constant.**
  `story` importing `etl` would break a contract `.importlinter` holds, and
  `db.py` is below every component for exactly this.
* **Not computed from the printed curve**, though the printed table runs to
  level 40. A budget derived from it would name a figure `cast_list` cannot
  spend — fielding a level-20 encounter needs level-20 *monsters*, not just
  the number they are worth — so the scene would still field nobody while
  now claiming a target. Worse than a 0. The printed table is the answer
  for a quest or challenge reward at a level with no monsters.
* **`party_level` is still not bounded at validation**, deliberately,
  against #963's second suggestion. A module written for level 20 is a
  legitimate module this build cannot field; refusing it in `module.parse`
  would call it *invalid* rather than unplayable, and would put a database
  read into the one command a converter runs before anything is built.

And one correction to #963's wording, because the next reader will trip on
it: the scene was **not** silent before. `_pool` already reported that
nothing written fitted the level — that note comes from an empty pool and
has nothing to do with the budget. What was silent was the **zero**, which
is why the fault read as a `cast_list` bug.

## The dead stay dead on a revisit

`Campaign.visited` was recorded and read by nothing, so a scene the module
routed back to fielded its whole cast again — the party walked into a room
it had cleared and the dead stood up. The DMG states the rule twice, the
second time for exactly this:

> *Monsters the party has killed should (usually) stay dead — the site
> shouldn't just reset to the state it was in the first time around.*

`Campaign.cleared` is `scene id → ref → how many`, accumulated, and
`run.survivors` takes them off the roster before anything spawns. A fully
cleared scene is **skipped** with its own wording, because "the party
cleared this" and "nothing written could be fielded" are different faults
that read alike.

Two things worth knowing before touching it:

* **It is a count per ref, not a set of cleared scenes.** A scene fielding
  three of one creature that lost two must field **one**.
* **`refs` and `flavours` are filtered in step.** They run parallel and are
  zipped together twice downstream, so dropping a ref without its flavour
  dresses a survivor as whatever died.

The `(usually)` in the printed rule is latitude this does not spend: a
revisit fields the survivors, and the book's *"new threats"* reading — a
site that is **different** rather than emptier — is still open. A module can
express it today with a `flags` entry and a second scene.

### Two plants stayed green, and the code was what was wrong

The most useful thing to come out of this. The assertion claiming to test
count-versus-set **was not testing it**: `cast_list` never returns the same
ref twice for a generated roster, measured across five seeds, so through a
fight "decrement the budget" and "drop every matching ref" are the same
behaviour — and so are "accumulate" and "overwrite", because no ref ever
dies twice. Both plants passed while the assertions read correct.

So the subtraction and the recording are **named functions now**,
`survivors` and `record_fallen`, rather than six lines inside `_fight`.
That is not a test convenience: logic a probe cannot reach is logic nobody
can check, and extracting it is what made the distinction assertable. The
plant that followed — dropping a ref without its flavour — only became
possible to write afterwards.

## An extended rest is once per day, and the refusal is printed

Nothing bounded it: a campaign of three consecutive extended-rest scenes
took all three, in silence. The printed rule is a lockout —

> *After you finish an extended rest, you have to wait 12 hours before you
> can begin another one.*

— and **scenes are what we have, not hours.** `Campaign.clock` is
deliberately not a real clock, so `_already_rested` asks the coarser
question the issue proposed: has an extended rest happened with *nothing
since*?

Four calls:

* **A short rest does not launder one.** The walk steps past a short rest
  rather than stopping at it — the lockout is twelve hours and a short rest
  is five minutes.
* **A refused extended rest is still a short rest.** The page stops another
  extended rest *beginning* and says nothing against five minutes, so
  giving the party nothing would invent a harsher rule than the book.
  Refusing outright is the other defensible reading; what is not defensible
  is doing it silently.
* **Derived from `visited`, not counted into a field.** One source of truth,
  and no second number to keep in step.
* **The refusal does not print the benefit it declined to give**, which was
  a real bug in the first draft — the unconditional line underneath said
  "Extended rest: everything back" directly below the refusal.

**The assertion that matters is not the refusal.** An extended rest resets
the milestone counter, so an unbounded one lets a party reset it at will and
`c.milestone()` is 0 for ever — quietly undoing #968. A driver that only
checked for the printed note would not have seen it.

Still not modelled, both from the same pages and both needing a real clock:
**sleep gating the benefit** (*"if you haven't slept at least 6 hours in the
last 24, you gain no benefit"*), which is the printed mechanism for denying
a rest that #979's pacing wants; and **a short rest renewing a power used
during it**, which is only reachable once something can act in a rest scene.

## A scene can happen on the clock, unless the party stopped it

`Scene.exits` could only say "when this scene ends", so nothing could
happen *to* a party. `Module.timeline` now can — the DMG's structural tool
for an adventure that is not a dungeon, and the half that keeps it from
being a railroad is the `unless`:

> *events on the timeline could trigger **unless** the characters manage to
> prevent them*

An entry is `(when, unit, scene, unless, says)`. Two units — scenes played
and extended rests taken — because those are the units the book's own
examples use, and a tick per scene transition is the coarsest thing that
expresses any of them. **Deliberately not a real clock.**

Five calls worth keeping:

* **`unless` is read before `when`**, so an event the party prevented early
  is retired rather than sitting pending for the rest of the campaign. It
  takes a scene id they played *or* a module flag that is non-zero, so a
  consequence recorded anywhere can stop one.
* **A cancellation is announced**, not silent. Having prevented the thing is
  the payoff, and a silent cancel is indistinguishable from an entry nobody
  wrote.
* **`says` is told to the players**, because DMG2 is explicit that a
  deadline is useless as pacing if it is a secret: *"Tell the players up
  front."*
* **A timed scene is a reachability root.** Nothing exits to one by
  construction, so without this every entry reported "nothing leads to it"
  and the one genuine orphan was lost among them.
* **The override replaces the scene's exit rather than deferring it.** A
  timed scene carries its own `exits`; a module that wants to resume the
  interrupted thread exits back to it. Remembering the displaced exit needs
  more campaign state and a rule for what happens when the timed scene has
  exits of its own — more than a first version should decide.

**Not done here: prohibitions.** DMG2's inverse — the extended rest a party
may *not* benefit from until some condition is met — is #993, where the
printed 12-hour lockout already lives. A prohibition is a predicate on
`Party.rest(extended=True)`, and that is the right place for it.

### The probe needed fixing before it could prove anything

Worth reading before writing the next one here, because it cost real time:

* **An unbounded campaign walk hangs instead of failing.** Remove the
  `fired` guard and `_due` returns the same scene for ever, so
  `while not campaign.finished` spins — and `check.py` waits on it with
  nothing to read. The walk is bounded at 40 and reports the overrun.
* **A plant that crashes the probe proves less than one that reddens an
  assertion.** Two of twelve did, and both were fixable: the orphan
  assertion sat *after* probes its own plant makes fail validation, and the
  control plant returned a scene id the control module never declared. An
  instrument that dies before reaching the relevant check is evidence that
  something changed, not that the check works.
* **And a killed plant run leaves the tree broken in a way grep will not
  find.** One did, and a search for `if False` and an intact `fired` guard
  both came back clean while `if not module.timeline: return 's2'` sat in
  `_due`. The break script writes an `IN_FLIGHT` sentinel naming the
  applied plant now; the reliable check is whether the driver still passes,
  not whether a signature is absent.

## Two encounters are a milestone, and the count is weighted

`world.milestones` existed, `c.milestone()` read it, and arcade mode set it
from its finished legs — **`story/` never did**, so every story fight
answered 0 for the whole module and the milestone's printed action point
reached nobody. Camille's ruling on #666 is the printed rule word for word,
so there was nothing to decide: every two encounters between extended
rests.

Four calls worth keeping:

* **The count is weighted, not `done // 2`.** The page says a fight two or
  more levels below the party must not contribute and one four or more
  above counts as two, so `Scene.counts_toward` returns 0, 1 or 2. Only a
  `combat` scene counts at all — the same page excludes quests explicitly,
  and a conversation is not an encounter either.
* **It lives on `Campaign`, not `Party`.** A fact about the day rather than
  about any character, and the extended rest that resets it happens in
  `run.step`.
* **`world.milestones` is set in `run._fight` before `encounter.start()`**,
  the same placement and the same stated reason as `api/day.py`: a trait
  reads it at arming.
* **The number is printed when it is non-zero**, which is what makes it
  checkable at all — it is otherwise read inside a world that does not
  outlive the fight, so nothing above could tell a board that got it from
  one that did not. This component's rule is that an unobservable effect
  gets an event rather than a harness that diffs state.

Two traps this hit, both worth knowing:

* **`Campaign` is hand-serialised** while `Sheet` round-trips through
  `asdict` and a tolerant filter. A new `Campaign` field written in
  `to_dict` and not read in `from_dict` resets silently on every load,
  which is what `encounters` did until a driver asked and read 0 against 2.
* **`DRIVERS` already had a `milestones` key.** A duplicate dict key keeps
  the *last* writer, so the first registration of the story driver ran the
  engine-and-arcade one instead and reported 21 green assertions about
  something else. It is `story_milestones`.

## A thing handed over in prose has somewhere to go

Camille, playing 2026-10-29:

> *"It looks like we were given healing poultices. I think this is likely
> prose only. When something like this happens it should be added to
> inventory."*

There was nowhere for one to go — `Sheet` had no inventory field — so a
scene could not grant an item even in principle. `Scene.grants` now lands
on the sheets through `loot.hand_over` and `Sheet.carried` holds it.

Four calls worth keeping:

* **A grant takes the page's name *or* the ref**, the same dual shape
  `Objective.foes` has, because a converted module writes what the page
  printed and the tracked fixture cannot.
* **An unresolvable word is reported, never dropped.** That is the whole
  original fault one layer down: swallowing it here would have reproduced
  the bug inside its own fix.
* **Round-robin from the first sheet**, printed rather than assumed. One
  consumable for four characters is one character carrying it; giving
  everybody a copy would mint three the page never printed.
* **Nothing spends one, deliberately.** #935 keeps using an item separate,
  and it is a real design question: the engine has `components.Item` (a
  held one-shot that dies with the board) and `Magic` (a worn slot), and a
  story-granted consumable is neither.

**Resolution is not done at validation time.** `--validate` is the one
command a converter runs before anything is built, so it must work with no
database; whether a word matches an item is a question for the moment the
scene plays.

## The page adjusts for party size by rule, and we had it as a table

#798 was filed as "the module adjusts each encounter by name". It does
not. Every chapter prints the same two paragraphs -- remove one
lowest-level non-minion for a weak party, add one of the non-minions
already here for a strong one -- and the per-encounter mention is an
*example*, not a specification. So there was nothing to author and the
whole thing is one function over the fielded list.

Three calls worth keeping: **one adjustment, not one per missing
character**, because the page says "remove one" and per-head scaling is
our curve again; **"least important" is not modelled**, because no stat
block says it, so lowest level is used and the note admits it; and it
fires **only for a scene that states its own XP**, since a scene without
one is already scaled through `per_head` and the rule on top would
double-count.

## Seams

* **`story/__init__.py` has now been edited twice**, and saying "one
  exception" would be the third draft of a sentence that keeps going
  stale. The rule is still worth keeping — arcade mode is built in
  parallel, so import from this file rather than changing it — but it is a
  rule with exceptions, which means **the bar is a stated reason in the
  commit, not an unbroken record**:

  | # | what | why nothing else would do |
  |---|---|---|
  | #935 | one field on `Sheet` | a granted item lives with the *wear*, and `Sheet` is the only record that survives a scene |
  | #994 | one keyword on `field_encounter` | placement happens inside it; the arithmetic lives in `formation.py` and the default reproduces today exactly |

  Both are additive with defaults that move nothing, which is the shape to
  keep. Measure the premise before the next one: the
  `sequential-encounters` worktree was last committed 2026-10-25 and has
  touched nothing under `story/`, so the collision this guards against has
  not been live all day.

  What the exception cost and why there was no alternative: a granted item
  has to live with the **wear**, because the wear is by definition what
  survives a scene, and `Sheet` is the only record that does. A new field
  on `Party` would have needed a save key; a field anywhere else would not
  have been carried. The edit is one additive field with a default, which
  is the lowest-conflict shape there is.

  And the premise was **measured before breaching it**, not assumed: the
  `sequential-encounters` worktree was last committed 2026-10-25 and has
  touched **nothing** under `story/`, so the collision this rule guards
  against was not live. Measure it again before the next exception — the
  answer changes the moment that branch moves.
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
    beat_loop scene_audience module_refusals affordance_match \
    summary_scenes boxed_text graph_furniture graph_administration \
    recall_order borrowed_board party_size_rule challenge_progresses \
    line_kinds objective_verdict objective_budget scene_grant \
    story_milestones timeline rest_lockout stays_cleared \
    budget_ceiling roll_margin readiness unknown_name \
    cold_hours marching_order tension unrested lost_costs \
    scene_once module_cast complexity_bound quests story_xp \
    graph_edges challenge_says fight_aftermath reinforcements \
    scene_allies trap_budget room_shape templates skill_cap \
    treasure
uv run scripts/check.py --only play,drivers
```

**The command above is 50 drivers and prints 622 assertions**, and **each was
proven by breaking what it watches** — the retype, the word grant, the
three-failure cap, the refusal of an unlisted skill, the read of
`Skills.trained`, the arming-is-not-spending rule, the `once` rule, the
scene ending, whose text becomes a fact, both halves of the brief/sets
split, each of the three furniture shapes, the contents pattern, the
classifier's call site, its `sort` flag and its keep-on-an-empty-answer
default, the DC sort, the lore guard, the cap that is not there, the
borrowed board and each half of the party-size rule. All went red.

Measured, because this sentence said "ten" for three commits after it
stopped being ten. `uv run scripts/drivers.py <the list above>` prints the
total; read it off rather than counting the names.

**And it had gone stale again, in the other direction.** It read *"25
drivers and 218 assertions"* while the command beside it listed **18** and
printed **169** -- so the number was counting drivers the list did not
name, and no reader could reconcile the two. Three were genuinely missing
from the list (`line_kinds` among them) and are in it now. Quote the figure
**the listed command prints**, or the sentence is unverifiable by the one
thing it tells you to run.

`affordance_match` is the one that needs a model and **skips** when none is
serving; the rest run offline.

**`module_refusals` exists because nothing read the validator's messages.**
`module.py` collects every problem and refuses with carefully worded text,
and no driver asserted a single one -- so breaking the `dc` type check to
coerce a nonsense value instead of refusing it left the whole suite green.
A refusal nobody tests is a refusal that can be deleted by accident. The
three it covers are the silent ones: a module that validates and then plays
wrong.

**A fixture can be too small to see the break.** `boxed_text` asserts that
a credits line is dropped by its trademark marks, and the first version of
its fixture ran **101 characters** against `READ_ALOUD = 150` -- so the
length filter dropped it, removing the mark rule changed nothing, and the
driver was **asserting the proxy it had been written to replace**. It now
asserts its own fixture is longer than `READ_ALOUD` before asserting
anything about marks. Where a new rule replaces an old one, the fixture has
to defeat the old one or the break stays green.

**Clear `__pycache__` between a break and its restore.** A restore that
lands in the same second as the `.pyc` does not invalidate it, so the tree
reads correct and runs broken — two drivers failed that way here and the
first three diagnoses were all aimed at the source. `find . -name
__pycache__ -type d -exec rm -rf {} +`.

One honest limit, because it is the kind of thing that rots: `training_bonus`
asserts the difference equals `TRAINING`, so changing the constant moves both
sides and it stays green. It proves the bonus is *applied*, which is the half
that was actually missing here (#565). Break the read, not the number.

## Quests carry a state, not a flag (#940)

The DMG lists quests first among what an adventure is made of, and sets a
level's budget as *"six to eight encounters, one major quest, and one minor
quest per character"*. The converted adventure prints two and **nothing
carried either**: both awarded nothing, and nothing recorded whether the
party had done them.

`Module.quests` is a list of `Quest(id, kind, xp, done_when, offered_by,
fails, says)`, and `Campaign.quests` is a **state per quest** —
`"" | "open" | "done" | "failed"` — rather than a set of booleans. That is
#940's comment, which is the whole reason for the shape:

> *You can present quests that conflict with each other*

Two active quests may be mutually exclusive, so completing one must be able
to **fail** the other, and a failed quest must stay failed when the scene
that would have completed it plays anyway. A flag would simply be set. That
is the assertion in the driver worth reading first.

Three things happen in `run.quests`, in order: a quest whose `offered_by` is
this scene opens; an open quest whose `done_when` matches this scene **or an
affordance won in it** is done; everything that one `fails` is failed. Each
is said out loud, because *"don't be shy about letting the players know what
their quests are [...] that avoids searching for the fun."*

**Any kind of scene may grant one** — the adventure grants one mid-combat,
so keying this on `roleplay` would have missed it. A quest with no
`offered_by` is open from the first scene, which is how a module states
something the party already has without a separate start hook.

Four refusals at parse time, each proven red: a `done_when` resolving to
neither a scene nor an affordance, no `done_when` at all, a quest whose
`offered_by == done_when` (*"don't reward the characters twice for the same
actions"*), and a `fails` naming a quest that does not exist.

**The XP is carried and not awarded.** `Sheet` has no XP field and nothing
here advances a character; that is **#967**. The figure is stored so the
award has something to read, and the line says `unspent` so nobody reads it
as working. The driver asserts both halves.

**What a green plant found**, and the reason that assertion exists: opening
*every* quest in *every* scene passed all thirteen original assertions,
because every quest in the probe is granted by the first scene it plays. The
driver now asserts a quest offered by a **later** scene is absent until that
scene, and is offered once rather than re-announced.

## XP is awarded and never spent (#967)

*"Experience points (XP) are the fundamental reward of the game, just as
encounters are the building blocks of adventures and campaigns."* Nothing
awarded any. `Sheet` had no `xp`, and a campaign played its whole module at
the level `Party.of` was called with.

`story/xp.py` holds the arithmetic and **every figure in it is read off
`game.db`** rather than written down — the reason `budget` gives one function
away: a table here can disagree with what the monsters are actually worth,
and then two numbers describe one rule. Three printed worked examples are
what the driver asserts against, because a computed figure matching a printed
one is stronger evidence than any shape assertion:

* a complexity-3 challenge at 7th level is **900 XP**;
* a 10th-level major quest pays **500 each**, *"regardless of how many
  characters are in the group"*;
* the cumulative advancement table — 1,000 / 2,250 / 3,750 / 5,500 / 7,500 /
  10,000 / 13,000 / 16,500 / 20,500 — which `10 * standard(level)` summed
  reproduces exactly for every heroic level.

**The two kinds of quest divide differently and that is printed, not an
oversight.** A minor quest is one monster of its level *between them*; a
major quest pays each character the same figure however many of them there
are. Everything else is *"divide the XP total for the encounter by the number
of players present"*.

**`WORTH` must never touch an award.** A creature's own row already carries
its rank multiplier — a level-1 solo is 500, which is five standard monsters
— so `WORTH` is for *spending* a budget, and applying it to a reward pays
five times over. There is an assertion pinned to that specific creature.

**An encounter has to have been overcome, and overcoming is not killing.**
The award reads `made.outcome`, which is where #964 put the scene's
objective, so *"killing, routing, or capturing"* all pay. God mode therefore
earns **nothing** — it fields nobody, so there was no risk and no opposition
to be worth anything — and that falls out of `made.enemies` being empty
rather than being special-cased.

**`Step.clean` is deliberately not read.** #964 recorded it saying the thing
that would pay for it is this award. Nothing printed pays more for a clean
win, so the field stays unspent; inventing a bonus would be this component's
own warned-against failure.

DMG2's **drama reward** is here and **off by default**, which is the book's
framing: *"you should grant drama rewards for vignettes only if you rely on
them in any given session."* Its unit is a beat in which an affordance
actually fired, because the book's exclusion list — digressing, idle chatter,
repeating, wandering off topic — is almost exactly the set of beats where
nothing was attempted. One award per scene, which is the anti-farming clause
as a cap rather than a judgement the engine cannot make.

**Nothing advances anybody.** `xp.ready` says a character has earned the next
level, the line is said once each, and `level` does not move. Applying it
re-deals a hand pinned on purpose, which is `chargen`'s and is **#1013**.

### What the plants found, which is most of what this section is worth

Twenty-one plants, nineteen red. Five assertions existed only because a plant
stayed green:

* **the mode** could not be posed at all. `standard()` takes the mode of a
  level's rows rather than the first one, and `LIMIT 1` returns the same
  answer at all 13 levels today — so a plant replacing the mode with
  `rows[0]` ran green. The selection is now `_mode()` and asserted against a
  list where the two differ. The plant *through* `standard` still cannot go
  red, and that is the honest state of it: **#1014** is the same fragility in
  `budget`, where a single stray row at level 10 would make an encounter 40%
  light in silence.
* **a lost fight** was never posed — the probe's party wins every fight the
  seed gives it, so dropping the `outcome == "won"` test changed nothing.
  Posed now by handing `reward` the step a lost fight produces.
* **the drama floor** and **the fired-affordance filter** both survived
  deletion, because every beat of the drama probe is substantial. Two scenes
  were added: one too short to qualify, one with plenty of beats where
  nothing is attempted.
* **the save** was round-tripped on a campaign where nobody had advanced and
  every sheet held 0 XP, so `[] == []` and `0 == 0` passed and two plants
  returning empties stayed green. It now round-trips the campaign that
  carries both.

And a probe caught `to_advance` returning one level's *increment* against a
cumulative `Sheet.xp` — ready at 1,250 instead of 2,250. The two agree at
level 1, which is where a first probe looks.

## The graph had no edges, and now reads as one (#934)

`Entity.links` existed, `Graph.around` read it, `docs/STORY_GRAPH.md` was
written as though edges existed, and the graph held **99 entities and 0
links**. `scripts/ingest.py` extracts entities and quotes and writes no edge,
so `around()` had never returned anything and the structure was a bag of
facts.

Camille, playing 2026-10-29:

> *"I asked about the relationship between Khellis and Orveth and got no
> answer, not even an 'I don't know'."*

**#933 fixed one half of that and this is the other.** #933 was a name the
graph had never heard of producing no `Standing` at all. This is both names
resolving and the answer *still* being two separate fact lists, because
`mentions` looks each one up independently and nothing asked about the pair.

### Two edges, and only one of them is invented here

`derive(graph)` draws an edge between entities named in **one grounded
quote**, relation `NAMED_WITH`, and that is the version the issue called
*"costs nothing at all"*. Measured over the one converted module: **207 edges
across 75 of the 99 entities**, with a degree distribution that looks like an
adventure rather than an artifact — 16 nodes with a single edge, a long tail
through the middle, and a few hubs that are the adventure's principal person,
its principal place and the party.

They are **unlabelled on purpose**. They say two things are connected and
hand over the sentence that connects them, which is what a DM can read for
themselves. `RELATIONS` names the five DMG2 organisation relations —
`led_by`, `based_at`, `enemy_of`, `rival_of`, `faction_of` — for whoever
writes the labelled pass, which has to come from the page. The
**Enemies/Rivals split is why an edge is typed** rather than a bare set:
*"openly or violently conflicts with"* against *"peaceful intrigue"* are
different answers to who opposes a group.

**Every edge is groundable in a span**, like every fact: the evidence is a
quote already extracted and already cited, so no edge exists without a
sentence behind it, and no model call is needed.

**A derived edge is never written to the file.** Only stated ones persist;
loading re-derives. Otherwise the file becomes the record of a derivation
rather than of what the page said, and a stale derived edge outlives the fact
it came from.

**One measured distortion.** A node carrying a generic alias is
over-connected by it — the party's own node has a one-word alias that appears
in a great many quotes, and that alone puts it in the top three by degree.
The edges are not wrong, but the node is central for a grammatical reason
rather than a narrative one. Do not read degree as importance.

### `RELATIONS` is a vocabulary, not a closed set

`from_dict` briefly **refused** a relation that was not in the list, by
analogy with the `kind` and `source` refusals. That was wrong twice: an
unknown relation launders nothing — which is what those two refusals are for
— and `around()` follows it perfectly well. It also broke a graph driver that
has been declaring a `lives in` edge since before the list existed. An
unrecognised relation passes through.

### Something has to read an edge

`ask()` has populated `Known.near` from `around()` the whole time and
**nothing in the tree read it**. A graph nothing consults is the same as no
graph, so:

* `Standing.near` carries the one-hop neighbours into the line the DM reads,
  capped at `NEAR = 6` — the busiest node has 33, and a prompt listing all 33
  crowds out the facts the line exists to carry;
* `linking()` answers the **pair** question from `Graph.between`, which
  returns the sentences naming both;
* a beat where **one line** names two known entities gets a pair `Standing`.
  **One line, not the beat**: `seen` carries every name from every earlier
  intent, so pairing off it ties together two things nobody mentioned
  together. One character asking about each is two questions.

And the negative case is the complaint itself: nothing connecting them prints
*"nothing on record connects them. Say so if asked; do not invent a tie
between them."* — the register #933 established, with the invitation to
improvise withheld.

### What the plants found

Twenty-one plants, nineteen red, one intended control green. Two findings
worth keeping:

* **`between` read only one side's facts** and every assertion passed,
  because every connecting fact in the fixture is filed under one of the two
  entities. The order a player names two things in cannot change the answer,
  so there is now an assertion that the connecting sentence filed under the
  *second* one is found.
* **a fact usually does not repeat its own entity's name** — *"He has never
  been to Fenn"* is filed under the person — so requiring both names in the
  span drops exactly the facts most worth having. The owner counts as named.

## A challenge says what each check meant (#932, step 1 of two)

A converted challenge emitted five mechanical lines and a tally:

```
- fighter   athletics     moderate d20=8  total=11  vs 12
+ cleric    athletics     moderate d20=13 total=14  vs 12
2/4 successes, 3/3 failures
```

The fires were never described going out or spreading, the sigils never did
anything, nobody said a word. Camille: *"I don't know that the result was
incorrect. But skill challenges should be an opportunity for narration."*

**The order here is the whole point, and it is #932's own.** An `Affordance`
carries `win`/`lose` — *facts*, what is now true because the roll went that
way — and `Director.react` is handed them and told to deliver them. That is
what keeps the DM narrating the adventure instead of inventing it. A
challenge's skills were **bare strings with no such text**, so wiring the beat
loop in first would have handed the DM a roll to narrate and nothing to
narrate from, and invented prose about the adventure's own set piece is the
one thing the affordance design exists to prevent.

So: `Try(skill, win, lose)` and `Scene.tries`, the text reaching the player,
and **the beat loop still to do**.

`primary` and `secondary` stay tuples of names, so every reader of them —
`band_of`, `attempt`, the validator — is untouched. A skill may be written
bare or as an object, **mixed in one list**, so a module adding prose to the
two skills the page describes need not rewrite the other four. Every converted
challenge is unchanged and prints exactly what it printed before.

Four refusals: an entry with prose and no skill; a skill listed as both
primary and secondary (`band_of` answers with the primary, so the secondary
entry and its prose were silently dead); a non-challenge scene stating what a
check means; and the skill name still checked in the new form, because a
second code path is exactly where that stops happening.

**Each sentence is said once.** The text is a fact, and a fact does not become
true again on the second success with the same skill — the first probe printed
one brazier toppling into the sand three times, which reads as three braziers.

### The guard that was nearly dead, and the seed that made it posable

`if made.rolled` withholds the text from a refused attempt, because a refused
attempt never happened. A plant removing it **stayed green**, and the reason
is worth keeping: for an *unlisted* skill `means()` answers with nothing
anyway, so on that path the guard carries no weight at all. The case that
needs it is a refused attempt whose skill **does** carry text — a secondary
spent twice.

Posing that took two corrections:

* the default chooser never refuses. Eight seeds of `taking_turns` produced
  **0** refused attempts, so counting refusals in a normal run asserts
  nothing. `run.step(choose=)` names the skill instead.
* at the first seed tried, arcana's first counted attempt *fails*, so its lose
  text is said once legitimately — and then the dedupe hides every later
  refusal, which makes the assertion unable to fail. **Seed 1** has the first
  use succeed, so the lose text is never true and a refusal printing it is
  visible. 39 refusals there; the plant now reddens.

## A fight says how it went, and the next scene carries it (#943, combat half)

A story fight reported `Won in 4 rounds` and sent the blow-by-blow to a
transcript file nobody reads during play — *"there is a whole encounter of
this material and none of it is narrated."* The skill-check half of #943
landed earlier (`MARGINS`, `fact (barely)`); this is the half that body
separated out.

**Same discipline, deliberately mirrored**: one phrase from a closed set
(`beat.FIGHTS`), derived from what the engine already produced, and **no
arithmetic anywhere near the prompt**. A number in a prompt is a number the
model quotes back, so fixing *"26 against AC"* by handing over 26 reproduces
the rut inside its own fix. There is an assertion that the carried sentence
holds no digit.

`aftermath(won, bloodied, down)` reads **two printed states and nothing
else** — *bloodied* is the game's own word for half hit points, *down* is
nought or less. Neither is a threshold invented here, which a round count
would have been: "short" has no printed definition. Worst-first among the
wins, because the worst thing that happened to the party is what a narrator
leads with.

**It has a reader, which is the part a derived phrase usually lacks.** The
conversation after the fight opens with it, before the scene's own text,
because it is what the party walks in carrying — and the DM is told it is for
the mood and *"not something anybody announces"*, the same instruction the
margin carries.

Three scoping rules, each with its own assertion:

* **the opening beat only.** After beat one the situation is the last
  reaction, and repeating the fight there has the DM narrating a battle three
  exchanges into the conversation after it.
* **spent on read**, like `campaign.denied`. A flag nothing clears is a DM
  opening on a battle two scenes back.
* **spent at the top of the scene, not where the beats start.** `_roleplay`
  returns early for a scene with nothing to play; holding the phrase past it
  would describe a fight two scenes back. A scene nobody narrates drops it,
  which is right — nobody was asked.

### Two things the plants settled

**The seeds had to be re-measured against the exact scene list.** All four
phrases are posed through *real* fights rather than only through the pure
function, and the first set of seeds came from a probe where the fight was the
only scene. A different graph gives the fight a different stream, so four
assertions failed on seeds measured against the wrong board. 22 plants, 20
red.

**And one guard cannot be reddened, which is recorded rather than hidden.**
The `0 <` that keeps somebody face-down out of the bloodied count: `aftermath`
ranks down above bloodied, so a character counted as both cannot change the
phrase today. It is kept because the count should be a correct count, and it
is the thing that would silently go wrong if that ranking were ever reordered.

## Reinforcements arrive on their round (#962)

`cast_list.resolve` returned a flat cast and `story.field` spawned all of it
before round 1. A `FoeSpec` had `count`, `name`, `words`, `role` and `rank` —
**nothing that said when**. The module prints a wave encounter: a few more
arrive every round until a landmark is destroyed or a round cap runs out, and
only its earliest waves count toward the reward. Imported flat, that is **a
different fight** — the party
faces the whole roster at once with no reason to hurry and no escalation.

DMG2 makes the staged reveal the *default* advice rather than an exotic case:
*"Reveal minions in stages."*

`FoeSpec` gains `at`, `every`, `until` and `worth`; `Dressed` gains `waves`,
which are **not** in `refs` — `refs` is what stands on the board before the
first turn, and `cleared` bookkeeping and the "Against:" line are both
written against that.

**The opening board is the same size with and without a wave**, which is the
assertion the whole issue comes down to.

### Three things or an arrival is scenery

Each has its own assertion, and each was proven by a plant:

* **on the board** — `loader.spawn`;
* **in the initiative order** — `Encounter.join`. Spawn alone makes an entity
  that stands there and never acts, which `Cast.summon`'s docstring already
  records;
* **on the same count as the creatures already there** — `join(beside=)`, the
  module's *"act on the same turn as the others"*. One count for the whole
  wave, so two of a kind do not act half a round apart.

And a fourth that a plant found missing: **an arrival is dressed like anything
else on the board.** Deleting `apply_flavour` stayed green, because a wave
found by shape carries `Reflavour.name` only and a name is not *mechanical* —
so the call really did nothing in that probe. Posed with a themed flavour,
whose fire resistance is readable off the creature.

### What keeps it bounded, and what it admits

* **a repeat must state `until`.** Refused without it: reinforcements with no
  last round are an unbounded fight, and one that earned XP would be an
  unbounded reward. `until` without `every`, a last round before the first,
  and round 0 are all refused too.
* **`worth=False` earns nothing**, which is the module's own rule and what
  keeps a ten-round wave fight from being worth an arbitrary amount. The XP
  award reads `enemies + arrived_worth`.
* **an unpriced wave is said out loud.** A `worth=False` wave is not charged
  against the encounter budget, so it is difficulty nobody paid for — which is
  #958's finding in a second place. The note names the XP figure rather than
  overriding the module.
* **the module's guard is a check, not a facility**: *"if there are any
  room for them. `arrival_squares` asks the grid index, and `Grid.place`
  already refuses to overwrite. A full board turns a wave away.

**Not done**: DMG2's *"come up behind the characters"* has nowhere to land —
this board has no behind — and the module's other stop condition (destroy the
building) is an objective rather than a round cap. Both are stated on the
issue.

### A note on plants, from this one going wrong twice

**A plant can run away.** One wrote `arrived_in = 999`, which made the arrival
hook fire on *every turn* rather than every round, so the fight spawned
without bound and the run had to be killed and restored from the snapshot. The
claim it was meant to test is already covered by two other plants.

**And eleven plants first went red by *crashing*** rather than by naming a
verdict, because the driver indexed `waves[0]` and read `Initiative.rolled`
without a guard. A crash is red, but it says nothing about *which* rule broke.
Nine of the eleven now report properly, and the fix was two defensive reads in
the driver rather than anything in the engine.

## A scene can field allies (#961)

`Scene` had `foes` and nothing on the other side. Every creature the story
engine fielded was a party member (`chargen.spawn`, ref `c:<class>`) or an
enemy, so a module could not say that a handful of guards fight alongside the
party — and the imported adventure's encounter chapter is **built on that**.
Four of its encounters could not be fielded as written.

**The engine could already hold them; `story` could not ask.** A PC-side
creature that is not a character is something the board supports and is
careful about: both `harvest` and `table.characters` filter on a `c:<class>`
ref precisely so a familiar does not count as a sheet (#797). So this is a
field, a resolver and a spawn.

`Scene.allies` is a tuple of **`FoeSpec`** — deliberately the same type, so an
ally is drawn by the same three tiers, validated by the same rules, and can
arrive on a `#962` schedule for free. A second near-identical spec type would
be a second set of rules to keep in step.

**Three consequences, which are most of the work:**

* **the budget.** *"You should build encounters to challenge the party that
  includes the ally."* The allies are drawn **before** a penny is spent and
  their worth is added to what the opposition may cost — so a fight with help
  is a bigger fight, and a scene with six allies is not trivial.
  **Their own XP, not a standard monster each**: the module's allies are
  minions worth a quarter, and crediting each with a full monster would double
  a four-character fight for guards who die to one hit. DMG2's exact *"add the
  experience value of a standard monster"* is written for a **companion**,
  which is #1015.
* **the XP share.** *"When a nonplayer character participates in an encounter,
  that character earns an equal share of experience points."* Four characters
  with two allies divide by six, and the two shares are paid to nobody.
* **an ally is not a character.** The party still holds four sheets, takes no
  wear for its guards, and `table.characters` still answers four.

### `field_allies` is a function because five plants said so

The spawn was six lines inside `_fight` and the driver spawned its own allies
to check them. **Five plants stayed green** against that: putting them on the
enemy side, standing them in the opposition's band, never dressing them. The
driver was proving its own spawn rather than the engine's — which is exactly
the reason `Step.stood` exists one issue over (#994). Through
`run.field_allies`, all three are assertable against the code that runs.

Two more the plants sharpened:

* **the top-up amount**, not just its direction. Multiplying it by twenty left
  *"more foes than before"* true, so the note's figure is asserted against
  what the allies are actually worth.
* **the band widens toward the board**, not into the wall behind the party.
  Reversing it produced perfectly legal squares, so what tells them apart is
  the count: six columns and 50 squares against three columns and half that.

**Not done**: an ally has no sheet, so nothing carries one between scenes —
the module's *"survivors of the previous encounter"* is out of reach. Who
plays them is unanswered; they are run by the same policy as everything else
on the board. And DMG2's **companion character** — formulas, no items, an
advancement table — is a different feature, split out as **#1015**.

## A dressed trap is paid for out of the budget (#958)

`cast_list.resolve` spends the whole encounter budget on creatures and holds
every one of them to `OVER = 1.1`. Then `terrain.dress` armed nought to two
traps from a fixed draw, **after** — because it is a different function that
was never told there is a budget.

**A dressed trap is priced as a minion**, which is DMG2's rule and a
correction the issue's own comment makes to its body: *single-shot traps count
as minions*, and every trap this engine arms is single-shot by construction
(`terrain.arm` sets `sprung` on the first body across the square and never
resets it). So one trap is **6.25%** of a board, not the 25% the body assumed:
one lands **inside** the ceiling and two land just outside. A bookkeeping
fault, not a balance emergency.

`cast_list._trap_allowance` works out what is left, `Dressed.traps` carries
it, and `field_encounter(traps=)` hands it to the dresser. Measured: a board
asking for one creature affords two traps, a board spent to its ceiling
affords one.

**`None` means "nobody worked it out", not "none."** That is the whole of the
compatibility story: `fight.build`, `api` and `winrate` reach
`field_encounter` without a cap, so arcade boards keep the dresser's own draw
and are bit for bit what they were. **The `winrate` run this issue asks for
would therefore measure nothing** — and `replay`'s fixtures are the standing
proof. Arcade's own budget is still unpriced for traps; changing that would
move every winrate and scorecard baseline, which is a separate decision.

**The draw is made and then cut** rather than skipped, so capping cannot move
the rest of the board. Worth knowing honestly: a plant that skipped it stayed
green, because nothing consumes the stream after the count once it is nought.
The ordering is defensive, and the floor assertion is the guard against
somebody reordering the scatter rather than proof the cut matters today.

### What the plants found

Fifteen plants, fourteen red. Four assertions exist only because one stayed
green, and three of the four are the same mistake: **asserting on what the
driver could see rather than on what the code does.**

* **`_fight` handing over no allowance at all** passed, because the board does
  not outlive the fight and the only visible thing was the outcome.
  `Step.traps` now counts what was armed, read off the board after `start()`
  — the same rule, and the same fix, as `Step.stood` and `Step.surprised`.
* **`dress`'s own default** is never exercised by `field_encounter`, which
  always passes the keyword, so a plant flipping it to 0 changed nothing.
  Asserted directly on the signature.
* **the unspendable-budget branch** is unreachable through `resolve` today,
  since `budget` clamps to the database's ceiling. Posed against the helper,
  and said so in the assertion.

## A scene can say how big the room is (#974)

Every board was one of two hard-coded rectangles — `Grid(16, 12)` for a fight,
`12 x 8` for a borrowed board — so a corridor, a cave mouth, a great hall and
a tavern were the same floor with the same two bands at the ends.
`field_encounter` took a seed, a level, both sides, a scaling preset and a
maths preset, and **no shape**.

`Shape`, `CHAMBERS` (the printed ten), `corners_of`, `bands_of`, `line_up`,
`field_encounter(room=)` and `Scene.room`. An octagon and an irregular
chamber needed nothing new: **a cut corner is blocking squares**, the same
mechanism a pillar already uses.

**The default does not move, and that is the whole safety argument.**
`bands_of(FLOOR)` reproduces `PARTY_AT` and `ENEMY_AT` exactly, and `line_up`
is byte-identical to the hard-coded `(i // 5)` / `(i % 5)` expressions it
replaces. All eight replay fixtures pass unchanged — so the re-record and the
`winrate` run the issue asks for are **not owed by what landed**. What would
owe them is the seeded draw over the ten chambers for the arcade path, which
is deliberately not here.

**One correction to the issue's own figures**: by area **all ten** printed
chambers are smaller than 16x12, not nine, and the two 10x16 entries do not
"match it in area" — 160 against 192. They are the closest, and two of the ten
are *taller*, which is why `line_up` had to generalise in both directions.

### Two real bugs this found

* **`formation.squares(spread=3)` put the fourth of four characters on row
  12 of a 12-row board.** `_fight` handed that straight to
  `field_encounter(squares=)`, so a character was spawned off the grid — and
  **#994's own driver asserted it**, expecting rows `[3, 6, 9, 12]`. The
  overflow is now lined up instead and said out loud; the others keep the
  arrangement the player chose.
* **the two sides were lined up independently and collided.** On a 10x10
  chamber the opposition's column reaches back into the party's, and
  `grid.place` refuses to overwrite — so the second creature would be
  `Position`-present and index-absent, the failure `dress` already warns
  about. `line_up(taken=)` is what stops it.

### What the plants settled

Twenty-two plants, twenty-one red. The pattern worth remembering: **six
plants survived because every square of a small chamber is also a square of
the standard floor.** Placement checks cannot tell a board that shrank from
one that did not, so the assertions had to be:

* the fielded world's **grid size** is the stated room's;
* the cut corners are **on** the board as blocking squares, not merely
  computable;
* **no two creatures share a square**;
* the party's first square **is** `bands_of(room)[0]`, since a formation laid
  from the floor's corner also lands inside a 6x8 room;
* and `Step.room` records the board, because it does not outlive the fight —
  the same reason as `stood`, `surprised` and `traps`.

A seventh needed a room **taller** than the floor: on a shorter board the
bounds filter drops the overflow, so a wrong column height produces the same
squares. `Shape(10, 16)` is where six-to-a-column and five-to-a-column differ.

## The printed encounter templates (#951)

`PARADIGMS` is four shapes keyed by **rank**; the book gives five keyed by
**role**. `solo` is its Dragon's Den and `leader` its Commander and Troops —
**Double Line, Battlefield Control and Wolf Pack had no analogue**, and the
first two are the ones that make a fight worth positioning in. Fielding five
creatures of one role gives the policy nothing to do, which is half of the
standing complaint about the combat AI.

`TEMPLATES` holds the three, as `(rank, share, roles)`. `COMPOSITION` is
unchanged and is read as the same shape with no roles, so `_compose` fills
both in one loop.

**The draw is deliberately untouched.** The book rolls five templates at equal
weight; adopting that would re-shape every arcade board and every fixture,
which owes `winrate` both ways and a re-record. So `PARADIGMS` is still the
four that get **drawn** and `SHAPES_BY_NAME` is the seven that can be **asked
for** — `field_encounter(paradigm=)` and `fight.py --paradigm` are what ask.
All eight replay fixtures pass unchanged.

Measured at level 5: a double line fields 3 front and 2 rear, battlefield
control 1 controller and 3 skirmishers, a wolf pack 4 skirmishers — and
`standard` still mixes roles freely, which is the control.

**A role filter that empties the pool is dropped rather than obeyed**, which
is this component's own recorded caution: 253 of 384 minions carry
`role = 'minion'` rather than a tactical role.

### Two things the plants sharpened

* **The empty-filter guard could not be posed against real data** — measured,
  every tactical role exists at every level in the standard rank, so no
  printed template can empty its own pool. Posed with a template asking for a
  role nothing has, injected into `TEMPLATES` and removed in a `finally`.
* **And asserting that it still fielded somebody was not enough.**
  `opposition` already falls back to `standard` when a named paradigm yields
  nothing, so the board is never empty either way — what the guard actually
  buys is that the template **stays that template** instead of silently
  becoming a standard encounter. The assertion reads the third return value.

## One skill cannot carry a whole challenge (#984, the cap)

A challenge had no per-skill success cap, so the party could win it four
times on one skill — the bottleneck DMG2's ground rule 2 is entirely about:
*"if only one skill does the heavy lifting for the challenge, you need to
rethink the challenge."*

The remedy comes with a number — *"a good maximum is equal to the complexity
of the challenge"* — so the default needs no authoring. `Scene.cap_for`
returns the module's own figure if it states one, else the complexity, else 0
for no cap. `Running.won_with` is the tally.

**The default withholds itself when it would make a challenge unwinnable**,
and that is not hypothetical: the one converted challenge is complexity 1 with
**three** primary skills and wants **four** successes, so a cap of one each
allows three. `Scene.capped` is that test. A stated cap is trusted over the
default and gets the same check at parse time — caps that together allow fewer
successes than the challenge wants are refused, because trusting a figure
without the check the default applies is a hole.

**The cap is enforced in two places and both are needed.** `taking_turns`
stops offering a capped skill, and `attempt` refuses one. The first is what
keeps the challenge moving: before it, the chooser kept naming a skill that
could no longer count — **33 refused attempts in one challenge**, which burned
`play`'s attempt limit and turned a win into a loss. The second is for a
chooser that knows nothing about caps, which is every model.

**It is a small measured difficulty increase, not a free rail**: over 150
seeds at complexity 3 with four skills, **21.3% capped against 25.3%
uncapped**. Worth stating because the first measurement, taken *before* the
chooser learned to skip a capped skill, said the cap cost nothing — the wasted
attempts were hiding it. A figure measured against a half-built mechanism is
not a figure.

Two plants also showed that `attempt`'s refusal is **unreachable through the
default chooser**, since the chooser filters first. Posing it needed a
`choose=` that insists on the capped skill — the same trick #932's driver
needed, and for the same reason.

**`secondary_grants: "success"` is still there and probably should not be.**
DMG2's list of what a secondary check can do does not include it, the tree
already measured it as degenerate (5 wins in 5, three of four successes from
easy secondary rolls), and **no converted scene sets it** — measured, the one
challenge in `modules/` uses `bonus`. Retiring it is a one-line deletion plus
three sites in `challenge.py`; left for a decision rather than taken, because
removing an authoring option is not a thing to do silently.

## The party finds the treasure it is owed (#969)

No treasure was awarded anywhere: a party finished a module with the equipment
`chargen` dealt it and nothing else.

Ten parcels per level — **four magic items at party level +1 to +4, and six
monetary.** Both halves are here. The monetary one landed first, on the ground
that coins change no number on any board; the item half was held for a decision
because a parcel sits **above** `band(level)` and `band` is exactly what monster
defences are set against, so an item off that curve looked like it owed
`winrate` both ways. Camille's call, 2026-10-30, was to award them.

**It owes no `winrate` run, and the reason is a scoping call rather than an
argument: a found item is carried, not worn.** `Sheet.carried` is a count of
what happened to the party and **nothing in a fight reads it**, so the party's
power is unchanged — all eight replay fixtures identical, which is the proof
rather than the hope. `chargen.treasure` equips three items at `band(level)`;
**equipping from inventory is the part that would owe the measurement**, and
there is no action for it today. Both docstrings say so, so the next reader does
not re-derive it.

`ITEM_STEPS = (4, 3, 2, 1)`, descending, because the page lists parcel 1 as the
best of them — and because DMG2's alternative rewards replace *"the
highest-level magic items you would otherwise give out"*, which only means
anything if parcel 1 is the dearest.

**`item_for` draws the way `chargen.treasure` draws** — joining `item` to
`item_step` — so it can only ever pick a rung that exists at the level asked
for. That is the pattern to reuse here rather than `terrain.printed_trap`'s.
**Not** filtered by slot or base item, deliberately: a parcel is what the party
*found*, and the page does not promise anybody present can use it;
`chargen`'s `_fits_base` matters when an item is being **equipped**, which
nothing here does. A level the database prices nothing at yields `""` and the
parcel is **dropped rather than retried elsewhere**, because substituting a
different level would hide a gap in the corpus.

An item goes to **one character**, round-robin by parcel, because an item is
one object; coin divides because coin does. Measured at level 5 over twelve
fights: items at levels 9, 8, 7 and 6, then 550, 500, 340, 340, 160, 110, then
nothing on fights 11 and 12 — ten parcels, 499 gp each, one item on each sheet.

**And one existing assertion had to change its question.** `scene_grant` asked
whether the party carried *exactly one thing* after the next fight, which was
the same question as "#935's grant survived" until a won fight started handing
over an item into the same bag. A total conflates *the grant survived* with
*nothing else arrived*; it asks about the granted ref now, which is the claim
and is equally breakable in both directions.

**Nothing is written down that the database already holds.** The curve is
`2 x market_price(level)`, computed from the mode of `item_step.cost`, and it
is exact against the book's Total Monetary Treasure line: 720 at level 1,
3,600 at 6, 10,000 at 10. Nine of ten heroic levels agree to the gold piece;
**level 3 is off by 5** (1,360 computed against 1,355 printed) and that has its
own assertion rather than a special case.

The mode, not the first row — 440 of 497 rows at level 8 carry it. Same
reasoning and same trap as `xp.standard`, #1014.

**`shares` sums to the level's total exactly.** The printed proportions come
to **1.005**, so the bare shares over-run by 10 gp at level 5 and the
overshoot comes **off** the largest parcel. That direction was asserted
backwards first — the adjustment is a subtraction, not a remainder.

**The distribution falls out rather than being rolled.** *"One treasure hoard
of three parcels, two treasures of two parcels each, and three treasures with
a single parcel. That leaves two to four encounters with no treasure reward."*
Six of the ten parcels are monetary, so six fights carry money in descending
parcels and the rest carry none — because the level's treasure is spent, not
because a die said so. Measured over nine fights at level 5: 550, 500, 340,
340, 160, 110, then nothing, and the party holds **1,996 of 2,000** with the
4 gp lost to the per-head flooring.

Nothing resets the count, because nothing levels up (#1013) — so ten parcels
is the module's lot, and `hoard`'s docstring says so.

**Nothing spends the coins.** An economy wants rituals (#453) and a market; a
visible number that cannot be spent is honest, awarding nothing was not.

**Two pieces of the printed system are absent, both filed with a measurement:**

* **#1020, alternative rewards.** They go in an item parcel's *place*, are not
  physical objects, occupy no slot, and fade after five levels — and **119 of
  them are already in `game.db`** under their own category with `slot = ''`.
  `item_for` filters on nothing, so **5% of the pool is already one** (64 of
  1,287 refs at levels 6–9) and `hoard` files it as a carried object, which is
  the wrong noun. Harmless today because nothing reads `carried`.

  The reason it is the *interesting* half rather than the leftover: the page
  says alternative rewards **never grant enhancement bonuses**, so a reward is
  the only parcel that could be put **in play** without moving the curve the
  monster defences are set against. That curve is the whole reason the item
  half had to be carried rather than worn.
* **#1021, the group-size adjustment.** The printed table adds and drops
  parcels for a party that is not five; this divides a fixed ten evenly, so a
  party of three is richer per head and the level's total never moves. Filed
  **without** the table's contents, because the page has not been read — which
  is the rule about a quoted table applied to an issue I was writing myself.
