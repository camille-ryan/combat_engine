# Guide ratings as a seed score, and richer inputs for the policy

*(On implementation, copy this to `plans/20260929-guide-ratings.md` per the
repo convention.)*

## Context

Three things have converged on the same missing piece.

**#213 asks for exactly this, in Camille's words:** "create a scorer for feats
and items that takes into account the rest of the character so far. This should
also be doctrine based. Most characters should take expertise and improved
defenses." That last sentence *is* a rating — a feat tax, gold on the community
scale.

**The scoring work this session produced orderings but no magnitudes.** The
condition tiers are grounded in `engine/conditions.py`'s `RULES` and verified on
a board, and the single-against-area split is the only measure that separates a
controller. But nothing says how much more a lockdown is worth than a slow, and
every weight in `chargen/choices.py` is a number I invented.

**The damage half is broken anyway (#249).** `expect.py` misses every rider that
listens for `Hit`, so a rogue with combat advantage scores 5.70 against a
simulated 15.23. Any threat number built on it today would have to be redone. An
external ordinal rating does not depend on that being fixed first, so it is
work that can proceed now.

~50 community guides exist across four hosts, and they rate options on a
six-colour ordinal scale that has been stable in that community for fifteen
years. That is a large body of judgement about exactly the options this project
cannot currently rank.

## Outputs

Three, in dependency order.

1. **A tracked `ref → rating` table.** Refs and integers, no prose.
2. **Untracked prose notes**, for policy ideas the ratings themselves cannot
   carry — the reasoning, the rules of thumb, the "this combination is the
   whole build" observations. Camille's call, and it also keeps authored text
   out of the repository.
3. **The policy and chargen derivation** built on (1).

## The scale

Six colours, confirmed against the community convention, plus the default
Camille chose:

| colour | meaning | value |
|---|---|---|
| gold | game-breaker, or a mandatory tax | 6 |
| sky blue | superior | 5 |
| blue | good | 4 |
| black | average | 3 |
| *(absent from every guide)* | nobody wrote about it | **2.5** |
| purple | usually bad, or needs a special case | 1.5 |
| red | always bad | 0 |

Unrated sitting just below rated-average is the point: a guide's silence is
weaker evidence than a guide's "average", but it is not evidence of badness.

**Why the down-weighting risk is smaller than it looks.** `choices.py` ranks
options *within one character's legal pool*. A class with no guide compares its
own options against each other, all at 2.5, flat — so the other terms decide and
nothing is crippled. The bias only bites on cross-class comparison, which is not
in scope here. Worth re-checking if a party-composition score ever arrives.

## Architecture

The name rule decides the shape, and the existing machinery already fits.

`game.db` carries **no name column** for power, feat, item, race or weapon —
only `ref`. Names live in git-ignored `localization/names.json` as a flat
`ref → name` map, read through `api/wire.py`'s `localisation()`. So:

```
fetch (cached, gitignored)
  → parse colour markup → (printed name, colour)
  → resolve via inverted localisation()  ← the only step that sees a name
  → emit  {ref: int}  +  {ref: source URL}   tracked, no prose
  → emit  prose notes, unresolved names      untracked
```

`scripts/leaks.py` is the gate and needs no change: it reads every name the
compendium has and greps every tracked file, exiting non-zero on a find.

### Files

| path | tracked | what |
|---|---|---|
| `scripts/guides.py` | yes | the instrument: fetch, parse, resolve, report |
| `src/combat_engine/ratings.py` | yes | `RATINGS: dict[str, int]`, `SOURCES: dict[str, str]` |
| `notes/` | **no** | prose notes, one file per guide |
| `.cache/guides/` | **no** | fetched HTML, so a re-run costs nothing |

`ratings.py` sits at package root rather than inside a component because both
`chargen` and `engine/policy` consume it, and putting shared data inside either
one would make the other import across a seam. Alternative considered and
rejected: emitting it into `game.db`, which is gitignored and so would not
survive a clone.

Two `.gitignore` additions: `/notes/` and `/.cache/`.

### Where it plugs in

Both consumers already take a flat dict of named numbers, which is why this is
cheap:

* **`chargen/choices.py`** — one new term, `"guide_rating"`, beside the fourteen
  already there. `feat_options` and `wield_options` read it.
* **`engine/policy.py`** — `Memory.worth(ref, default=5.0)` has a hardcoded
  default that a rating should supply instead. That one line is the single
  cleanest insertion point in the codebase: the learned mean already overrides
  it as fights accumulate, so a rating becomes a **prior** that play corrects.

## Stages

**Stage 1 — one guide, end to end.** Pick a single EnWorld-hosted class guide
(BBCode `[color=...]`, the simplest markup of the four hosts). Fetch, parse,
resolve, and **measure match accuracy against a hand-checked sample of 40 refs.**

This stage is a gate, not a step. If accuracy is below ~90%, stop and report
rather than proceeding — a ratings table that is 20% wrong is worse than none,
because it looks authoritative. Report the confusion cases either way.

**Stage 2 — the other three host formats.** Google Docs (CSS spans), Wayback
(old WotC markup), external sites. Each is a parser; the resolver is shared.
Rate-limit and cache; these are static historical documents and should be
fetched once.

**Stage 3 — level filter and emit.** This project is heroic tier: the measured
attack rows sit at levels 0–9 and level 10 prints none. Paragon and epic ratings
are noise here and should be dropped rather than stored, with the count reported
so the coverage figure is honest.

**Stage 4 — wire into chargen.** The `guide_rating` term, and `SCORED_CHOICES`
already exists as the switch. Fixtures will move; re-record in its own commit
per `scripts/CLAUDE.md`.

**Stage 5 — wire into the policy.** `Memory.worth`'s default. This is the
"richer inputs" half, and the condition terms from this session's measurements
belong here too — `denial_tier`, `area_multiplier`, `duration` — because the
guides independently confirm their ordering.

Stages 4 and 5 are separate commits and separately measurable. Do not do both
before measuring the first.

## Risks worth naming before starting

* **Resolution ambiguity is the real technical risk.** Names are not unique
  across classes, and a guide's shorthand will not match the compendium string
  exactly. Needs a confidence threshold, a hand-kept reject list, and the
  discipline that an unresolved name goes **only** to a gitignored path. A debug
  log of unmatched names is a file full of names; that is the trap.
* **Optimisation is not balance.** These guides rate options for a player trying
  to win. A gold-rated option may be one this project wants the dealer to
  *avoid*, because the round-count target is 7–8 and a game-breaker shortens
  fights. Expect to need a sign on some terms, and treat a sharp drop in round
  count after stage 4 as a finding rather than a success.
* **Copyright.** The ratings are judgements about game mechanics and are stored
  as `ref → integer` with a source URL; no authored text enters the repository,
  which is what keeping the notes untracked secures. Worth stating in the commit
  so the reasoning is on the record next to the names reasoning.
* **Coverage will be partial.** 9,793 rateable options against ~50 guides.
  Report the real figure rather than implying completeness.

## Verification

* **`leaks.py` green** — the gate, and the one that cannot be waived.
* **Resolver accuracy** on the stage-1 hand-checked sample, both the rate and
  the confusion cases.
* **Coverage reported** as rated/total per kind, and per class, so a class with
  no guide is visible rather than silently flat.
* **`uv run scripts/chargen.py`** before and after stage 4: does a fighter now
  take a sensible weapon? The known-bad case is the 1d4 whip (#234).
* **`replay verify`** after each of stages 4 and 5, re-recorded separately, with
  round counts before and after. The target is 7–8.
* **`audit.py`** is not widened by any of this: `scripts/` and a new top-level
  module are outside `WIDE`. Stage 5 touches `engine/policy.py`, which `NARROW`
  already exempts.

## Not in this plan

* **Fixing #249.** The rider gap makes the damage half of a threat score wrong,
  and it should be fixed — but an ordinal rating does not depend on it, which is
  why this can go first.
* **A party-composition score.** The one place the unrated default would
  genuinely bias things, and its own argument.
* **Retuning the existing fourteen `choices.py` weights.** Camille's standing
  instruction is that they stay as they are for now; adding a term beside them
  is not the same as retuning them.
