"""A policy that scores the three things `docs/AI_DOCTRINE.md` actually asks for.

`policy.features` gives 44 features and `policy.WEIGHTS` prices 37 of them, and every
one is an action kind, a hit chance or a count of targets. Nothing there can say
**where a square is good**, **how dangerous a creature is**, or **whether a heal is
worth casting** -- which is most of what the doctrine is about. This module adds those,
and holds the policy that weighs them.

**There is one policy, and this is it.** It began as a second one beside
`LinearPolicy` so that an A/B could attribute a regression -- "forty-five interacting
hand-set numbers cannot be moved one at a time" was the argument, and it was mine. The
A/B turned out to be the wrong instrument: both sides of the board run the same policy,
so an improvement helps the monsters as much as the party and largely cancels in the
win rate. Measured twice on fresh seeds, the gap never survived Holm while the tactical
counts moved hard.

So `LinearPolicy` is retired and the two weight tables are **one table of 52**.
Attribution comes from `scripts/scorecard.py` -- per-side tactical counts against a
committed baseline -- and from `scripts/doctrine.py`, which reports what each weight
fired on and what it contributed to the action actually chosen. That is finer-grained
than an A/B was, which is why the original objection no longer holds.

## Where it stands, measured

**80 fights a cell, seeds 201-280** -- fresh seeds again, and the only run that
measures the code as it now stands: the five fixes in 255859d landed after the
previous run, so the two cannot be pooled and the earlier figures do not carry
forward. Both sides run the same policy, `--draw scored`.

| | level 5 linear | level 5 doctrine | level 10 linear | level 10 doctrine |
|---|---|---|---|---|
| wins of 80 | 57 (71%) | 62 (78%) | 56 (70%) | 68 (85%) |
| exact p | | 0.469 | | 0.036 |
| under Holm | | keep null | | **keep null** |
| median rounds | 7.5 | 8.0 | 12.0 | **10.0** |
| party hit rate | 63% | 61% | 62% | 61% |
| **party provoked / fight** | 3.8 | **2.2** | 4.4 | **3.7** |

**Neither win-rate comparison survives correction, and the previous run's
`p = 0.000066` did not replicate.** That figure was measured on seeds 121-200 and on
different code; here level 10 comes to p = 0.036 against a Holm threshold of 0.025.
The direction has been positive in both runs at both levels, which is worth
something, but **this policy has not been shown to beat `LinearPolicy` on win rate
at the bar this instrument sets.** Said plainly because the earlier number was
reported as a win and reporting only the better of two runs is the forking path the
instrument's docstring warns about.

Part of the reason is that the baseline moved: `LinearPolicy` won 47 and 49 of 80 on
the old seeds and 56 and 57 here, so these fights are easier for the party and there
is less room above them.

**What did replicate, and it is the measure to read at this sample size,** is
provocations -- thousands of events rather than one outcome a fight:

    party opportunity attacks conceded, level 5     304 -> 174   (-43%)
    party opportunity attacks conceded, level 10    352 -> 293   (-17%)
    the worst single offender at level 5, p13970     99 ->  55

That is what the five fixes in 255859d were aimed at and it moved hard. Median
rounds also came down from 12 to 10 at level 10, toward #217's 7-8 target, while
level 5 sits at 8.0 either side.

### What the balance looks like now, which is the thing to worry about

40 fresh seeds a level, one policy both sides, after everything above:

    level   wins    rate   median rounds
      1    40/40    100%        3.0
      5    36/40     90%        6.0
     10    35/40     88%        9.0

**The party wins about nine in ten above level 1, and neither median is inside #217's
7-8.** Camille's reason for abandoning the A/B was that both sides run the same policy
so an improvement cancels -- right about the measurement, wrong about the outcome,
because the defects were nearly all ones only a character could suffer: 231 inert rows
chosen against the monsters' 0, 54 idle melee turns against 7. Fixing a shared scorer
helped one side. Filed as #267; it is a balance question, not a scoring one.

And none of it means the policy plays well. The scorecard still reads 169-178 inert
choices a run, 41 idle melee turns at level 10, and 18% of decisions settled by a tie.
It is winning 90% while still playing badly.

### Pruning the destinations, which is where a turn's cost was

Camille's suggestion, and it is worth as much for the quality of play as for the
speed. `actions.legal` offers every reachable square -- measured, **210 of a
creature's 226 options are a `move` or a `run`** -- and scoring all of them came to
15,760 evaluations for one fight. `worth_standing` applies the rule: a creature that
fights in melee wants to end adjacent to something, one that does not wants to be
out of reach but in range, and approaching is considered only when neither is
available. 15,760 -> **2,623** scored actions, and "moved away" provocations fell
from 71 to 41 at level 5.

A caution about the timings quoted anywhere near this: an earlier note in this
docstring had one fight at 25 seconds against `LinearPolicy`'s 13, and that
comparison was **measured while an 80-seed run was saturating the machine**. Both
were about 2.5 seconds idle. The call counts are the figures to trust, being immune
to what else is running: memoising the board facts took one fight from 128M function
calls to 62M, with `query.enemies` going from 226,472 calls to 31,857.

### The flanking terms were added after that table and did not improve it

Camille asked whether creatures try to get into a flank at all, and whether anyone
sets one up for an ally. Measured over 20 fights at level 5, party attacks made
while flanking:

    LinearPolicy    6.7%
    DoctrinePolicy  8.5%

So yes, and weakly. Two findings came out of asking.

**`takes_flank` was paying for standing in a flank, not moving into one.** `dest`
falls back to the square the creature already occupies, so every action taken from a
flanking square collected it -- and the commonest chosen action it fired on was
**`end`, 116 times against `move`'s 30**. A bonus for passing the turn, in the term
meant to buy aggression. It is now scored only on a move *into* a flank and on an
attack against a creature already flanked, which is the roll the +2 applies to.

**`sets_up_flank` is new and has not earned its weight.** It implements the
`AI_DOCTRINE.md` line "setting up a flank ... is nearly as good as flanking", which
nothing read. It fires -- 43 chosen actions over 4 fights -- and on the 40 held-out
seeds it moved the win rate *down*, 30 of 40 to 27 at level 5 and 33 to 32 at level
10. Both differences are well inside noise, so it is kept at a low weight on
doctrine grounds rather than on evidence, and it is the first thing to re-examine
when the weights are re-fitted.

## What is scored, and what each rests on

**Threat removal**, and hit points are part of it rather than beside it. A
creature's threat is `threat.threat` -- its best-case damage over three rounds, as
a share of the health it is aimed at -- and an action removes the fraction of that
threat matching the fraction of the creature's remaining hit points it takes off.
So a killing blow removes all of it and half its hit points removes half, without
"kill" needing to be a separate idea. This is what should make a striker finish a
bloodied enemy rather than open on a fresh one.

**Conditions do not enter this term at all, and `threat.CONDITION_THREAT` is read
by nothing.** An earlier version of this paragraph said they entered "through"
that table, which was false: the table exists, every entry is 0.0 by instruction,
and no code path consults it. That is precisely the "weight nothing consults"
failure the root `CLAUDE.md` calls this component's commonest, written into the
module whose docstring cites it. Recorded here rather than quietly corrected.

Wiring it needs a signal that does not exist yet. **No `Power` header declares the
conditions a row applies** -- there is no such field, so `immobilized` is knowable
only by running the body. The clean way is the scratch board `threat.board` already
builds: run the row there and collect `ConditionApplied`, which carries the
condition *and* its duration. See #263, and the four things that have to be settled
before numbers go into the table.

*What this axis is not.* `notes/DOCTRINE.md` §1 is that threat has two axes which
pull against each other -- *reduction* and *redirection* -- and that a defender
immobilising the enemy already beside it removes almost no damage and has done its
job perfectly. Only reduction is here. A defender scored on reduction alone plays
like a striker, and that is a known hole rather than an oversight.

**Position.** Evaluated at the square an action would leave the creature in, which
is why the flanking terms use `Grid.flanks` and `Grid.cover` -- both take squares
rather than creatures, so a *hypothetical* destination can be priced without
moving anybody. Moving a creature to find out would emit `EnterSquare`, refresh
the zones, and possibly set off whatever is standing in them.

Hostile terrain is approximated by **a zone an enemy owns**, because a `Zone`
records `owner`, `squares`, `difficult` and `blocks_sight` and does *not* record
that it deals damage -- the damage lives in the row's own watcher. So "this square
hurts" is not answerable today and "this square belongs to the enemy" is.

**What a move costs and what it buys, in the same currency.** Camille's
correction, and the most load-bearing thing here. `LinearPolicy` charges a flat
-5.0 for provoking, which cannot tell a brute's free swing from a minion's; and it
has nothing at all to say for the other side of the trade. So:

* `threat_conceded` is the expected damage of the opportunity attacks actually
  handed over, as a share of my own side's health -- "if the expected damage is 10
  out of 100 total party hp, that's quite significant";
* `reach_gained` is the difference between the best attack available from the
  destination and the best available without moving, as a share of theirs. A close
  blast that would catch the whole enemy party is worth a free swing against you,
  and no constant can express that.

Both *modulate* `policy.features`'s flat `provokes_now` and `provokes_avoidably`
rather than replacing them -- see `threat_conceded`'s weight for why that was
measured rather than assumed.

**Healing.** Two separate problems, and the first is why healing scores badly
today: `allies_caught: -7.0` is the term that stops a wizard dropping a burst on
its own party, and a heal targets allies on purpose, so the scorer reads mending
the fighter as friendly fire. `heals` identifies a healing row by reading its body
for `c.heal`, `c.surge` or `c.temp_hp`, the same way `chargen._pays_off_through`
reads a body for `c.<ability>_mod` and for the same stated reason -- no header
field says so. `score` then clears `allies_caught` for such a row.

The second is that a heal is worth what it *restores*: the hit points the target is
actually missing, as a share of the **party's** pool. Healing 20 onto an ally five
below full is worth five, and healing anybody at full hit points is worth nothing.
Against the party pool rather than the target's own maximum, so that a heal and a
kill are weighed against the same thing -- which is the point of a single currency
and is what `SHARE` below is.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any

from . import threat as T
from .actions import Action
from .components import Health, Position, Side
from .dsl import get
from .events import Event, OpportunityWindow
from .grid import distance
from .policy import (
    WEIGHTS,
    Memory,
    _allies_of,
    _is_square,
    _opportunity_options,
    _square,
    features,
)
from .query import (
    alive,
    creatures,
    enemies,
    flanked_by,
    flankers,
    is_,
    squares,
)
from .turns import Encounter
from .types import ActionType, Condition, Team

#: The doctrine half of the weight table. Merged with `policy.WEIGHTS`'s 37 into the
#: one dict the policy carries; kept separate here so `scripts/doctrine.py` can report
#: on these terms specifically, and because they share one currency and the others do
#: not.
#:
#: **Five of these are one currency and share one weight.** `threat_removed`,
#: `threat_conceded`, `reach_gained` and `healing_given` are each a *share of a
#: side's whole health pool*, so `SHARE` is the exchange rate between "a fraction
#: of a team's health" and a score, and it is deliberately the same number for all
#: of them. Mixing currencies is what went wrong first: the flat terms below were
#: set at 1.5 to 3.0 while a typical share-term came to 0.05, so a +2.5 for
#: flanking outbid the whole threat model and the policy chased flanks into free
#: hits -- 162 opportunity attacks over 20 fights against `LinearPolicy`'s 53.
#:
#: So the flat terms are priced *relative to* a share. A +2 to hit is worth about
#: a tenth of one attack's damage, and one attack is a few percent of a pool, so a
#: flank is worth a few hundredths of a share -- which is where these now sit.
#:
#: **Re-fitted from 75 to 15 when the currency got bigger.** `potential` now counts
#: what an area row catches and measures against real targets, so a creature's
#: three-round threat went from a fraction of the party pool to a large share of it
#: -- and `threat_removed`'s mean contribution to the chosen action went from 9.43 to
#: 27.57 at the old weight. That is three times the -9.0 below, which is the one
#: thing the inequality says it must stay under. 15 puts it near 5.5.
#:
#: **The inequality, which is what sets this rather than taste.** `LinearPolicy`
#: charges -9.0 for a
#: ranged attack made from inside melee when a shift was available (-5.0 plus
#: -4.0), and that penalty is load-bearing: it is what stopped the party walking
#: into free hits. Two things have to hold at once. A single attack's
#: `threat_removed` must stay *well under* 9.0 or it re-breaks that (at 75 it comes
#: to about 1.8, which is `hit_chance`'s own contribution). And a genuinely good
#: repositioning -- a close blast that catches three enemies instead of one, about
#: 0.12 of the enemy pool -- must be able to *reach* 9.0, or the case Camille
#: raised could never fire. 75 is the smallest round number satisfying both.
#:
#: **One number does not currently serve every level, and the reason is not the
#: currency.** Measured, mean contribution to the actions actually chosen:
#:
#:     term              level 1   level 5
#:     reach_gained        49.6       1.7
#:     threat_removed      11.4       1.2
#:
#: The first reading of that was that a share of a health pool is not level-stable.
#: It was wrong, and checking the characters was what showed it: levelling
#: *replaced* a character's rows instead of adding to them, so a level-5 wizard
#: held **no attack-declaring rows at all** and a level-10 rogue none either. That
#: was #244, a chargen bug rather than a property of the scale, and it is fixed --
#: attack rows known, before -> after:
#:
#:     wizard   L1  4 -> 4     L5  0 -> 5     L10  0 -> 7
#:     rogue    L1  4 -> 4     L5  1 -> 6     L10  0 -> 8
#:     fighter  L1  6 -> 6     L5  3 -> 8     L10  2 -> 10
#:
#: With that fixed the raw figure is roughly level-stable -- 20.6, 39.4 and 31.1
#: hit points of best case over 3 rounds for the fighter at levels 1, 5 and 10,
#: where it used to fall 48.7, 14.9, 6.7. So `SHARE` is still fitted on level-5
#: numbers that have now moved, and the weights above want re-measuring.
#:
#: The currency is expected to hold. At higher levels hit-point removal simply
#: takes more rounds, which is also why control ought to matter *more* there -- it
#: removes threat at once where damage removes it over time. `CONDITION_THREAT` is
#: where that gets expressed and it is still zeros (#263).
SHARE = 15.0

DOCTRINE: dict[str, float] = {
    # The headline. A share of one side's whole health pool is a small number --
    # a level-5 monster's best three rounds come to 4-13% of the party -- so the
    # weight has to be sizeable for the term to mean anything beside `hit_chance`
    # at 3.0.
    #
    # **Measured down from 60.0, which was too large by three times.** At 60 the
    # term contributed a mean of 7.79 to the actions actually chosen, against a
    # -5.0 penalty for provoking and -4.0 for provoking avoidably -- so the
    # scorer would walk into a free hit to reach whichever enemy it had decided
    # was dangerous. Over 40 seeded fights at level 5 the party provoked 199
    # opportunity attacks against `LinearPolicy`'s 116, for no gain in win rate
    # and a slightly *lower* hit rate. 20.0 puts its mean contribution near
    # `hit_chance`'s, which is where a tiebreaker between attacks belongs.
    "threat_removed": SHARE,
    # **What a condition buys the party, which was worth exactly nothing.** A -2
    # to a target's AC, or anything that makes it grant combat advantage, raises
    # every attack the party makes at it. Same currency as the three above -- a
    # share of a health pool -- but the *enemy's* pool, because it is our damage
    # going up rather than theirs coming down.
    "party_enabled": SHARE,
    # **What provoking actually costs, on top of the flat penalty rather than
    # instead of it.** Camille's point is that -5.0 cannot distinguish a brute's
    # free swing from a minion's, and this is what does -- the expected damage of
    # the swings actually conceded, as a share of my side's health.
    #
    # It *modulates* `policy.features`'s `provokes_now` and `provokes_avoidably`
    # rather than replacing them, and that was measured rather than chosen:
    # switching those two off and leaving this in its place dropped the cost of
    # provoking from -9.0 to about -0.8, and the party went from 53 opportunity
    # attacks over 20 fights at level 5 to 140. The flat pair is a calibrated
    # baseline; this is the part that varies with who is swinging.
    "threat_conceded": -SHARE,
    # And what the move *buys*. Camille's rule: the OA is worth paying when the
    # square on the far side of it is worth more than the swing costs -- getting
    # a close blast onto the whole enemy party being the case that makes it
    # obvious. Same weight as the two above, because it is the same currency.
    "reach_gained": SHARE,
    # **Standing in your own blast.** `policy.features` excludes the caster from
    # `allies_caught` -- `t != actor` -- which it does so that a `target=SELF` buff
    # is not read as friendly fire, and which makes catching *yourself* in your own
    # area attack completely free. Two reviewers of a level-10 sweep found the same
    # wizard doing it for seven rounds and dying of it. Priced against its own hit
    # points, exactly like `threat_conceded`.
    "self_harm": -SHARE,
    # **A buff that is already on you.** Re-applying it adds nothing and costs the
    # action. `policy.features` has `swaps_stance` for the `STANCE`-tagged case and
    # nothing for the rest, so a defender spent three consecutive rounds re-casting
    # the same inert self-buff while the party fought without it.
    "already_on": -4.0,
    # Flanking is +2 to hit for two creatures rather than one, and the guides
    # treat setting one up as a striker's ordinary business.
    "takes_flank": 0.6,
    # "Nearly as good as flanking", per `AI_DOCTRINE.md`, so a little under
    # `takes_flank` -- it is a flank an ally still has to spend a move to take,
    # and the enemy moves in between.
    "sets_up_flank": 0.4,
    # Being flanked is the same +2 handed to two enemies. `AI_DOCTRINE.md` lists
    # it under bad squares in as many words.
    "becomes_flanked": -0.8,
    # Cover is a -2 on everything aimed at you, for as long as you stand there.
    # **Signed**, not a flag: the value is the change in cover, so the same
    # weight prices losing cover as a cost. Named for the delta it is.
    "cover_change": 0.4,
    # A zone an enemy put down. Not known to deal damage -- see the module
    # docstring -- so priced as suspicion rather than as a hit.
    "into_enemy_zone": -0.6,
    # Difficult going costs a square of movement, which is small and real.
    "into_difficult": -0.2,
    # What a heal puts back, as a share of the **party's** pool -- the same
    # currency as the three above, so mending the fighter and killing the brute
    # are weighed against one another rather than on two different scales.
    "healing_given": SHARE,
    # Healing somebody who is not hurt. A separate term from the above rather
    # than a zero in it, so that choosing the wrong target is visibly penalised
    # instead of merely scoring nothing.
    "healing_wasted": -1.0,
    # A heal on a creature that is about to drop is worth more than the hit
    # points say, which is the surge-saturation point in `AI_DOCTRINE.md`.
    "heals_the_dying": 2.0,
}

#: The verbs a body calls to put hit points back. `Cast.heal`, `Cast.surge` and
#: `Cast.temp_hp`. Temporary hit points are in because they soak the next blow,
#: which is the same job from the policy's point of view.
_HEAL_VERBS = ("c.heal(", "c.surge(", "c.temp_hp(")

#: The verbs a body calls to *help* an ally without healing it -- a bonus to
#: attack or defence, a resistance, a saving throw. Read for the same reason the
#: healing verbs are: no header field says a row is beneficial.
#:
#: **Found by reading a transcript.** A party-wide +1 to attack scored -15.56 and
#: was never once chosen, because the friendly-fire exemption recognised healing
#: and nothing else -- so `allies_caught` charged -7.0 per ally for handing them a
#: bonus. Free value the scorer read as a mistake.
_HELP_VERBS = ("c.bonus(", "c.resist(", "c.save_bonus(", "c.regen(")

#: Answers cached per ref -- reading a body with `inspect.getsource` is far too
#: slow to do once per option per turn.
_HEALS: dict[str, bool] = {}

#: Same, for the helping verbs.
_HELPS: dict[str, bool] = {}


def heals(ref: str) -> bool:
    """Does this row put hit points back?

    Read out of the body, because no header field says so. #260 asks for one; it
    is not waited on here. `chargen._pays_off_through` reads a body the same way
    and records the same justification.
    """
    if not ref:
        return False
    got = _HEALS.get(ref)
    if got is not None:
        return got
    declared = get(ref)
    body = getattr(declared, "body", None) if declared is not None else None
    if body is None:
        _HEALS[ref] = False
        return False
    try:
        src = inspect.getsource(body)
    except (OSError, TypeError):
        src = ""
    out = _HEALS[ref] = any(v in src for v in _HEAL_VERBS)
    return out


def benefits(ref: str) -> bool:
    """Is this row *for* the creatures it targets, rather than against them?

    Heals, and also buffs: a row with **no attack line** whose body hands out a
    bonus, a resistance or a regeneration is helping whoever it names. The
    no-attack-line half matters -- plenty of attacks also lay a bonus on the
    caster, and those are not support.
    """
    if not ref:
        return False
    if heals(ref):
        return True
    p = get(ref)
    if p is None or p.attack is not None or p.body is None:
        return False
    got = _HELPS.get(ref)
    if got is None:
        try:
            src = inspect.getsource(p.body)
        except (OSError, TypeError):
            src = ""
        got = _HELPS[ref] = any(v in src for v in _HELP_VERBS)
    return got


#: Living enemies, per (board, round, creature). A board fact, and it was being
#: recomputed per candidate action: a profile of one level-5 fight found
#: `query.enemies` called **226,472 times** for 5.2 of 18.6 seconds, with
#: `query.creatures` behind it at 332,776. Nothing about the answer changes between
#: two candidate actions on the same turn.
_FOES: dict[tuple[int, int, int], tuple[int, ...]] = {}

#: `best_from` per (board, round, creature, origin). The other half of the same
#: profile: 28,278 calls for 4.7 seconds, and it is asked twice per action for the
#: same two squares over and over.
_BEST: dict[tuple[int, int, int, Any], float] = {}

#: Cover from the nearest enemy, per (board, round, creature, square). 29,798 calls
#: for 3.6 seconds, and `Grid.cover` traces corner to corner each time.
_COVER: dict[tuple[int, int, int, Any], int] = {}


def forget() -> None:
    """Drop the per-board memos. `scripts/winrate.py` calls this between fights."""
    _FOES.clear()
    _BEST.clear()
    _COVER.clear()
    _INERT.clear()


def _round(world: Any) -> int:
    return getattr(world, "round", 0)


def foes(world: Any, actor: int) -> tuple[int, ...]:
    """Living enemies of `actor`, memoised for the round."""
    key = (id(world), _round(world), actor)
    got = _FOES.get(key)
    if got is None:
        got = _FOES[key] = tuple(
            e for e in enemies(world, actor) if alive(world, e))
    return got


#: Per (board, caster, row): could the row accomplish anything at all?
_INERT: dict[tuple[int, int, str], bool] = {}


def inert(world: Any, actor: int, ref: str) -> bool:
    """Would this row accomplish nothing whatever?

    No attack line, no damage against the baseline, and no effect laid. **All three**,
    because any one alone is an ordinary row: a zone deals no damage as it goes down,
    a buff declares no attack, a mark lays an effect and does neither.

    `threat.row_damage` and `threat.row_effects` already answer two of the three off a
    scratch-board run, so this costs a cache lookup after the first ask.

    **What it is for.** `is_power` is a flat +6.0 and nothing asked whether the row
    could do anything, so the scorer spent **231 of 1,127 party decisions at level 10
    on rows that provably accomplish nothing** -- 20% of its turns -- while the
    monsters did it zero times, holding three or four attack rows each against a
    character's dozens of utilities. #264.
    """
    key = (id(world), actor, ref)
    got = _INERT.get(key)
    if got is None:
        p = get(ref) if ref else None
        if p is None or p.attack is not None or T.row_damage(world, actor, ref) > 0:
            got = False
        else:
            got = not T.row_effects(world, actor, ref)
        _INERT[key] = got
    return got


def running(world: Any, actor: int, ref: str) -> bool:
    """Is what this row lays already in place on this creature?

    **Three places to look, and the effect label alone is not enough.** A fighter's
    aura row leaves an effect labelled `defender aura` on its caster -- nothing with
    the ref in it -- and puts the ref on the *zone* instead, via
    `c.aura(1, label=c.ref)`. Checking labels alone therefore missed it entirely, and
    the row was re-cast twice a turn for seven consecutive rounds while its wizard
    died four squares away.

    So: an effect whose label carries the ref, a **zone of that name this creature
    owns**, or a stance of that name. `swaps_stance` in `policy.features` catches only
    rows tagged with `Keyword.STANCE`, and this row's keywords are empty while its
    body calls `c.stance`, so that guard could not see it either.
    """
    if any(eff.label.startswith(ref) for eff in world.effects.of(actor)):
        return True
    for _, zone in world.zones.all():
        if zone.owner == actor and zone.label == ref:
            return True
    stance = world.effects.stance_of(actor)
    return stance is not None and stance.label.startswith(ref)


def _square_of(world: Any, eid: int) -> Any:
    pos = world.get(eid, Position)
    return pos.square if pos is not None else None


#: What a creature swings when handed an opportunity attack, when it has no
#: `Powers.basic` of its own to name.
#:
#: **Read off the creature, not hard-coded.** `Powers.basic` says it plainly -- "a
#: monster points at one of its own abilities; everyone else uses the engine's melee
#: basic" -- and this asked for the literal `"mba"` from everybody. A monster has no
#: row by that id, so `row_damage` returned 0 and **every provocation against a
#: monster was priced at nothing**: two enemies standing over the wizard came to
#: -0.25 where the flat penalty alone is -9.


def provokers(world: Any, actor: int, dest: Any) -> list[int]:
    """Which enemies would get a free swing if `actor` walked to `dest`.

    `policy._would_provoke` answers the same question as a boolean; this needs the
    creatures themselves, because the *cost* of provoking is what each of them
    would do with the swing and they do not all hit equally hard.
    """
    from .grid import distance
    from .policy import _reach_of

    here = _square_of(world, actor)
    if here is None or dest is None:
        return []
    out = []
    for foe in foes(world, actor):
        reach = _reach_of(world, foe)
        there = _square_of(world, foe)
        if there is None:
            continue
        if distance(here, there) <= reach and distance(dest, there) > reach:
            out.append(foe)
    return out


def _basic_of(world: Any, eid: int) -> str:
    """Which row this creature swings on an opportunity attack."""
    from .components import Powers

    known = world.get(eid, Powers)
    return (known.basic if known is not None and known.basic else "mba")


def watchers(world: Any, actor: int) -> list[int]:
    """Enemies whose reach already covers `actor`, so each gets a free swing.

    The *other* way a creature concedes an opportunity attack, and the commoner one:
    not by walking out of a reach but by firing a ranged or area power while someone
    is standing over it. `provokers` answers the movement case; this answers this
    one, and they are different creatures.

    **Found by reading a transcript.** A wizard fired a ranged row with three melee
    enemies on it, took six opportunity attacks and about 27 damage in one turn, and
    the scorer had charged it a flat -9 -- the same as it would have charged for one
    enemy, because `threat_conceded` was wired into the movement branch alone.
    """
    from .grid import distance
    from .policy import _reach_of

    here = _square_of(world, actor)
    if here is None:
        return []
    out = []
    for foe in foes(world, actor):
        there = _square_of(world, foe)
        if there is not None and distance(here, there) <= _reach_of(world, foe):
            out.append(foe)
    return out


def conceded(world: Any, actor: int, foes: list[int]) -> float:
    """What conceding these swings costs, as a share of **my own** hit points.

    **Camille's correction, and the reason this is not a flat number.** A
    provocation is priced at what it actually hands over, and a -5.0 that does not
    move with the hitter cannot say that: a brute's free swing and a minion's are
    the same -5.0 to `LinearPolicy` and are not remotely the same event.

    **Against my own hit points, not my side's pool.** Camille's second refinement,
    and it is the one that matters: 15 damage is an inconvenience to an 85-hit-point
    fighter and most of a wizard. Measured against the pool, the wizard's danger
    disappeared into the party's total, and all three reviewers of a level-10 sweep
    independently found the same death -- a wizard taking the same opportunity
    attack four rounds running, losing 55 of 61 hit points, never stepping away.
    Divided by its own health, that fourth provocation prices at nearly everything
    it has.

    Clamped at 1, because a creature can only be killed once, so the figure reads
    directly as "this fraction of the way to dropping me".

    **Scaling it by the creature's own `threat` was tried and is wrong.** It keeps
    the shared currency -- losing me costs the enemy my whole three rounds -- but it
    inverts the thing this is for: the fighter's output is worth more than the
    wizard's, so the product made a swing at the 85-hit-point fighter *dearer* than
    the same swing at the 63-hit-point wizard. Fragility is the signal wanted here
    and hit points are what carry it.

    **It overstates non-lethal damage and that is a deliberate simplification.**
    Losing a quarter of your hit points does not cut your output by a quarter -- in
    these rules you fight at full strength until you drop. Read it as risk rather
    than as loss: a quarter of the way to contributing nothing.
    """
    if not foes:
        return 0.0
    health = world.get(actor, Health)
    if health is None or health.hp <= 0:
        return 0.0
    incoming = sum(T.row_damage(world, f, _basic_of(world, f)) for f in foes)
    return min(1.0, incoming / health.hp)


def _in_area(world: Any, actor: int, origin: Any, ref: str) -> int:
    """How many living enemies a row fired from `origin` would catch.

    Deliberately geometric and cheap -- distance against the row's own size --
    rather than the exact targeting `dsl` would do. This is asked for every
    candidate square of every move, which is thousands of times a turn, and the
    question it answers is "would stepping here bring more of them under the
    blast" where a square or two of error does not change the answer.
    """
    from .grid import distance

    p = get(ref)
    if p is None or p.attack is None or p.reach is None:
        return 0
    kind, size = p.reach.kind, max(1, p.reach.size)
    if kind == "personal":
        return 0
    caught = 0
    for foe in foes(world, actor):
        there = _square_of(world, foe)
        if there is None:
            continue
        if distance(origin, there) <= size:
            caught += 1
    # A melee or ranged row hits one creature however many are in range; an area
    # one hits everything it covers, and that is the whole difference here.
    return caught if kind in ("close_burst", "close_blast", "area_burst", "wall") \
        else min(1, caught)


def charge_reach(world: Any, eid: int) -> int:
    """How far away a creature can be and still be charged by this one.

    A charge moves up to speed and must end adjacent, so a target at distance `d`
    is chargeable when `d - 1 <= speed`: **speed + 1**. Zero for a creature with no
    melee attack to charge with, since a charge ends in a melee basic.

    The closing-path requirement `actions._charges` enforces is not re-checked here
    -- that needs a path per candidate square, and this is asked of every square of
    every move. So this is an upper bound: it can say "chargeable" where a wall
    makes it false, and never the reverse.
    """
    from .components import Movement, Powers

    known = world.get(eid, Powers)
    if known is None or not known.basic:
        return 0
    if not fights_in_melee(world, eid):
        return 0
    move = world.get(eid, Movement)
    return (move.speed if move is not None else 6) + 1


def threatens_from(world: Any, actor: int) -> int:
    """How far the enemy that reaches furthest could reach `actor`.

    Their melee reach **and their charge**, which is Camille's point: standing seven
    squares from something with speed six is standing inside its reach, and a scorer
    that only counted adjacency could not see that. This is the band a creature that
    does not want to be in melee should stay outside of.
    """
    from .policy import _reach_of

    worst = 0
    for foe in foes(world, actor):
        worst = max(worst, _reach_of(world, foe), charge_reach(world, foe))
    return worst


def best_from(world: Any, actor: int, origin: Any) -> float:
    """The best expected damage this creature could do from `origin`.

    A share of the enemy side's health, so it is the same currency as
    `threat_removed` and `conceded`. Used as a *difference* between two squares --
    Camille's rule: "compare expected consequences from the move vs the
    differential between the best attack after moving, and the best action without
    taking the OA". A close blast that would catch the whole enemy party is worth
    a free swing against you, and nothing in a flat provocation penalty can say so.

    **A square you could charge from counts as a square you could attack from.**
    Camille's rule, and it is what lets this term reward an approach that does not
    arrive. Without it, `best_from` paid only for squares with a target already in
    reach, so a creature ten squares out gained nothing by closing to seven and
    simply stopped -- measured, `idle_melee` went from 10 to 42 when
    `closes_distance` was removed and this was all that was left.

    It makes the figure a **step** rather than a gradient: non-zero inside charge
    range, zero outside it, flat within. That is the distinction worth having and it
    cannot saturate the way squares-travelled did, because there is only one step.
    """
    from .components import Powers

    key = (id(world), _round(world), actor, origin)
    hit = _BEST.get(key)
    if hit is not None:
        return hit
    known = world.get(actor, Powers)
    theirs = world.get(actor, Side)
    if known is None or theirs is None:
        return 0.0
    other = Team.ENEMY if theirs.team is Team.PC else Team.PC
    pool = T.pool(world, other)
    if not pool:
        return 0.0
    best = 0.0
    for ref in known.known:
        # **Only what it could actually use.** Counting a spent daily inflated
        # every destination equally by the best thing the creature owns, which is
        # both wrong and invisible -- the move looks worth an opportunity attack
        # on the strength of a card that is face down.
        if not known.available(ref):
            continue
        caught = _in_area(world, actor, origin, ref)
        if not caught:
            continue
        best = max(best, T.row_damage(world, actor, ref) * caught)
    # The charge, if this square is one it could charge from. Its damage is the
    # basic attack's, since that is what a charge swings.
    span = charge_reach(world, actor)
    if span:
        from .grid import distance

        basic = known.basic
        for foe in foes(world, actor):
            there = _square_of(world, foe)
            if there is None:
                continue
            if 2 <= distance(origin, there) <= span:
                best = max(best, T.row_damage(world, actor, basic))
                break
    _BEST[key] = best / pool
    return _BEST[key]


def fights_in_melee(world: Any, actor: int) -> bool:
    """Has this creature any melee attack at all?

    **The gate on `takes_flank`, and it was missing.** A flank is +2 to hit *for
    a melee attack*, so it is worth nothing to a creature that never makes one --
    and rewarding it regardless sent the wizard walking into contact to stand in
    a flanking square it could not use. Measured: with the flank bonus ungated,
    the party provoked 92 opportunity attacks over 20 fights at level 5 against
    `LinearPolicy`'s 53, and the excess was "moved away", not ranged attacks.

    Read off what the creature knows rather than off its role, because a role is
    a label and this is a question about the rows in hand.

    **`close_burst` and `close_blast` are not melee and counting them here was a
    bug of mine.** A close burst 3 is centred on the caster and reaches three
    squares, so it wants space, not adjacency. Including them made the wizard --
    whose only attacks are bursts, blasts and ranged rows -- report `True`, which
    sent it to the *melee* tier of `worth_standing` looking for a square next to
    something, and handed it `takes_flank` for a +2 it can never spend. The
    kiting rule Camille asked for could not apply to the one character that most
    needed it.
    """
    from .components import Powers

    known = world.get(actor, Powers)
    if known is None:
        return False
    for ref in known.known:
        p = get(ref)
        if p is None or p.attack is None or p.reach is None:
            continue
        if p.reach.kind == "melee":
            return True
    return False


def _would_flank(world: Any, actor: int, dest: Any, target: int) -> bool:
    """Would standing at `dest` flank `target`, given where the allies are?

    `Grid.flanks` takes two squares and the target's space and checks adjacency
    itself, so this asks about a square the creature is not standing in -- which
    is the whole point, and why nothing has to be moved to find out.
    """
    space = squares(world, target)
    if not space:
        return False
    for mate in flankers(world, actor):
        if mate in (target, actor) or not alive(world, mate):
            continue
        for b in squares(world, mate):
            if world.grid.flanks(dest, b, space):
                return True
    return False


def _is_attack(ref: str) -> bool:
    """Does this row roll an attack a flank could help?

    `Power.attack` being None does not settle it -- `Attack`'s own docstring
    sanctions declaring the attack in the body, and all 118 of one class's ranged
    rows do -- so `provokes` is read as the second signal, being derived from the
    range line rather than from the header's attack block.
    """
    p = get(ref) if ref else None
    return p is not None and (p.attack is not None or p.provokes)


def sets_up_flank(world: Any, actor: int, dest: Any) -> bool:
    """Would standing at `dest` leave an ally a flank it could take next turn?

    `docs/AI_DOCTRINE.md`: "Setting up a flank (moving to a square where an ally can
    shift or move into flanking) is nearly as good as flanking." Nothing scored it,
    so a creature would only ever take a flank that was *already* available --
    measured, 94 of 439 chosen movement actions ended in a flank and none of them
    was chosen for what it offered anybody else.

    The square that flanks with `dest` across a Medium enemy is the one diametrically
    opposite, `2 * foe - dest`, which is what makes this cheap enough to ask of every
    candidate square. `Grid.flanks` then confirms it, so a Large creature -- where
    the reflection is not exact -- is answered correctly rather than approximately.

    An ally counts if it could *reach* that square: within its speed, which is the
    "move into flanking" half of the sentence, and adjacency covers the shift half
    as a special case of it.
    """
    from .components import Movement
    from .grid import distance

    mates = [m for m in flankers(world, actor) if m != actor and alive(world, m)]
    if not mates:
        return False
    for foe in foes(world, actor):
        space = squares(world, foe)
        if not space or min(distance(dest, s) for s in space) > 1:
            continue        # not adjacent from `dest`, so no flank to offer
        for s in space:
            opposite = (2 * s[0] - dest[0], 2 * s[1] - dest[1])
            if not world.grid.passable(opposite):
                continue
            # Free, or already held by the ally that would use it -- a mate
            # standing there is a flank taken, not one set up, and `takes_flank`
            # has already scored that case.
            held = world.grid.occupant(opposite)
            if held is not None and held not in mates:
                continue
            if not world.grid.flanks(dest, opposite, space):
                continue
            for mate in mates:
                here = _square_of(world, mate)
                move = world.get(mate, Movement)
                if here is None or move is None:
                    continue
                if distance(here, opposite) <= move.speed:
                    return True
    return False


def _would_be_flanked(world: Any, actor: int, dest: Any) -> bool:
    """Would two enemies flank `actor` at `dest`?"""
    space = frozenset({dest})
    near = foes(world, actor)
    for i, one in enumerate(near):
        for other in near[i + 1:]:
            for a in squares(world, one):
                for b in squares(world, other):
                    if world.grid.flanks(a, b, space):
                        return True
    return False


def _enemy_zone_squares(world: Any, actor: int) -> set[Any]:
    """Every square covered by a zone an enemy owns.

    The best available reading of "hostile terrain": a `Zone` does not record
    whether it hurts, so ownership is what there is to go on.
    """
    mine = world.get(actor, Side)
    out: set[Any] = set()
    for _, zone in world.zones.all():
        owner = getattr(zone, "owner", -1)
        theirs = world.get(owner, Side)
        if mine is None or theirs is None or theirs.team is mine.team:
            continue
        out |= set(zone.squares)
    return out


def _cover_from_enemies(world: Any, actor: int, where: Any) -> int:
    """The **least** cover a creature at `where` has from any living enemy.

    `Grid.cover(src, dst)` is the cover a target at `dst` has from an attacker at
    `src`, so this is cover the creature would enjoy, measured from each enemy in
    turn. The minimum rather than the maximum, because cover is only worth
    anything against the enemy that is actually shooting: a pillar that hides you
    from three of four is no cover at all against the fourth, and taking the
    maximum would score that square as though it were safe.
    """
    key = (id(world), _round(world), actor, where)
    hit = _COVER.get(key)
    if hit is not None:
        return hit
    worst: int | None = None
    for foe in foes(world, actor):
        for sq in squares(world, foe):
            got = int(world.grid.cover(sq, where))
            worst = got if worst is None else min(worst, got)
    _COVER[key] = worst or 0
    return _COVER[key]


def doctrine_features(
    world: Any, encounter: Encounter, actor: int, action: Action
) -> dict[str, float]:
    """The three doctrine axes, as a flat dict beside `policy.features`."""
    f: dict[str, float] = {}
    mine = world.get(actor, Side)
    here = _square_of(world, actor)

    # -- threat removal, in rounds: hit points and control in one currency ----
    removed = 0.0
    gained_hp = 0.0
    if action.ref:
        laid = T.row_effects(world, actor, action.ref)
        for t in action.targets:
            theirs = world.get(t, Side)
            if t == actor or mine is None or theirs is None:
                continue
            if theirs.team is mine.team or not alive(world, t):
                continue
            health = world.get(t, Health)
            if health is None or health.hp <= 0:
                continue
            # **Rounds of damage denied, which is what makes control comparable
            # with killing.** Camille's rubric: a kill takes all three rounds, an
            # end-of-next-turn immobilise on a creature that cannot then reach
            # anybody takes one, save-ends takes 1.8 because a save is 55%.
            dealt = T.expected_vs(world, actor, action.ref, t)
            rounds = min(1.0, dealt / health.hp) * T.ROUNDS
            rounds += T.denial(world, t, laid,
                               pushed=T.row_push(world, actor, action.ref))
            # Capped at the window, so overkill and a stack of conditions cannot
            # between them remove more than the creature had to give.
            removed += min(rounds, float(T.ROUNDS)) * T.threat(world, t) / T.ROUNDS
            # The other sign: an effect that makes it easier for the party to hit
            # does not reduce its damage, so `denial` cannot see it at all.
            gained_hp += T.enabled(world, t, laid)
    if removed:
        f["threat_removed"] = removed
    if gained_hp:
        other = Team.ENEMY if mine is not None and mine.team is Team.PC else Team.PC
        theirs_pool = T.pool(world, other)
        if theirs_pool:
            f["party_enabled"] = gained_hp / theirs_pool

    # -- position, at the square this action would leave us in ---------------
    dest = action.dest if action.dest is not None else here
    if dest is not None and here is not None:
        near = foes(world, actor)
        if near and fights_in_melee(world, actor):
            # **Only where a flank is worth something to *this* action.** `dest`
            # falls back to the square the creature already occupies, so scoring
            # this on every action gave a flat bonus for *standing* in a flank --
            # including for ending the turn. Measured over 20 fights at level 5,
            # the chosen actions it fired on were `end` 116 times against `move`
            # 30, so the commonest thing it rewarded was passing the turn, which
            # is the one action a flank cannot help.
            #
            # Two cases where it genuinely pays, and nothing else:
            #   - moving into a flank, which is the behaviour being bought;
            #   - attacking a creature this creature is flanking, which is the
            #     +2 actually being spent.
            if dest != here:
                took = any(_would_flank(world, actor, dest, e) for e in near)
                f["takes_flank"] = float(took)
                # Only when the flank is not already there to be taken: a square
                # that flanks *and* sets one up would otherwise be paid twice for
                # the same step, and the doctrine calls setting one up "nearly as
                # good as flanking" -- which is less good, not additional.
                if not took:
                    f["sets_up_flank"] = float(sets_up_flank(world, actor, dest))
            elif action.targets and _is_attack(action.ref):
                # Gated on the row declaring an attack, because the +2 is a bonus
                # *to an attack roll*. Without that a `hide` aimed at a flanked
                # creature collected it, which is the same leak as `end` on a
                # smaller scale.
                f["takes_flank"] = float(
                    any(t in near and flanked_by(world, t, actor)
                        for t in action.targets)
                )
            f["becomes_flanked"] = float(_would_be_flanked(world, actor, dest))
            before = _cover_from_enemies(world, actor, here)
            after = _cover_from_enemies(world, actor, dest)
            if after != before:
                f["cover_change"] = float(after - before)
        if dest != here:
            # Only for a square we are not already standing in. Charging the
            # creature for the zone it is stuck in would penalise every action
            # equally and change no decision, while looking like it did.
            f["into_enemy_zone"] = float(dest in _enemy_zone_squares(world, actor))
            f["into_difficult"] = float(dest in world.difficult(actor))
            # **What the move costs and what it buys, in one currency.** Both are
            # shares of a side's health, so they are directly comparable and the
            # trade is arithmetic rather than a pair of hand-set constants.
            giving = provokers(world, actor, dest)
            if giving:
                f["threat_conceded"] = conceded(world, actor, giving)
            gained = best_from(world, actor, dest) - best_from(world, actor, here)
            if gained:
                f["reach_gained"] = gained

    # **The other way a swing is conceded, and the commoner one.** A ranged or area
    # row used with somebody standing over you hands *each* of them an attack, and
    # `provokes_now` charges a flat -5.0 for it however many there are. Priced here
    # per enemy, the same way the movement case is, so firing next to three costs
    # three times firing next to one.
    if action.ref and not f.get("threat_conceded"):
        p = get(action.ref)
        if p is not None and p.provokes:
            standing = watchers(world, actor)
            if standing:
                f["threat_conceded"] = conceded(world, actor, standing)

    # **Would this land on me?** An area attack centred near the caster catches it,
    # and nothing in `policy.features` can see that.
    if action.ref and actor in action.targets and _is_attack(action.ref):
        health = world.get(actor, Health)
        if health is not None and health.hp > 0:
            mine_dmg = T.row_damage(world, actor, action.ref)
            if mine_dmg > 0:
                f["self_harm"] = min(1.0, mine_dmg / health.hp)

    # **Is this already running?** An effect labelled with the row's own ref is
    # already on the creature, so casting it again buys nothing. `Effect.label` is
    # prefixed with the ref that laid it, which is what makes this readable.
    on_myself = action.ref and (not action.targets or tuple(action.targets) == (actor,))
    if on_myself and running(world, actor, action.ref):
        f["already_on"] = 1.0

    # -- healing --------------------------------------------------------------
    if action.ref and heals(action.ref):
        given = 0.0
        wasted = 0.0
        dying = 0.0
        # The same denominator `threat` uses, so a heal and a kill are measured
        # against the same thing. Against the target's own maximum -- which is
        # what this did first -- healing the wizard and healing the fighter came
        # out equal, and the party pool is what actually has to last the fight.
        ours = T.pool(world, mine.team) if mine is not None else 0
        for t in action.targets:
            health = world.get(t, Health)
            if health is None:
                continue
            theirs = world.get(t, Side)
            if mine is not None and theirs is not None and theirs.team is not mine.team:
                continue
            missing = max(0, health.max_hp - health.hp)
            if missing == 0:
                wasted += 1.0
                continue
            given += missing / ours if ours else 0.0
            if health.hp <= 0 or health.bloodied:
                dying += 1.0
        if given:
            f["healing_given"] = given
        if wasted:
            f["healing_wasted"] = wasted
        if dying:
            f["heals_the_dying"] = dying
    return f


#: Action kinds that put the creature in a new square.
#: The kinds `act` prunes before scoring. **`charge` is deliberately not one.**
#:
#: Pruning exists because `legal` offers ~210 destinations and scoring all of them is
#: where a turn's cost is. A charge is not a destination -- it is a destination *plus
#: an attack* -- and `worth_standing` ranks destinations, so it cannot tell "move here"
#: from "charge here and swing". Charges therefore competed with plain moves for the
#: same 16 slots and lost: **326 of 380 decisions that offered a charge had every one
#: of them pruned away**, 75 of 730 options surviving, and the best discarded charge
#: scored a median 11.54 against a `KEEP` list full of squares worth less.
#:
#: That is also why 915ed93 cut the charge rate while raising the offer count: more
#: charge options, same 16 slots, more of them thrown out. And why the four scoring
#: shapes tried in #265 all failed to move it -- the scorer never saw the action.
#:
#: Exempting them costs almost nothing: a median of 2 charge options per decision and
#: at most 5, against the ~210 the prune is actually for.
_STEPS = ("move", "run", "shift", "teleport")

#: How many destinations survive pruning. 16 against the ~210 `legal` offers, which
#: is where the cost of a turn actually is.
KEEP = 16


def best_reach(world: Any, actor: int) -> int:
    """How far this creature's longest usable attack reaches."""
    from .components import Powers

    known = world.get(actor, Powers)
    if known is None:
        return 1
    far = 1
    for ref in known.known:
        p = get(ref)
        if p is None or p.attack is None or p.reach is None:
            continue
        if known.available(ref):
            far = max(far, p.reach.size)
    return far


