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

**All 25 classes have a guide.** `GUIDED_CLASSES` is what a caller checks.

The avenger came from a Google Site of **51 sub-pages**, which needed a crawl: the
colour key is on the landing page and the ratings are spread over the rest, so
they are fetched and concatenated into one document.

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

**Read colour *names*, not only hex.** `color: DarkTurquoise` is a rating and
`#00ccff` is the same rating, and the reader saw only the second. Over **five
thousand** ratings were being discarded — `DeepSkyBlue` 947 times, `MediumBlue`
756, `Purple` 602, `DarkTurquoise` 531, `Red` 333, `Crimson` 144, `GoldenRod` 48.
`NAMED` folds each onto the canonical hex of the tier it means, so there is one
code path and a guide's own stated key still wins: a legend written in
`DeepSkyBlue` arrives as `#00ccff` and reads the same as a legend written in hex.

This is the mistake that cost most, and it was diagnosed as the opposite. One
guide came out 100% black, so it was **refused** as a guide whose colour had been
lost in a forum migration — and the page's own prose, which mentions "the sky blue
rating", was read as evidence for that story rather than against it. The colour was
there all along in `DarkTurquoise`. Reading it recovered 388 ratings and the
twenty-fifth class. The refusal guard stays, because a guide with genuinely no key
would still be worth refusing, but nothing trips it now.

## A guide's title is a printed name

`leaks.py` caught this and nothing else would have: the URLs carried titles, and
one title contains an epic destiny's printed name. Every URL in the registry is
now stripped to its bare thread id, which EnWorld serves the same page for. Worth
remembering for any future source — a link is not automatically name-free.

## Measured, across all 36

* **4,405 refs rated** — 2,359 powers, 1,585 feats, 410 items, 51 races — plus
  60 set aside as green or pink. No guide refused.
* Tier spread: 569 red, 860 purple, 2,486 black, 2,165 blue, 1,084 sky, 163 gold.
  Black at 34% with blue close behind is a healthier shape than the 70% black an
  earlier pass produced.
  Black the largest bucket at 39% is the shape a rating distribution should have.
* **856 refs are rated for more than one class, and 370 differ by two tiers or
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
guide has rated. 57% overall, and the spread is what matters:

| | | | |
|---|---|---|---|
| fighter 90% | swordmage 88% | paladin 87% | warlock 86% |
| seeker 86% | sorcerer 86% | invoker 84% | rogue 84% |
| battlemind 83% | ardent 83% | wizard 78% | psion 77% |
| runepriest 77% | barbarian 71% | avenger 70% | assassin 62% |
| cleric 43% | druid 30% | bard 30% | ranger 25% |
| monk 22% | shaman 14% | warlord 7% | artificer 2% |
| warden 1% | | | |

The four at the bottom are not failures of the reader — unlike the invoker, which
was, and is now at 84%. The artificer and warden
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
