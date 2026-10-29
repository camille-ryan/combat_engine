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

## A skill challenge never stops the plot

Camille's ruling, **2026-10-29**, verbatim:

> *"Skill challenes should never prevent the plot from progressing."*

The code obeys it by one `or` in `run.step` --
`made.next_id = wanted or module.next_of(scene, choice)` -- so a module
that names a success branch and no failure branch falls back to the
ordinary exit instead of stranding the party. Nothing asserted that until
`drivers.py challenge_progresses`, and deleting the fallback ends the
campaign silently on any failed challenge.

**The adventure agrees, which is why this is the right rule rather than
our preference.** Both of its challenges continue either way:

| | success | failure |
|---|---|---|
| chapter 1 | the fires go out, every token removed | the fires burn through the whole fight -- *"The heroes receive experience for this skill challenge even if they fail it."* |
| chapter 4 | good time, they reach the stones by mid-afternoon | rough going, **each character loses a healing surge**, and they reach the same stones late |

Chapter 4's two outcomes name **the same next encounter**. A challenge is
a toll on the way through, not a gate.

**What a failure costs is a resource or a condition, never the road**, and
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
    beat_loop scene_audience module_refusals affordance_match \
    summary_scenes boxed_text graph_furniture graph_administration \
    recall_order borrowed_board party_size_rule challenge_progresses
uv run scripts/check.py --only play,drivers
```

**25 drivers and 218 assertions** cover this component, and **each was
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
