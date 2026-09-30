# Community guides as a seed score

`scripts/guides.py` reads option ratings out of the 4e optimisation guides and
writes them to `src/combat_engine/ratings.py` as `ref -> score`. This file is the
registry and the reasoning; the plan is `plans/20260929-guide-ratings.md`.

## Why

Every weight in `chargen/choices.py` is a number somebody invented, and #213
asks for a scorer that is "doctrine based" — Camille's own example being that
"most characters should take expertise and improved defenses", which is a
statement about a *rating*. The community has been rating 4e's options on a
stable six-colour scale for fifteen years. That is a large body of judgement
about exactly the options this project could not rank.

It also does not depend on #249 being fixed. The damage half of any threat
number is currently wrong by a factor of three on conditional strikers, so a
computed score would have to be redone; an external ordinal rating would not.

## What crosses into the repository

Only `ref -> number`, plus which guide said so.

* Fetched HTML → `.cache/guides/`, git-ignored. Full of printed names.
* The authors' prose → `notes/`, git-ignored. Not ours to carry, and more use
  to a human than to a scorer.
* `src/combat_engine/ratings.py` → tracked. Refs and numbers.

`scripts/leaks.py` is the proof, not the intention: it reads every name the
compendium holds and greps every tracked file, exiting non-zero on a find.

The ratings themselves are judgements about game mechanics, which is the same
ground the rest of the project stands on. Each is attributed to its source URL
so a number can be argued with rather than trusted.

## The scale

| colour | meaning | score |
|---|---|---|
| gold | game-breaker, or a mandatory tax | 6.0 |
| sky blue | cream of the crop | 5.0 |
| blue | good | 4.0 |
| black | middle of the road | 3.0 |
| *(unrated)* | no guide mentions it | **2.5** |
| purple | outclassed, or only situationally good | 1.5 |
| red | do not take this | 0.0 |

## Unrated is absent evidence, not a low score

The number matters less than the marking. `rating(ref, cls)` returns **`None`**
when nobody rated it, and `why(ref, cls)` says which kind of silence it is:

| answer | what it means |
|---|---|
| `rated` | a guide for this class said something |
| `no guide for this class` | by far the commonest, and carries **no** information about the option |
| `rated for another class only` | an opinion exists and does not transfer |
| `unmentioned` | a guide for this class exists and did not name it |

`score()` exists for callers that must have a float and returns `UNRATED` (2.5),
just below rated-average — but it is a placeholder, not a verdict. A scorer that
can omit a term should ask `rated()` first and leave the feature absent, so other
terms decide rather than a made-up number competing with them.

**Even `unmentioned` is not a negative**, and the measurement says why: the first
guide read rated **136 of 3,501 feats**. It did not consider and reject the other
3,365. Silence means the author was writing about something else, or the option
postdates the guide, or their table bans the source.

A book-scope heuristic was tried and abandoned for the same reason. Deriving each
guide's scope from the books it demonstrably rated from separates almost nothing
for powers — 100% and 97% of the two classes' powers come from books their guide
rated from — and for feats it leaves 2,033 "in scope but unmentioned", which a
guide that discussed 136 plainly never weighed. Scope was the wrong mechanism;
honesty about ignorance is the right one.

**24 of 25 classes have a guide.** `GUIDED_CLASSES` is what a caller checks.

The invoker is the one gap, and it is not fixable from this source: its guide's
colour was **lost in a forum migration**. The page's own text says "the sky blue
rating is based on the excellent 1-13 powers", so the ratings existed — but the
HTML carries no colour markup at all, and every option falls through to black.
The guide is refused rather than contributing 388 false averages. An archived
snapshot of the original thread would be the way to recover it; none of the 16
archive.org links in the index is that thread.

The avenger came from a Google Site of **51 sub-pages**, which needed a crawl: the
colour key is on the landing page and the ratings are spread across the rest, so
they are fetched and concatenated into one document.

**Black is bold with no colour on it.** The first pass here walked colour spans
and reported zero blacks, and concluded the tier was unextractable. That was
wrong: black is the default *colour*, but an option's name is **bold** whether it
is rated or not, and a colour is wrapped around it only when the author is
rating it away from average. So bold is the anchor and colour is the modifier.
Measured on the first guide, of the bold names that resolve to a ref: 419 sit
inside a colour and **152 do not**, and those are the blacks.

Bold is the better anchor for a second reason. A coloured span often runs on
into the prose after the name; the bold element is the name and stops there.
Switching to it took the table from 288 refs to 374 and coverage from 55% to
74%.

