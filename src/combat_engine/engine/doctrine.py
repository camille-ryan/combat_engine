"""A policy that scores the three things `docs/AI_DOCTRINE.md` actually asks for.

`LinearPolicy` has 44 features and 37 weights and every one of them is an action
kind, a hit chance or a count of targets. Nothing in it can say **where a square
is good**, **how dangerous a creature is**, or **whether a heal is worth casting**
-- which is most of what the doctrine is about. This adds those three and changes
nothing else.

A second policy rather than more weights on the first, deliberately. Forty-five
interacting hand-set numbers cannot be moved one at a time, so a regression in
them cannot be attributed; two policies on the same seeds can be compared. The
default stays `LinearPolicy` until this one is measured to be better, which also
means `scripts/fixtures/` does not move while it is being written.

## Where it stands, measured

**80 seeded fights a cell, seeds 41-120** -- held back while the weights were set
on seeds 1-20, because tuning and confirming on one set of seeds is how a scorer
comes to look better than it is. Both sides of the board run the same policy,
`--draw scored` throughout, and this is *after* #244 was fixed, so the party holds
the powers it is supposed to.

| | level 5 linear | level 5 doctrine | level 10 linear | level 10 doctrine |
|---|---|---|---|---|
| wins of 80 | 47 (59%) | **60 (75%)** | 46 (57%) | **67 (84%)** |
| exact p | | 0.043 | | 0.00045 |
| median rounds | 8.5 | **8.0** | 12.0 | 10.5 |
| party hit rate | 61% | 61% | 62% | 61% |
| party provoked / fight | 3.6 | 4.7 | 4.0 | 6.3 |

Both differences survive **Holm** over the two comparisons, which is the bar
`scripts/winrate.py`'s docstring sets. 40 seeds was not enough and was tried first:
the same comparison read p = 0.062 and p = 0.027 there and neither survived
correction.

Three things worth reading off that table rather than the win rate alone.

**The gain is not accuracy.** Party hit rate is 61% either way, to the point. This
is not hitting more often; it is choosing a better target and a better action,
which is what the threat and healing terms were for.

**It provokes considerably more and wins anyway**, and that is Camille's point made
by measurement. Much of this module's tuning went on pushing the opportunity-attack
count back down to `LinearPolicy`'s, on the assumption that conceding more free
swings must be worse. It is not: at level 10 it concedes half again as many and wins
84% against 57%. The count was a proxy and the proxy was wrong. `threat_conceded`
and `reach_gained` exist so that the trade is *priced* rather than avoided.

**Rounds moved toward the target, not away.** #217 sets 7-8 rounds and warns that a
rising win rate with a collapsing round count means the party has outgrown the
encounter rather than played better. Level 5 went 8.5 -> 8.0, which is on target;
level 10 went 12.0 -> 10.5, still long. The win rate did not come from shorter
fights.

**The weights are still the ones fitted before #244 was fixed**, on level-5 figures
that have since moved, so `scripts/doctrine.py` has more to give here.

## What is scored, and what each rests on

**Threat removal**, and hit points are part of it rather than beside it. A
creature's threat is `threat.threat` -- its best-case damage over three rounds, as
a share of the health it is aimed at -- and an action removes the fraction of that
threat matching the fraction of the creature's remaining hit points it takes off.
So a killing blow removes all of it and half its hit points removes half, without
"kill" needing to be a separate idea. This is what should make a striker finish a
bloodied enemy rather than open on a fresh one.

Conditions enter the same term through `threat.CONDITION_THREAT`, which is
**currently all zeros** by instruction, so they contribute nothing yet.

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
from .policy import LinearPolicy, features
from .query import alive, creatures, enemies, flankers, squares
from .turns import Encounter
from .types import Team

#: Weights for the doctrine terms only. `LinearPolicy.weights` is untouched and
#: the two are summed, so a term here is worth what it says beside the 37 there.
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
#: **75 is set by one inequality, not by taste.** `LinearPolicy` charges -9.0 for a
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
SHARE = 75.0

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
    # **What provoking actually costs, on top of the flat penalty rather than
    # instead of it.** Camille's point is that -5.0 cannot distinguish a brute's
    # free swing from a minion's, and this is what does -- the expected damage of
    # the swings actually conceded, as a share of my side's health.
    #
    # It *modulates* `LinearPolicy`'s `provokes_now` and `provokes_avoidably`
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
    # Flanking is +2 to hit for two creatures rather than one, and the guides
    # treat setting one up as a striker's ordinary business.
    "takes_flank": 0.6,
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

#: Answers cached per ref -- reading a body with `inspect.getsource` is far too
#: slow to do once per option per turn.
_HEALS: dict[str, bool] = {}


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


def _square_of(world: Any, eid: int) -> Any:
    pos = world.get(eid, Position)
    return pos.square if pos is not None else None


#: What a creature swings when handed an opportunity attack. A melee basic, for
#: all but the few monsters whose opportunity action is something else -- and for
#: those this under-prices the provocation rather than over-prices it.
_BASIC = "mba"


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
    for foe in enemies(world, actor):
        if not alive(world, foe):
            continue
        reach = _reach_of(world, foe)
        there = _square_of(world, foe)
        if there is None:
            continue
        if distance(here, there) <= reach and distance(dest, there) > reach:
            out.append(foe)
    return out


def conceded(world: Any, actor: int, foes: list[int]) -> float:
    """Expected damage those opportunity attacks deal, as a share of my side's hp.

    **Camille's correction, and the reason this is not a flat number.** A
    provocation is priced at what it actually hands over: "if the expected damage
    is 10 out of 100 total party hp, that's quite significant", and a -5.0 that
    does not move with the hitter cannot say that. Expressed in the same currency
    as `threat_removed` -- a share of a side's health -- so the two can be
    subtracted from one another and the comparison means something.

    A brute's free swing and a minion's are the same -5.0 to `LinearPolicy` and
    are not remotely the same event.
    """
    mine = world.get(actor, Side)
    if mine is None or not foes:
        return 0.0
    ours = T.pool(world, mine.team)
    if not ours:
        return 0.0
    return sum(T.row_damage(world, f, _BASIC) for f in foes) / ours


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
    for foe in enemies(world, actor):
        if not alive(world, foe):
            continue
        there = _square_of(world, foe)
        if there is None:
            continue
        if distance(origin, there) <= size:
            caught += 1
    # A melee or ranged row hits one creature however many are in range; an area
    # one hits everything it covers, and that is the whole difference here.
    return caught if kind in ("close_burst", "close_blast", "area_burst", "wall") \
        else min(1, caught)


def best_from(world: Any, actor: int, origin: Any) -> float:
    """The best expected damage this creature could do from `origin`.

    A share of the enemy side's health, so it is the same currency as
    `threat_removed` and `conceded`. Used as a *difference* between two squares --
    Camille's rule: "compare expected consequences from the move vs the
    differential between the best attack after moving, and the best action without
    taking the OA". A close blast that would catch the whole enemy party is worth
    a free swing against you, and nothing in a flat provocation penalty can say so.
    """
    from .components import Powers

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
    return best / pool


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
    """
    from .components import Powers

    known = world.get(actor, Powers)
    if known is None:
        return False
    for ref in known.known:
        p = get(ref)
        if p is None or p.attack is None or p.reach is None:
            continue
        if p.reach.kind in ("melee", "close_burst", "close_blast"):
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