def melee_reach(world: Any, eid: int) -> int:
    """How far this creature's longest **melee** attack reaches.

    Not `best_reach`, which takes the longest of anything including a bow. A reach
    weapon is the case this exists for: standing two squares from something that
    reaches one means attacking without being attacked back, and the scorer could
    not see that square because `worth_standing` discarded it.
    """
    from .components import Powers

    known = world.get(eid, Powers)
    if known is None:
        return 0
    far = 0
    for ref in known.known:
        p = get(ref)
        if p is None or p.attack is None or p.reach is None:
            continue
        if p.reach.kind == "melee" and known.available(ref):
            far = max(far, p.reach.size)
    return far


def close_reach(world: Any, eid: int) -> int:
    """How far a close burst or blast of this creature's would catch something.

    Camille's point: **every square from which a close attack could hit an enemy
    should be evaluated.** A close burst 3 is not a melee attack -- it wants space --
    but nor is it a ranged one, and the kiting band computed off the longest *ranged*
    row would throw away every square the burst could actually be used from.
    """
    from .components import Powers

    known = world.get(eid, Powers)
    if known is None:
        return 0
    far = 0
    for ref in known.known:
        p = get(ref)
        if p is None or p.attack is None or p.reach is None:
            continue
        if p.reach.kind in ("close_burst", "close_blast") and known.available(ref):
            far = max(far, p.reach.size)
    return far


