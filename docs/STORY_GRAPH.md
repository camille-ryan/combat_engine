# The story graph — what is true, who knows it, and who said so

A design for the knowledge layer under the story engine. Written before the
code so the reasoning survives the implementation, because almost all of it
came out of a conversation and none of it was anywhere in the repository.

Status: **design agreed, partly measured, not built.** What exists today is
listed at the bottom.

## The problem it exists for

A player asked an NPC who a named man was. He is named exactly once in
that scene's read-aloud, as the patron's missing informant, and the
adventure says nothing else about him there. The DM answered with:

> *[a paragraph giving him a knighthood, a fall from grace, and a death]*

A knighthood, a fall from grace and a death — for a man the party is being
hired to rescue alive, two scenes later. The invention **contradicts the
plot**, and nothing distinguishes it from the real thing. That is #830.

Two guards already exist and neither bites. `_DM` forbids introducing *"an
object, a person or a place that has not been mentioned"* — but the man *is*
mentioned, so the rule does not apply. Affordances constrain what a
character may **try**, and say nothing about what an NPC **knows**.

**This will be the commonest failure in play.** Every other guard in the
component addresses something the model does unprompted. This one is driven
by the player, who will ask about anything the text names — a person, a
jewel, a place — and most of those have no answer written down. The opening
scene's read-aloud alone names nine proper nouns; the NPC entries cover two.

## Three layers, and the model reads two

The single most important structural decision, and it came from Camille's
observation that adventures should not be ingested the way setting books
are. A setting book says **what is**. An adventure says **what may happen**.
Flattening the second into the first turns contingencies into facts, and the
moment a party plays it differently the graph is wrong about its own world.

| | what it is | who may read it |
|---|---|---|
| **setting** | true before anyone plays; shared across campaigns; immutable | the model, freely |
| **module** | possibilities, scoped to this adventure, not yet true | **code only** — never the model |
| **campaign** | what *this* party did and was told; per-save; append-only | the model, freely |

The middle row is the point. It is the same rule the component has now
learnt four times under different names:

* `Npc.hides` withholds a fact rather than forbidding its use;
* `Scene.brief` versus `Scene.sets` withholds the DM's text (#805, then
  #829 when the DM prompt was found still reading `brief` and saying the
  chapter's twist out loud through a gate sergeant);
