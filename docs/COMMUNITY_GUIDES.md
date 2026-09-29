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
| *(unrated)* | | **2.5** |
| purple | outclassed, or only situationally good | 1.5 |
| red | do not take this | 0.0 |

**Black is invisible, and that matters.** No guide *colours* its black text —
black is the default, so there is no span to find. Measured on the first guide:
67 red, 90 purple, 82 blue, 46 sky, 3 gold, and **zero black**. So "the author
called this average" and "the author never mentioned it" are indistinguishable
in the markup, and both land in the unrated bucket. That is the argument for
unrated sitting at 2.5 rather than at 3.0 or at 0: the bucket genuinely holds
both, so it belongs just below rated-average and nowhere near bad.

**Green is not a tier.** Several guides use it for options that are "a different
kind of useful", and the first guide's key says outright that *a lot of
non-combat options fall here*. That is this project's `narrative=` and
`out_of_combat=True` category, so green is recorded in `OUT_OF_COMBAT` and
excluded from the combat score rather than ranked against things it cannot be
compared to.

## Every guide needs its own colour map

The scale is conventional; the hexes are not. The first guide's author states
that the shades were chosen to suit photosensitive eyes, and uses a teal
(`#33cccc`) where the convention would use a pale blue. So each guide's key is
read off its own text and recorded by hand in `GUIDES`. Inferring a tier from a
hue is how a red becomes a gold.

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

| guide | class | rated | note |
|---|---|---|---|
| `wizard` | wizard | 288 refs | states its key in full; teal is its sky blue |

## Measured, first guide

* 836 coloured runs → **288 refs rated**, 18 out-of-combat.
* **Accuracy 99.3%**: of 145 resolved powers, 144 belong to the class the guide
  is about and one is a warlock row, which a wizard guide may legitimately
  mention. This check needs no human and no name — a wizard guide naming a
  fighter power has mis-resolved, and that is countable.
* **Coverage 55%** of the wizard's 187 written heroic-tier rows: 66% of dailies,
  52% of at-wills, 46% of encounter rows. Well above the 10–20% the plan
  estimated.
* 118 runs resolved to something out of scope and are reported as such; 405
  matched nothing in `names.json` at all, of which 305 are distinct and almost
  all one to three words — shorthand, headings, and options from books this
  compendium does not hold.
* 4 refs were rated twice at different tiers. The better reading is kept, which
  matches the "best case" the doctrine asks for elsewhere, and the count is
  reported rather than buried.

## What this is not

A rating is what a player optimising for victory thinks. That is not the same as
what this project wants: the round-count target is 7–8, and a game-breaker
shortens fights. Expect some terms to want a sign rather than a magnitude, and
treat a sharp drop in round count after wiring this in as a finding rather than
a success.