def worth_standing(world: Any, actor: int, moves: list[Action]) -> list[Action]:
    """Camille's rule: only score destinations that could matter.

    **This is where a turn's cost is, not in the scoring.** `actions.legal` offers
    every reachable square -- measured, 210 of a creature's 226 options are a `move`
    or a `run` -- and scoring all of them was 15,155 evaluations for one fight. Most
    are squares no creature would ever want.

    So, Camille's rule, and it prunes for *quality* as much as for speed:

    * a creature that fights in melee wants to end up **adjacent to something**, and
      only if no square does that is approaching worth considering;
    * one that does not wants to be **out of reach but in range** -- not adjacent,
      because that hands over an opportunity attack, and not so far that it cannot
      shoot.

    Two things are deliberately kept beyond that rule. A hurt creature keeps its
    retreat, because `decide` has always backed away below a third of
    its hit points and pruning that away would silently remove the behaviour. And
    if the rule matches nothing, the closest approaches are kept, so a creature is
    never left with no way to move at all.

    Returns the destinations worth scoring. Ties break on `str` so a seed replays.
    """
    from .grid import distance

    near = foes(world, actor)
    if not near or len(moves) <= KEEP:
        return moves
    melee = fights_in_melee(world, actor)
    reach = best_reach(world, actor)

    def gap(sq: Any) -> int:
        return min(distance(sq, _square_of(world, f) or sq) for f in near)

    # Camille's two rules, as tiers. The first tier that has anything in it wins, so
    # a creature never considers a worse class of square while a better one exists.
    span = charge_reach(world, actor)
    danger = threatens_from(world, actor)
    mine = melee_reach(world, actor) or 1
    burst = close_reach(world, actor)
    first: list[Action] = []
    second: list[Action] = []
    ranked: list[tuple[int, str, Action]] = []
    for a in moves:
        g = gap(a.dest)
        if melee:
            # **Anywhere its melee attack reaches**, not just adjacent. A reach-2
            # creature standing at two attacks something that reaches one without
            # being attacked back, and this kept `g <= 1` only -- so the square was
            # discarded before anything could score it. Measured: a reach-2 creature
            # ended adjacent on 92 of 109 attacking turns, having never been offered
            # the alternative. Both are kept now and the scoring chooses, which is
            # right because sometimes closing *is* better -- a flank needs adjacency.
            #
            # A square it could charge from is the next best, being one it can attack
            # from next turn.
            if g <= mine:
                first.append(a)
            elif span and 2 <= g <= span:
                second.append(a)
        else:
            # **Just outside what the enemy can reach, including its charge.**
            # Camille's rule for a creature that does not want to be in melee:
            # seven squares from something with speed six is inside its reach, and
            # the old test only knew about adjacency. Falling back to merely
            # out-of-melee-and-in-range is the second tier, for a board where
            # nowhere is safe.
            # A close burst or blast reaches from anywhere inside its own size, and
            # the band computed off the longest *ranged* row would have thrown those
            # squares away. Camille's point, and it is why `burst` is in here.
            if danger < g <= reach or (burst and 1 < g <= burst):
                first.append(a)
            elif 1 < g <= reach:
                second.append(a)
        ranked.append((g, str(a), a))
    keep = first or second
    if not keep:
        # No tier matched, so close the distance instead. For a ranged creature with
        # nothing in range this is the same thing: get in range.
        ranked.sort(key=lambda t: (t[0], t[1]))
        keep = [a for _, _, a in ranked[:KEEP]]
    health = world.get(actor, Health)
    if health is not None and health.hp < health.max_hp * 0.35:
        ranked.sort(key=lambda t: (-t[0], t[1]))
        for _, _, a in ranked[:3]:
            if a not in keep:
                keep.append(a)
    return keep[:KEEP + 3]