* a transition affordance's `win` text is withheld as a stage direction
  (#807);
* an unnoticed NPC is withheld from the cast entirely.

Stated generally: **the model may read what the players know, and never
what the DM knows.** The module layer is by definition the DM's, so it
reaches the model only through affordances, lore rows and scene text — all
of which are code-mediated.

Asked who the informant is, the DM gets the setting layer's facts about him
and whatever this campaign has already established, and may invent past
them. What it must not do is contradict them -- and the page facts are the
reason it will not kill off a man the adventure says is missing and held
somewhere. The module layer, which knows he is alive in a cave and why, is
still not consulted.

### An adventure contains both kinds, and ingest must split them

Not choose between them. The same page carries both:

* a sentence describing the fortress, its valley and its unpopular new
  lord — true before anyone plays. **Setting.**
* a sentence beginning *"if the party refuses..."* and naming what the
  patron offers instead — a branch. **Module.**

The split is largely **typographic and therefore exact**, which was
measured: boxed read-aloud is 8.7% of the adventure and is player-facing by
construction; everything else is the DM's. `importer.read_aloud` already
extracts the first by font.

## Provenance is a first-class field

Camille's requirement, and it is what makes the whole thing safe rather than
merely useful. Every fact carries where it came from:

| `source` | means | may contradict? |
|---|---|---|
| `page` | lifted from the adventure, with a verbatim quote and a page number | no — it is the canon |
| `earned` | the module's own `win`/`lose` text, paid for with a die roll in play | no |
| `invented` | the model made it up at the table | yes, and that is the point |

Three things follow, and all three are the reason to do this at all.

**The DM's inventions become consistent.** Today an invented backstory
exists for one paragraph and is gone; the next time anyone asks, a different story
arrives. Written to the campaign layer as `invented`, it is *the* story from
then on. An improvised barkeep stays the same barkeep.

**They stay distinguishable.** A `page` fact and an `invented` fact are
never confusable, so a reader, an instrument, or a later session can tell
what the adventure said from what the table made up. A transcript becomes
auditable.

**They stay reversible.** An invention that contradicts the plot — a man
dead who must be rescued alive — can be found and dropped, because it is
tagged. The canon cannot be corrupted by play, only added to.

An invention is written to the **campaign** layer and never to setting. A
setting graph is shared across campaigns; one table's improvisation must not
leak into another's world.

## Camille's ruling: invention is wanted, contradiction is not

**This reverses what the first draft of this document argued**, and the
reversal is on the issue itself, in a comment the body does not reflect --
which is the failure mode the root `CLAUDE.md` opens by warning about.

> *"it's actually intended behavior for the DM to make things up and them
> to become canon. However, the made up facts MUST be consistent with the
> rest of the story."*

So the job is **not** to make the DM say "I never met him". Improvisation
is the point of having a model at the table at all; the knighthood was not
wrong for being invented. It was wrong for killing a man the party is hired
to rescue alive.

That changes what the graph is for, and makes it *more* necessary rather
than less:

1. **Record what is invented**, tagged, so it is the story from then on
   rather than lasting one paragraph.
2. **Feed it back**, so the next answer about the same person agrees with
   the last one.
3. **Feed back the canon too**, so an invention cannot contradict what the
   page already said.

The third is what would have caught the knighthood. The adventure says the
man is missing and was taken to a grotto; a DM holding those two facts does
not kill him off. **Consistency is supplied, not requested** -- the same
shape as every guard in this component that works.

Absence remains an option the module can choose -- an NPC with nothing
recorded and nothing to invent from may still say they never met the man --
but it is the exception, not the default, and the rest of this document
should be read that way.

## Lookup is exact, and so is the absence when it is wanted

The graph half is kept and the RAG half is treated with suspicion, for a
reason specific to this project.

The architecture rests on closed sets. A 7B scores **1 of 3** judging freely
and **3 of 3** classifying against a list, and affordances exist entirely
because of that gap. Top-k embedding retrieval reintroduces what affordances
removed: it **never returns nothing**, it returns the nearest thing. Ask
about a jewel, get a node about a city, and the DM now has a
plausible-adjacent fact — which it will use, because a fact in a prompt is
an invitation to use it.

**An exact lookup can answer "nothing known", and an approximate one
cannot.** That matters even though absence is no longer the default reply:
the DM has to be told *which* facts bind it, and a retriever that hands
back the nearest thing binds it to the wrong ones. Ask about a jewel, get a
node about a city, and the invention is now anchored to a fact that has
nothing to do with the question -- which is worse than no anchor at all.

So the property to keep is that a miss **misses**: `None` means "nothing on
record, invent freely", and a hit means "these are true, do not contradict
them". Top-k cannot express the first.

So: resolve a mention to an entity by **name and alias, exactly**, and
traverse typed edges one hop for context. The Planescape project's
`registry.json` is exactly this index — canonical name, aliases, type, brief
— and its chat UI never uses it that way, going through FAISS for every
query. The piece worth borrowing is the one that is not wired up there.

Embeddings do have a place: **resolving a mention to a node** when the
player types "the fat priest" for a patron the graph has under his name. That is approximate matching with
a constrained output set, which is the right use. Not fact selection.

## Secrecy is a DC, and a band cannot keep a secret

| | | |
|---|---|---|
| **common** | anyone has it, no roll | `known_to: everyone` |
| **circulating** | a check on the right skill | Streetwise in the keep, Religion for cult trappings |
| **specialist** | a hard check | History for a stolen jewel |
| **secret** | **no band at all** | `known_to: [the-patron]` — needs the person, or an affordance |

The last row is what a single difficulty scale gets wrong: *"very hard to
know"* and *"cannot be known by thinking about it"* are different, and
collapsing them means a lucky History roll uncovers the plot.

**Measured, and it forces the design rather than decorating it.** With five
characters rolling at level 1, somebody passes an easy check **100%** of the
time and a moderate one 97–100%; only hard is a real question, at 52–89%. So
a band does not decide *whether* the party learns something — it decides
*who tells them*. A fact that must stay unavailable gets **no rollable entry
at all**.

### Knowing and telling are different

An NPC who knows a secret and is in a scene will say it if it is in their
prompt. The friar **knows** he serves a snake god and will never say it; he
**knows** he has a spy and volunteers it in beat one. `Npc.knows` and
`Npc.hides` already encode exactly that split and it is load-bearing.

In the graph it is a flag on the edge: *knows* and *would volunteer*. **Only
the second reaches a prompt.** Knower edges are not enough on their own.

## Getting it out of the text

Do not ask a model to judge secrecy — that is the 1-of-3 side of the line.
Two things were tested against the real adventure:

**Lexical signals do not exist.** I predicted adventures mark secrecy in
stock phrases. Across 154 pages: *hidden from the party* 7 matches on 5
pages, *available for the asking* 4 on 3, **5.1% of sentences carrying any
signal at all**. Worse, the phrase I cited as proof has **zero** matches in the source. I
had written it myself while hand-authoring the first chapter and quoted my
own paraphrase back as evidence about the book. (It is not repeated here
either: `leaks.py --modules` flags it, correctly -- the check cannot tell
my paraphrase sitting in a module from the adventure's own prose sitting
in a module, and should not try, since both belong there and neither
belongs in the tree.)

**What does exist is `DC \d+` — 140 matches on 42 pages.** The adventure
almost never says a thing is hidden; it says *"DC 15 Insight"*. Of 143 DC
sites, **~78 gate a fact** rather than an action, most of them written as a
skill heading with a ladder of numbered facts beneath it. That is a lore row
already — fact, skill, number — and it is the thing to harvest.

Of the rest: 44 gate an **action** (an Athletics DC 19 to bend
a window's bars) and
belong to affordances, from the same extraction pass. Twelve are
**person-locked** (a DC 19 Intimidate, after which a captive names who hired
him) — a fact held by a knower, which is the third category and confirms it
is real rather than posited.

### The default for everything else is structural, not lexical

Read-aloud is 8.7% of the text and player-facing by typesetting. Headings
carry more: `Illumination` and `Terrain` alone are 8.5% and are definitionally
what anyone in the room perceives.

**Honest limit:** 44% of the text sits under no heading my pattern found,
and `Features of the Area` came out at 471 characters across 154 pages,
which is obviously a detection failure rather than a real count. Headings
are a **font**, exactly as the italics were, and pulling them by font is the
same trick that already works. Until that is done, the size of the
heading-based default is unmeasured.

An earlier attempt to measure the blanket default's error rate was **invalid
and is withdrawn**: it used my own hand-authored `knows` entries as ground
truth, and those are paraphrases and inventions, not the source. Third time
in one session that I reached for my own writing as evidence about the book.

## Ingest runs locally and free

Camille's call, and it removes the cost risk that bit the Planescape project
($256, and a $200 surprise).

**No OCR stage.** 134 of 154 pages have a clean text layer, median 2,730
characters. Planescape needed GPT-4o vision because those books are scans.

**DeepSeek does the extraction.** Measured on three real pages: 20, 15 and
14 entities, schema adherence free through ollama's `format`.

**Quotes are validated by climbing fuzzy match**, Camille's method — exact
first, then widening one edit at a time to a hard cap:

```
max edits   recovered     wrong page
        0    33/49  67%    0/98   0%
        2    46/49  94%    0/98   0%
        4    47/49  96%    0/98   0%
```

The knee is at **2 edits**, and the negative control is flat zero
throughout: 98 attempts to match a quote against a page it did not come
from, not one false hit, even at 8 edits.

My first instinct — an error budget as a fraction of length — was wrong
twice over: less precise, and computationally intractable, since one pass at
40 edits over a page never finished and had to be killed. **Climb from
exact, cap absolutely.** The tightest match that works is also the strongest
claim.

On a hit the **document's span replaces the model's text**, so what is
stored is what the page says — `charac- ter` with its line break intact, not
the model's tidy-up. That is what makes a citation checkable later.

And the 4% that does not recover is **paraphrase, not hallucination**: a
third-person restatement of a line the page prints as dialogue. Dropping it
is right.

## What exists today

Built and committed:

| | |
|---|---|
| `importer.extract` | PDF → per-page text, outline |
| `importer.read_aloud` | the italic boxed text, by font: 80 blocks, deduped, column-aware, paragraphs restored |
| `llm.structured` | JSON Schema enforced through ollama's `format` |
| `llm.Role`, `roles_for` | a model per job, per-campaign override, two backends |
| `module.Lore` | fact / skill / band / `dc` / `once` / `after` — the per-scene form of a gated fact |
| `Npc.knows`, `hides`, `looks`, `unseen` | the per-scene form of a knower |

Measured and **not** committed — scratch only, worth keeping before it is
lost: the DeepSeek extraction probe and the climbing fuzzy recovery.

Not built: entity extraction as a pipeline stage, the registry with aliases,
cross-document reconciliation, the store, lookup, and the wiring into
`beat.py` that would actually close #830.

## What this does not do

It does not replace affordances. The graph answers **what is true**; an
affordance answers **what can be tried, against what DC, changing what**.
Collapsing them puts judgement back into retrieved text, which is the thing
the 3-of-3-versus-1-of-3 measurement argues against.

It does not make the DM reliable. Every guard in this component is a
tendency rather than a guarantee, and the ones that hold are the ones
enforced in code — an enum the model cannot answer outside of, a fact
printed rather than narrated, a field withheld rather than forbidden. The
graph should be built the same way: **the absence answer must be produced by
the lookup, not requested in the prompt.**
