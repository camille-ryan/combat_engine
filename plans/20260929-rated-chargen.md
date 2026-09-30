# Headless chargen draws on the community ratings, and win rate becomes readable

*(On implementation, copy to `plans/20260929-rated-chargen.md` per the repo
convention.)*

## Context

`src/combat_engine/ratings.py` now holds **5,240 rated options** across all 25
classes, read from 37 community guides. Nothing reads it. Meanwhile
`chargen/choices.py`'s fourteen weights are all numbers I invented, which is what
#213 objects to and asks for a "doctrine based" scorer instead.

The second half matters more than the first. **#75 was closed because win rate is
unreadable**, not because it was fixed:

> feats and items are drawn at random, so the win rate measures arbitrary builds
> rather than the engine

So this is the change that makes the metric mean something. #217's closing note
says what makes a measure readable here — *"the same seeded fight with pinned
feats, so before and after are comparable"* — and that is the standard to hold to.

Two facts to keep in view while reading any result:

* **Above level 1 the party essentially never wins** — #75 measured 2/30 at level
  5 and 0/30 at level 10. Level 1 is the only level where a win-rate difference
  can be read at all.
* **The round-count target is 7–8**, not the 3–4 in #217's title, which that
  issue's last comment establishes was itself the error.

## Scope

Four things, in dependency order.

### 1. A rating term, and a weighted draw

`chargen/choices.py` already has the right shape: `Choice(ref, score, terms)`, a
`WEIGHTS` table, and `sample(options, rng)` which draws with weight proportional
to score and deliberately never takes the argmax. One new term goes beside the
fourteen:

```python
"guide_rating": 3.0,   # what somebody who played the class thought
```

fed from `ratings.score(ref, cls)`. Use `score()` rather than `rating()` here
because `sample` needs a number — but gate on `rated()` first so an unrated option
contributes **no term at all** rather than a 2.5 that competes with real evidence.
That distinction is the whole point of the API and is documented in
`docs/COMMUNITY_GUIDES.md`.

Reaches `race_options`, `feat_options` and `wield_options`, all three of which
already return ranked `Choice` lists.

### 2. V-class dump-stat exclusion

**Owner's rule: an option is refused if its payoff keys off an ability that is
neither the build's primary nor its secondary.** Strictest of the three readings
and the one chosen deliberately.

`chargen._leans_on` already does most of this: it reads a row's own source for
`c.<ability>_mod`, because "a body saying `c.int_mod` needs Intelligence and no
header field says so". It currently *rewards* leaning on primary or secondary;
this needs the complement — refuse when the only ability it leans on is outside
both.

Why it matters here specifically: 19 of 25 classes draw from one power pool and
differ only on the **secondary**, so for those the other leg's secondary is your
dump stat. An artificer with Constitution second should not be handed the
Wisdom-payoff options, and that is exactly the distinction one guide expressed by
colouring the two halves of a name differently.

Four classes differ on the *primary* — cleric, paladin, ranger, warlock — and
`chargen._fits` already separates those correctly. No change needed there.

### 3. An item floor

`chargen.treasure` picks uniformly with `rng.randrange` from a pool filtered by
enhancement slot, band, level and base-item fit. Replace that with a weighted
draw:

* **exclude** anything rated below black (< 3.0);
* **keep** unrated items in the pool at `UNRATED` weight, per the owner's call.

**State the expected effect plainly, because it is nearly nothing.** Measured
pools: a fighter's level-1 weapon slot is 124 items of which **1** is rated; the
warden has **0** rated items in any slot; and every rated item in those pools is
already ≥ black, so the floor excludes nothing today. A lone rated blue against
123 unrated is a 1.3% draw. The item half of this will not move the win rate and
should not be expected to — it is scaffolding for when item coverage grows.

### 4. `scripts/winrate.py` — the instrument that does not exist

There is no batch fight runner. `scripts/fight.py` plays one fight and prints
`winner`; `Encounter.winner` and `Encounter.over` are the API. #75's numbers were
produced ad hoc and the method was never committed.

```
uv run scripts/winrate.py                    30 seeds, levels 1/5/10
uv run scripts/winrate.py --seeds 60 --level 1
uv run scripts/winrate.py --draw chassis|scored|rated
```

Reuses `fight.py`'s construction — `chargen.spawn` for the party, `loader.pick`
for a standard encounter, `LinearPolicy` on both sides, `install`, `take_turn`.
Reports wins/seeds **and median rounds**, because rounds is the measure #217
established as readable and it should not regress while win rate is chased.

`--draw` is what makes before/after comparable on the same seeds: `chassis` is
`SCORED_CHOICES = False`, `scored` is today's scorer, `rated` is this change.

## Files

| path | what |
|---|---|
| `src/combat_engine/chargen/choices.py` | the `guide_rating` term, the dump-stat refusal, `item_options` |
| `src/combat_engine/chargen/__init__.py` | `treasure` draws weighted; `_leans_on` gains its complement |
| `scripts/winrate.py` | new instrument |
| `docs/COMMUNITY_GUIDES.md` | record what the draw now consumes |

`src/combat_engine/ratings.py` is **not** hand-edited — it is generated by
`scripts/guides.py`.

## Verification

* **`winrate.py --draw chassis` against `--draw rated`, same seeds, level 1.**
  The headline. 60 seeds rather than 30, because a 26/30 baseline needs more than
  30 to distinguish a real move from noise.
* **Median rounds in the same run.** Target 7–8. A sharp fall is a *finding*, not
  a success: these guides rate for winning and a shortened fight means the party
  got stronger than the encounter, which is the balance problem #217 watches.
* **`replay verify`** — fixtures will move, re-recorded in a commit containing
  nothing else, per `scripts/CLAUDE.md`.
* **`uv run scripts/chargen.py --class fighter --level 5`** before and after: does
  the ranked list change in a way that reads sensibly, and is the 1d4 whip still
  being chosen (#234)?
* **`uv run scripts/expect.py --class fighter --level 5 --scored`** — the weapon in
  hand, which is the concrete symptom #234 named.
* **`leaks.py`, `lint.py`, `ruff`**, and `audit.py --changed`. Chargen is in
  `audit.py`'s `WIDE` list, so expect the wide run.

## Risks worth stating before starting

* **The item half will show no effect.** Quantified above. If the win rate moves,
  it moved because of feats, races and weapons.
* **Coverage is uneven, so the effect is class-dependent** — 93% of a fighter's
  heroic rows are rated against 45% for a warden and 24% for a monk. A party
  average will understate the effect on well-covered classes.
* **#253 inflates some ratings upward.** A coloured heading's rating is attributed
  to everything it lists, which skews high. Not fixed here.
* **Optimisation is not balance.** A gold rating is what a player chasing victory
  wants; this project wants a 7–8 round fight.
* **Win rate is only readable at level 1.** Report 5 and 10 for completeness and
  expect both to stay near zero — at level 10 also confounded by #244, where a
  dealt character has almost no attack powers.

## Not in this plan

* Fixing #249 (the rider gap), #253 (heading mis-attribution) or #256 (the build
  dimension). All three would improve the input; none blocks this.
* Retuning the existing fourteen weights. Adding a term beside them is not the
  same as retuning them, and the owner's instruction is that they stay.
* Any policy change. `LinearPolicy` is held fixed so the only variable is the
  draw — which is what makes the comparison mean anything.