One caveat that follows: bold is also used for ordinary emphasis, so some of the
black bucket is a name mentioned in passing rather than a deliberate verdict of
"average". The consequence is bounded — a false black moves a ref from 2.5 to
3.0, half a point on a six-point scale — which is why it is accepted and written
down rather than guarded against. A ref bolded in one place and coloured in
another keeps the coloured reading, since the uncoloured mention is usually the
incidental one.

**Green is not a tier.** Several guides use it for options that are "a different
kind of useful", and the first guide's key says outright that *a lot of
non-combat options fall here*. That is this project's `narrative=` and
`out_of_combat=True` category, so green is recorded in `OUT_OF_COMBAT` and
excluded from the combat score rather than ranked against things it cannot be
compared to.

## A rating belongs to a class, not to an option

`RATINGS` is keyed `ref -> {class: score}`, and that is not a detail.

A power is class-specific already. A **race, a feat or an item is not** — it gets
rated in a class context, and the same option is honestly worth different amounts
to different classes. Across all 37 guides: **831 refs are rated for more than one
class and 344 of those differ by two tiers or more**, the widest being the full 6
of 6. On the first two guides alone it was 51 overlapping and 13 that wide.

The first version averaged those, which produced a mid-tier number wrong for both
sides of every one of them. So `rating(ref, cls)` takes the class and returns `UNRATED` when
the only opinions on file belong to other classes: a wizard guide's view of a race
says nothing about that race for a fighter, and borrowing it is worse than
admitting ignorance.

`spread(ref)` reports how far apart the classes are, and is worth reading rather
than smoothing away. An option two experienced players put two tiers apart is
genuinely situational, which is information a single number loses.

The one case where a power legitimately carries two classes is a guide rating
another class's row as worth poaching — a real and separate judgement, and the
key holds it correctly.

## The colour map derives itself, with a floor under it

The scale is conventional; the hexes are not. The first guide's author states the
shades were chosen to suit photosensitive eyes, and uses a teal (`#33cccc`) where
convention uses a pale blue. Hand-recording 36 keys was the plan's stated
bottleneck.

It is not needed. Nearly every guide states its key near the top and writes each
colour word **in that colour**, so `legend()` reads the map off the document.
Checked against the one key entered by hand: 6 of 6 agreed.

`CANON` sits underneath as a floor — the six hexes the guides that *do* state a
key agree on. That exists because deriving the key fails silently on some guides,
and a guide with no key drops every coloured rating as unmapped. Precedence is
canon, then the guide's own key, then a hand override. Exactly one override
survives, for the guide whose legend swatch differs from what its body uses.

Anything still unmapped is **reported**, not guessed. Inferring a tier from a hue
is how a red becomes a gold — and inferring one from a colour *word* is the same
mistake: `magenta` was mapped to the purple tier until a guide turned out to use
that exact colour for "GM/table dependent".

## Resolution

An exact match on a normalised name, which is enough because of a measurement
rather than a hope:

| | refs | distinct names | collisions |
|---|---|---|---|
| powers | 4,243 | 4,243 | **0** |
| items | 1,883 | 1,882 | 1 |
| feats | 3,501 | 3,368 | 133 pairs |

So no fuzzy matching, no confidence threshold, no reject list. A power name
identifies a power.

Every prefix in `names.json` is indexed, not just the rateable ones, so a
coloured run naming something out of scope is *reported as such* rather than
counted as a failure. `x` alone is 4,876 entries with no table in `game.db` —
paragon paths and the like, which this project does not implement. A collision
between a rateable ref and an out-of-scope one resolves to the rateable one: a
guide rates options, and widening the index had otherwise taken ambiguity from
6 to 63.

## The registry

36 guides, read from 96 candidate URLs harvested off the index thread's seven
pages. `--discover` fetches each and reports whichever class owns most of the
powers it rates; `REGISTRY` in `scripts/guides.py` is the result, one line per
guide. 23 classes are covered, with three guides each for fighter, paladin,
warlock and wizard.

**The class is detected, not trusted.** The index mislabels at least one guide —
what it lists as a seeker handbook is a warlock handbook — and the check that
caught it works just as well with nothing claimed: 180 of its 182 apparent
"strays" were warlock rows. Two guides resist detection because they rate mostly
feats, items and paragon paths rather than their own class's powers; those carry
the class stated by hand and say so in their note.

## Four things that had to be fixed, each found by a number looking wrong

**Read the author's posts, not the first post.** 51 of 96 candidates resolved
*nothing*. A long guide runs over five or six posts and several begin at post 2
behind a short introduction and a table of contents. The thread starter wrote
post 0, so every post by that author is the guide and everything else is a reply.
Fixing it took the class-guide count from 12 to 38 and the classes covered from 8
to 22.