@dataclass
class DoctrinePolicy:
    """The policy. One of them, as of this commit.

    **`LinearPolicy` is retired** -- Camille's call. It existed as a frozen baseline so
    that an A/B could attribute a regression, and that A/B turned out to be the wrong
    instrument: both sides of the board run the same policy, so an improvement helps
    the monsters as much as the party and largely cancels in the win rate. Measured
    twice on fresh seeds, the gap never survived Holm while the tactical counts moved
    hard. `scripts/scorecard.py` is the gate now, and it compares against committed
    numbers rather than against a rival.

    So the two classes are one, and **the two weight tables are one table of 52**.
    That is the thing I argued against when the second policy was created -- "forty-five
    interacting hand-set numbers cannot be moved one at a time, so a regression cannot
    be attributed" -- and the answer is that attribution now comes from the scorecard's
    per-side counts and `scripts/doctrine.py`'s per-term firing, which is finer-grained
    than an A/B ever was. Recording the reversal rather than making it quietly.
    """

    weights: dict[str, float] = field(
        default_factory=lambda: {**WEIGHTS, **DOCTRINE})
    memory: Memory | None = None
    #: Keeps a daily in hand until the fight is going badly.
    desperate_at: float = 0.4

    def score(
        self, world: Any, encounter: Encounter, actor: int, action: Action
    ) -> float:
        f = features(world, encounter, actor, action)
        if action.ref and benefits(action.ref):
            # **Help is not friendly fire.** `allies_caught` is -7.0 and exists to
            # stop a burst landing on your own party; a heal or a buff names allies
            # on purpose. Cleared before `weigh` rather than compensated for after,
            # so the number is never wrong in between.
            f["allies_caught"] = 0.0
        # `running` asked directly, **not** read off `f`: it is a doctrine term and `f`
        # is `policy.features`'s dict, so `f.get("already_on")` was always None and the
        # condition never fired. A predicate reading a field its source does not carry,
        # which is the failure the component file opens with -- and it looked exactly
        # like a working fix, because the scorecard printed identically.
        on_already = bool(action.ref) and (
            not action.targets or tuple(action.targets) == (actor,)
        ) and running(world, actor, action.ref)
        if action.ref and (inert(world, actor, action.ref) or on_already):
            # **An inert row is not a power, for scoring purposes.** `is_power` is a
            # flat +6.0, which made any row beat any alternative -- so a row that can
            # accomplish nothing was chosen 231 times in 1,127 decisions. Zeroed
            # rather than penalised: none of the ones measured cost a *standard*
            # action, so they were filling idle minor and free actions, and a free
            # action that does nothing costs nothing. What it must not do is outbid a
            # move that would have repositioned.
            #
            # **A row whose effect is already running counts as inert too**, for the
            # same reason: it accomplishes nothing *now*.
            f["is_power"] = 0.0
        f.update(doctrine_features(world, encounter, actor, action))
        return self.weigh(f, action)

    def act(
        self, world: Any, encounter: Encounter, actor: int, options: list[Action]
    ) -> Action:
        """Prune the destinations, then take the best of what is left.

        `actions.legal` offers every reachable square and nine in ten options are one,
        so `worth_standing` filters before anything is scored. Sorting by `str` as well
        keeps two runs of a seed identical when several actions score the same.
        """
        moves = [a for a in options if a.kind in _STEPS and a.dest is not None]
        if len(moves) > KEEP:
            keep = set(map(id, worth_standing(world, actor, moves)))
            options = [a for a in options
                       if a.kind not in _STEPS or a.dest is None or id(a) in keep]
        usable = [a for a in options if a.available] or options
        return max(usable,
                   key=lambda a: (self.score(world, encounter, actor, a), str(a)))

    def weigh(self, f: dict[str, float], action: Action) -> float:
        """The weighted sum, given features already computed.

        Split out from `score` so a subclass can adjust a feature *before* it is
        weighed without computing the dict twice -- `features` asks
        `Power.hit_chance` once per target, so it is not free. `DoctrinePolicy`
        is the caller: a healing row has to have `allies_caught` cleared before
        the -7.0 lands on it.
        """
        total = sum(self.weights.get(k, 0.0) * v for k, v in f.items())
        if self.memory is not None and action.ref:
            total += self.memory.worth(action.ref, 5.0) * f.get("expected_hits", 0.0) * 0.4
        if f.get("usage_daily") and f.get("my_hp_fraction", 1.0) < self.desperate_at:
            total += 6.0
        if f.get("is_second_wind") and f.get("my_hp_fraction", 1.0) < 0.3:
            total += 12.0
        return total

    def decide(
        self, world: Any, actor: int, kind: str, options: list[Any], prompt: str
    ) -> Any:
        """Choices inside a power.

        Movement choices are aimed: a shift goes toward the nearest enemy if
        the creature is trying to reach one and away if it is hurt. Anything
        else takes the first option, which is sorted, so it is stable rather
        than arbitrary.
        """
        if kind in ("push", "pull", "slide") and options and _is_square(options[0]):
            # Where to shove somebody. Away from its friends, which is the
            # point of a push -- it is worth more than the square of damage
            # it came with. Ties break in sorted order, so a seed replays.
            mates = [
                a
                for a in _allies_of(world, actor)
                if alive(world, a)
            ]
            if not mates:
                return options[0]

            def isolation(sq: Any) -> tuple[int, Any]:
                return (min(distance(sq, _square(world, m)) for m in mates), sq)

            return max(options, key=isolation)

        if kind in ("shift", "move", "teleport") and options and _is_square(options[0]):
            health = world.get(actor, Health)
            retreat = health is not None and health.hp < health.max_hp * 0.35
            foes = [e for e in enemies(world, actor) if alive(world, e)]
            if not foes:
                return options[0]

            def reach(sq: Any) -> int:
                return min(distance(sq, _square(world, e)) for e in foes)

            return max(options, key=reach) if retreat else min(options, key=reach)
        return options[0]

    def react(
        self, world: Any, encounter: Encounter, actor: int, window: Event
    ) -> Action | None:
        """Take an opportunity attack whenever one is on offer.

        Deliberately blunt. Declining is occasionally right and a fitted
        policy can learn when; always taking it is the right default because
        the failure mode of the alternative -- silently never reacting -- is
        invisible in a log.
        """
        if not isinstance(window, OpportunityWindow):
            return None
        if not encounter.can_spend(actor, ActionType.OPPORTUNITY):
            return None
        if is_(world, actor, Condition.DAZED) or is_(world, actor, Condition.STUNNED):
            return None
        options = [
            a
            for a in _opportunity_options(world, encounter, actor, window.provoker)
            if a.available
        ]
        if not options:
            return None
        return max(options, key=lambda a: (self.score(world, encounter, actor, a), str(a)))

    def explain(
        self, world: Any, encounter: Encounter, actor: int, action: Action
    ) -> dict[str, float]:
        """Every doctrine term and what it contributed. For an instrument.

        A weight nothing consults is this project's commonest bug, so the scorer is
        built able to say what it read.
        """
        d = doctrine_features(world, encounter, actor, action)
        return {k: self.weights.get(k, 0.0) * v for k, v in d.items()}


def pool_shares(world: Any) -> dict[int, float]:
    """Every living creature's threat, for an instrument to print."""
    return {eid: T.threat(world, eid) for eid in creatures(world)
            if alive(world, eid)}