def _would_be_flanked(world: Any, actor: int, dest: Any) -> bool:
    """Would two enemies flank `actor` at `dest`?"""
    space = frozenset({dest})
    foes = [e for e in enemies(world, actor) if alive(world, e)]
    for i, one in enumerate(foes):
        for other in foes[i + 1:]:
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
    worst: int | None = None
    for foe in enemies(world, actor):
        if not alive(world, foe):
            continue
        for sq in squares(world, foe):
            got = int(world.grid.cover(sq, where))
            worst = got if worst is None else min(worst, got)
    return worst or 0


def doctrine_features(
    world: Any, encounter: Encounter, actor: int, action: Action
) -> dict[str, float]:
    """The three doctrine axes, as a flat dict beside `policy.features`."""
    f: dict[str, float] = {}
    mine = world.get(actor, Side)
    here = _square_of(world, actor)

    # -- threat removal, hit points included ---------------------------------
    removed = 0.0
    if action.ref:
        for t in action.targets:
            theirs = world.get(t, Side)
            if t == actor or mine is None or theirs is None:
                continue
            if theirs.team is mine.team or not alive(world, t):
                continue
            health = world.get(t, Health)
            if health is None or health.hp <= 0:
                continue
            dealt = T.row_damage(world, actor, action.ref)
            share = min(1.0, dealt / health.hp)
            removed += share * T.threat(world, t)
    if removed:
        f["threat_removed"] = removed

    # -- position, at the square this action would leave us in ---------------
    dest = action.dest if action.dest is not None else here
    if dest is not None and here is not None:
        foes = [e for e in enemies(world, actor) if alive(world, e)]
        if foes:
            if fights_in_melee(world, actor):
                f["takes_flank"] = float(
                    any(_would_flank(world, actor, dest, e) for e in foes)
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


@dataclass
class DoctrinePolicy(LinearPolicy):
    """`LinearPolicy` plus threat, position and healing.

    Everything not named in the module docstring is inherited unchanged --
    `act`, `decide` and `react` are `LinearPolicy`'s, so the two policies differ
    in how they *score* an action and in nothing else. That is what makes an A/B
    between them readable.
    """

    doctrine: dict[str, float] = field(default_factory=lambda: dict(DOCTRINE))

    def score(
        self, world: Any, encounter: Encounter, actor: int, action: Action
    ) -> float:
        f = features(world, encounter, actor, action)
        if action.ref and heals(action.ref):
            # **A heal is not friendly fire.** `allies_caught` is -7.0 and exists
            # to stop a burst landing on your own party; a heal targets allies on
            # purpose. Cleared before `weigh` rather than compensated for after,
            # so the number is never wrong in between.
            f["allies_caught"] = 0.0
        total = self.weigh(f, action)
        d = doctrine_features(world, encounter, actor, action)
        return total + sum(self.doctrine.get(k, 0.0) * v for k, v in d.items())

    def explain(
        self, world: Any, encounter: Encounter, actor: int, action: Action
    ) -> dict[str, float]:
        """Every doctrine term and what it contributed. For an instrument.

        A weight nothing consults is this project's commonest bug, so the scorer
        is built able to say what it read.
        """
        d = doctrine_features(world, encounter, actor, action)
        return {k: self.doctrine.get(k, 0.0) * v for k, v in d.items()}


def pool_shares(world: Any) -> dict[int, float]:
    """Every living creature's threat, for an instrument to print."""
    return {eid: T.threat(world, eid) for eid in creatures(world)
            if alive(world, eid)}