**Gate on the power count, not the share alone.** The share is computed over
resolved powers, so an items compendium that happens to name two wizard powers
read as a wizard guide at 100%. It was rating 282 options and only 4 of them were
powers. The gate is now 60 options, at least 10 of them powers, and 80% of those
owned by one class — which also excludes the basic-attack guide (271 powers,
17% one class) and the item guides.

**Look for the colour both above and below the name.** The wizard handbook writes
`<span style="color"><b>name</b></span>`; the fighter handbook writes
`<b><span style="color">name</span></b>`. Reading ancestors alone found the colour
on 42 of the fighter guide's bold elements and missed 583 — so its every rating
was discarded as unmapped and only uncoloured blacks survived. **14 of 36 guides
were reporting 95–100% black**, which is what a broken reader looks like rather
than what a guide looks like. After the fix, three.

**Refuse a guide with no colour key at all.** One does not colour-code; every
option fell through to black and it contributed 388 false averages, which are
worse than nothing because they look like verdicts. A guide whose ratings are
more than 90% black is now refused and reported.

## A guide's title is a printed name

`leaks.py` caught this and nothing else would have: the URLs carried titles, and
one title contains an epic destiny's printed name. Every URL in the registry is
now stripped to its bare thread id, which EnWorld serves the same page for. Worth
remembering for any future source — a link is not automatically name-free.

## Measured, across all 36

* **4,215 refs rated** — 2,251 powers, 1,507 feats, 406 items, 51 races — plus
  60 set aside as green or pink.
* Tier spread: 527 red, 783 purple, 2,612 black, 1,926 blue, 935 sky, 156 gold.
  Black the largest bucket at 39% is the shape a rating distribution should have.
* **831 refs are rated for more than one class, and 344 differ by two tiers or
  more** — the strongest evidence for keying by class. 615 are rated twice for
  the *same* class by different guides at different tiers, which is genuine
  disagreement; the later guide wins.
* On the first guide alone, for comparison: 1,293 bold names → 374 refs.
* **Accuracy 99.5%**: of 195 resolved powers, 194 belong to the class the guide
  is about and one is a warlock row, which a wizard guide may legitimately
  mention. This check needs no human and no name — a wizard guide naming a
  fighter power has mis-resolved, and that is countable.
* **Coverage 74%** of the wizard's 187 written heroic-tier rows: 87% of dailies,
  68% of encounter rows, 60% of at-wills. The plan estimated 10–20%.
* Tier spread: 65 red, 87 purple, **92 black**, 81 blue, 46 sky, 3 gold. Black
  being the largest bucket is what a guide should look like, and its absence was
  the signal that the first parse was wrong.
* 147 runs resolved to something out of scope and are reported as such rather
  than counted as misses; 714 matched nothing in `names.json` at all — shorthand,
  prose emphasis, and options from books this compendium does not hold.
* 28 refs were bold in more than one place at different tiers. The better reading
  is kept, because an uncoloured mention is usually incidental bolding rather
  than a verdict, and the count is reported rather than buried.

## Coverage is very uneven, and a caller has to know that

Share of each class's **written heroic-tier rows** (levels 0/1/3/5/7/9) that a
guide has rated. 55% overall, and the spread is what matters:

| | | | |
|---|---|---|---|
| fighter 90% | swordmage 88% | paladin 87% | seeker 86% |
| sorcerer 86% | warlock 86% | rogue 84% | ardent 83% |
| battlemind 83% | wizard 78% | psion 77% | runepriest 77% |
| barbarian 71% | avenger 70% | assassin 62% | cleric 43% |
| bard 30% | druid 30% | ranger 25% | monk 22% |
| shaman 14% | warlord 7% | artificer 2% | warden 1% |
| **invoker 0%** | | | |

The four at the bottom are not failures of the reader. The artificer and warden
guides rate mostly feats, items and paragon paths rather than their own class's
powers — which is why their class could not be detected either. The warlord and
shaman guides are simply short: 71 and 81 rated options against a fighter guide's
491.

**So a score built on this will be confident about a fighter and ignorant about a
warden.** `rated()` is what distinguishes the two, and a scorer that treats an
unrated option as average will quietly flatten half the classes in the game. This
is the strongest practical reason the API returns `None` rather than 2.5.

## What this is not

A rating is what a player optimising for victory thinks. That is not the same as
what this project wants: the round-count target is 7–8, and a game-breaker
shortens fights. Expect some terms to want a sign rather than a magnitude, and
treat a sharp drop in round count after wiring this in as a finding rather than
a success.
