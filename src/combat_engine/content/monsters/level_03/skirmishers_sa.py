"""Monster abilities, level 3, skirmishers: the second sweep.

Thirty-seven stat blocks whose rows were still undeclared. `skirmishers.py`
holds the first sweep of this level and this file holds the rest; the split is
by *when* the work was done, not by what the creatures are, so the conventions
are the ones that file settled and they are kept here unchanged:

* numbers load from `game.db` -- the attack line is written exactly as printed
  (`Attack(vs=AC, printed=8)`) and the damage line goes in the header as data
  so an MM1 block can be rescaled to MM3 maths later;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it for the rest of the fight. Several rows the database
  files as standard actions are plainly traits and are written as such;
* a printed range of "5/10" takes the **normal** range, so the creature shoots
  inside the band where it has no penalty;
* combat advantage is read off the roll rather than asked of the board
  afterwards, because `resolve.attack` clears `HIDDEN_FROM` the moment the
  attack is over.

`_advantage_rider` and the two lurker helpers were written for level 2 and are
imported rather than copied -- nine creatures here are the same shape.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.monsters.forms import (
    _shapechange,
    _shapes,
)
from combat_engine.content.monsters.level_01 import aquatic_edge
from combat_engine.content.monsters.level_02.skirmishers import (
    _advantage_rider,
    _conceal,
    _hides_with_cover,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Effect,
    Health,
    Keyword,
    Melee,
    MeleeOrRanged,
    Powers,
    Ranged,
    Relation,
    Size,
    Square,
    Target,
    UpTo,
    Usage,
    When,
    World,
    get,
    power,
    spread,
)
from combat_engine.engine.events import (
    AdjacencyGained,
    AttackRolled,
    Bloodied,
    ConditionApplied,
    ConditionEnded,
    DamageApplied,
    Dropped,
    Hit,
    Miss,
    RelationSet,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    adjacent,
    distance_between,
    enemies,
    flankers,
    has_combat_advantage,
    is_,
    squares,
    team,
)
from combat_engine.engine.triggers import Trigger, about_me, both, by_me, by_melee, targets_me

#: The five conditions that stop a creature taking a free action.
_SILENCING = (
    Condition.DOMINATED,
    Condition.IMMOBILIZED,
    Condition.RESTRAINED,
    Condition.SLOWED,
    Condition.STUNNED,
)


# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _while_bloodied(world: World, eid: int) -> bool:
    """The printed "usable only while bloodied" Requirement, as a gate."""
    hp = world.get(eid, Health)
    return hp is not None and 0 < hp.hp <= hp.max_hp // 2


def _carries(world: World, eid: int, ref: str) -> bool:
    """Has that creature got this row? What "creatures with <trait>" asks."""
    known = world.get(eid, Powers)
    return known is not None and ref in known.known


def _reachable(world: World, eid: int, reach: int, test: Callable[[int], bool]) -> bool:
    """Is there anybody in reach this row may legally be aimed at?

    `Target` has no field for "one **prone** creature" or "one immobilized,
    restrained, or helpless creature", and a body that checks and returns is
    a standard action the AI spends on nothing. Asked as a `requires=` the
    row is simply not offered, which is what the printed target line means:
    `dsl.usable` gets `(world, eid)` and the caster is the only thing it
    knows, so the question has to be "is such a creature within reach of me".
    """
    return any(
        distance_between(world, eid, foe) <= reach and test(foe)
        for foe in enemies(world, eid)
    )


def _holds_somebody_down(world: World, eid: int) -> bool:
    return _reachable(
        world, eid, 2,
        lambda foe: any(
            is_(world, foe, held)
            for held in (Condition.IMMOBILIZED, Condition.RESTRAINED, Condition.HELPLESS)
        ),
    )


def _has_somebody_prone(world: World, eid: int) -> bool:
    return _reachable(world, eid, 1, lambda foe: is_(world, foe, Condition.PRONE))


def _has_the_drop(world: World, eid: int) -> bool:
    return _reachable(world, eid, 1, lambda foe: has_combat_advantage(world, eid, foe))


def _nearest(c: Cast) -> int | None:
    """The closest living enemy, which several rows name outright."""
    return min(c.enemies(), key=lambda foe: c.distance(foe), default=None)


def _adjacent_foes(c: Cast, reach: int = 1) -> list[int]:
    return [foe for foe in c.enemies() if c.distance(foe) <= reach]


def _step_beside(c: Cast, mate: int, anchor: int) -> Square | None:
    """One square `mate` can step into that is still next to `anchor`.

    "The allies must end adjacent to it" names a destination rather than a
    distance, which is what `to=` on the movement ops is for -- but no op
    will pick the square and an occupied one is simply refused.
    """
    taken = squares(c.world, mate)
    beside = spread(squares(c.world, anchor), 1)
    for sq in sorted(spread(taken, 1) - taken):
        if sq in beside and c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None:
            return sq
    return None


def _shift_up_to(c: Cast, squares_: int, *, toward: int | None = None) -> bool:
    """Shift, and when the card names where to end up, aim the step there.

    "Shifts up to 3 squares **to a square adjacent to** the triggering
    enemy" is a destination, and `c.shift` with a bare distance asks the
    controller for one -- which on a quiet board walks away from the creature
    the rest of the row is about, so the attack that follows has nothing in
    reach. Falls back to an ordinary shift when no legal square is free.
    """
    if toward is not None:
        taken = squares(c.world, toward)
        here = c.here
        for sq in sorted(spread(taken, 1) - taken):
            if max(abs(sq[0] - here[0]), abs(sq[1] - here[1])) > squares_:
                continue
            if not c.world.grid.passable(sq) or c.world.grid.occupant(sq) is not None:
                continue
            if c.shift(squares_, to=sq):
                return True
    return c.shift(squares_)


def _recharge_when_bloodied(c: Cast) -> None:
    """Put this row back up when the printed line says so, not only on a die.

    Eight blocks here print "Recharge when first bloodied" where the database
    files a plain 6+. The number stays in the header, because that is what
    `actions.recharge` rolls and what the card shows; this is the printed
    sentence on top of it, and the two only ever agree to make the row
    available sooner. Armed from the body, which is all that is needed: a
    recharge row cannot be spent before it has been used once.
    """
    me, ref = c.me, c.ref

    def bled(ev: Bloodied) -> None:
        if ev.actor == me:
            c.restore_use(ref, on=me)

    c.watch(Bloodied, bled, until=When.ENCOUNTER, on=me, once=True, label=f"{ref} recharge")


def _armed(c: Cast, label: str) -> bool:
    """Is a watch with this label already standing on the caster?

    An at-will row that arms a lasting rider is used again and again, and a
    second copy of the rider pays out twice for one printed sentence.
    """
    return any(effect.label == label for effect in c.world.effects.of(c.me))


def _per_round_rider(c: Cast, dice: str, matches: Callable[[Any], bool]) -> None:
    """Extra damage on the **first** qualifying hit of each round."""
    me, ref = c.me, c.ref
    spent: dict[str, int] = {}

    def rider(ev: Hit) -> None:
        if ev.attacker != me or spent.get("round") == c.world.round:
            return
        if not matches(ev):
            return
        spent["round"] = c.world.round
        c.damage(dice, on=ev.target, detail=ref)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


def _mobile_attack(c: Cast, total: int, *, shifting: bool = False) -> None:
    """Move, swing once on the way, move on -- and no opening for the victim.

    The distance is spent in two halves rather than all at once, because "at
    any point during the movement" is what puts a creature in reach that one
    step to one destination would not.
    """
    half = max(1, total // 2)
    c.shift(half) if shifting else c.move(half)
    foe = next(iter(_adjacent_foes(c)), None)
    if foe is not None:
        c.no_provoke(from_=foe, on=c.me, until=When.EOT)
        c.basic(on=foe)
    rest = total - half
    if rest > 0:
        c.shift(rest) if shifting else c.move(rest)


def _two_basics(c: Cast, *, separate: bool, between: int = 0, penalty: int = 0) -> None:
    """Two granted swings, with a step between them if the line says so."""
    hobble = c.penalty("attack", penalty, on=c.me, until=When.EOT) if penalty else None
    try:
        struck: set[int] = set()
        for turn in range(2):
            if turn and between:
                c.shift(between)
            foe = next(
                (f for f in _adjacent_foes(c) if not (separate and f in struck)), None
            )
            if foe is None:
                continue
            struck.add(foe)
            c.basic(on=foe)
    finally:
        if hobble is not None:
            c.end_effect(hobble, why="the attacks are over")


def _regenerates(c: Cast, amount: int, *, airborne: bool = False) -> None:
    """Heal at the top of each of its own turns while it still stands.

    Written out rather than `c.regeneration` for the creatures whose printed
    line adds a condition of its own -- "if it starts its turn on the ground
    its regeneration does not function" is read here and nowhere else.
    """
    me = c.me

    def tick(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        hp = c.world.get(me, Health)
        if hp is None or hp.hp < 1:
            return
        if airborne and c.height(on=me) <= 0:
            return
        c.heal(amount, on=me)

    c.watch(TurnStart, tick, until=When.ENCOUNTER, on=me, label=f"{c.ref} regeneration")


def _ongoing_of(c: Cast, who: int, dtype: DamageType) -> int:
    """How big a burn of that type the creature is already carrying."""
    return max(
        (
            effect.ongoing[0]
            for effect in c.world.effects.of(who)
            if effect.ongoing and effect.ongoing[1] is dtype
        ),
        default=0,
    )


def _shoved_by_hand(ctx: dict[str, Any]) -> bool:
    """Was this shove a melee or a ranged attack's? `c.resist_forced`'s gate."""
    p = get(ctx.get("power") or "")
    return p is not None and p.reach.kind in ("melee", "ranged")


def _by_close_or_area(world: World, me: int, ev: Any) -> bool:
    """"...hits it with a close or area attack." Not `by_melee`: that one
    counts a close burst as melee, which is right for its own question and
    wrong for this one, where a sword stroke must not qualify."""
    p = get(getattr(ev, "power", "") or getattr(ev, "detail", "") or "")
    return p is not None and p.reach.kind in ("close_burst", "close_blast", "area_burst")


def _hit_me_from_a_distance(world: World, me: int, ev: Any) -> bool:
    attacker = getattr(ev, "attacker", None)
    return (
        getattr(ev, "target", None) == me
        and attacker is not None
        and distance_between(world, me, attacker) <= 3
        and _by_close_or_area(world, me, ev)
    )


def _missed_me_from_beside(world: World, me: int, ev: Any) -> bool:
    attacker = getattr(ev, "attacker", None)
    return (
        getattr(ev, "target", None) == me
        and attacker is not None
        and adjacent(world, me, attacker)
    )


def _hit_a_bloodied_enemy(world: World, me: int, ev: Any) -> bool:
    victim = getattr(ev, "target", None)
    if getattr(ev, "attacker", None) != me or victim is None:
        return False
    hp = world.get(victim, Health)
    return hp is not None and 0 < hp.hp <= hp.max_hp // 2


def _enemy_stepped_beside(world: World, me: int, ev: Any) -> bool:
    """"An enemy enters a square adjacent to it."

    `AdjacencyGained` is emitted mirrored, so `actor` is read as the creature
    answering and `mover` is the one that actually moved -- without the second
    test this also fired when the creature closed the gap itself.
    """
    if getattr(ev, "actor", None) != me:
        return False
    other = getattr(ev, "other", None)
    return (
        other is not None
        and getattr(ev, "mover", 0) == other
        and team(world, other) is not team(world, me)
    )


def _foe_near_at_my_turn(world: World, me: int, ev: Any) -> bool:
    if getattr(ev, "actor", None) != me or getattr(ev, "ghost", False):
        return False
    return any(distance_between(world, me, foe) <= 3 for foe in enemies(world, me))


def _foe_ended_near_me(world: World, me: int, ev: Any) -> bool:
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or getattr(ev, "ghost", False):
        return False
    return (
        team(world, actor) is not team(world, me)
        and distance_between(world, me, actor) <= 3
    )


# --------------------------------------------------------------------------
# m1019
# --------------------------------------------------------------------------


@power(
    "m1019a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 4),
)
def m1019a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(3)


# --------------------------------------------------------------------------
# m1050
# --------------------------------------------------------------------------


@power(
    "m1050a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d4", 7),
)
def m1050a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1050a1",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1050a1(c: Cast) -> None:
    """The pair's rider, and the bigger die is the pair working together.

    "Flanking with each other" is asked of `query.flankers` rather than of
    `flanked_by`, which answers only "is this creature flanked at all" and
    cannot say by whom -- so written with that the bonus doubled whenever any
    two enemies had the target between them.
    """
    me, ref = c.me, c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker != me or not c.had_advantage(ev):
            return
        pair = [
            mate
            for mate in flankers(c.world, ev.target)
            if mate != me and _carries(c.world, mate, ref)
        ]
        together = me in flankers(c.world, ev.target) and bool(pair)
        c.damage("2d6" if together else "1d6", on=ev.target, detail=ref)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m1050a2",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1050a2(c: Cast) -> None:
    """Losing its partner makes it reckless for the rest of the fight.

    Read off `Dropped` and compared against `team` directly rather than
    against `c.allies()`: the moment the trigger fires the fallen creature is
    no longer alive, and `query.allies` filters the dead out, so the test
    would have been false every single time.
    """
    me, ref = c.me, c.ref

    def fell(ev: Dropped) -> None:
        if ev.actor == me or team(c.world, ev.actor) is not team(c.world, me):
            return
        if not _carries(c.world, ev.actor, ref) or not c.can_see(ev.actor):
            return
        for defence in (AC, FORT, REF, WILL):
            c.penalty(defence, 2, on=me, until=When.ENCOUNTER)
        c.bonus("attack", 2, on=me, until=When.ENCOUNTER)
        c.bonus("damage", 2, on=me, until=When.ENCOUNTER)

    c.watch(Dropped, fell, until=When.ENCOUNTER, on=me, once=True, label=ref)


# --------------------------------------------------------------------------
# m1053
# --------------------------------------------------------------------------


@power(
    "m1053a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 4),
)
def m1053a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1053a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d4", 2),
    dropped=("c.contract(ref)",),
)
def m1053a1(c: Cast) -> None:
    """The burn is exact; catching the disease is the dropped half.

    A disease is a track rolled between encounters and the engine has no
    verb for handing one over, so the clause is named rather than faked."""
    if c.strike():
        c.hit()
        c.ongoing(2)


@power(
    "m1053a2",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    narrative=("skill:bluff",),
)
def m1053a2(c: Cast) -> None:
    """Two halves of the printed line have combat meaning and one does not.

    Going Small and losing the bite are both real and are written. Looking
    like a particular individual is a Bluff circumstance -- nothing on a
    board rolls against a disguise -- so that clause is not missing a verb,
    it has nowhere to go.
    """
    c.resize(Size.SMALL, on=c.me)
    c.forbid("m1053a1", on=c.me, until=When.ENCOUNTER)


@power(
    "m1053a3",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1053a3(c: Cast) -> None:
    _advantage_rider(c, "1d6", ("melee",))


# --------------------------------------------------------------------------
# m1054
# --------------------------------------------------------------------------


@power(
    "m1054a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 4),
)
def m1054a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1054a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d4", 2),
    dropped=("c.contract(ref)",),
)
def m1054a1(c: Cast) -> None:
    """As m1053a1: the burn lands, the disease has no verb to carry it."""
    if c.strike():
        c.hit()
        c.ongoing(2)


@power(
    "m1054a2",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    narrative=("skill:bluff",),
)
def m1054a2(c: Cast) -> None:
    """Small and biteless are written; looking like somebody is a Bluff
    circumstance with nothing on a board to roll against."""
    c.resize(Size.SMALL, on=c.me)
    c.forbid("m1054a1", on=c.me, until=When.ENCOUNTER)


@power(
    "m1054a3",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1054a3(c: Cast) -> None:
    _advantage_rider(c, "1d6", ("melee",))


# --------------------------------------------------------------------------
# m1055
# --------------------------------------------------------------------------


@power(
    "m1055a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 4),
)
def m1055a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1055a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d4", 2),
    dropped=("c.contract(ref)",),
)
def m1055a1(c: Cast) -> None:
    """As m1053a1: the burn lands, the disease has no verb to carry it."""
    if c.strike():
        c.hit()
        c.ongoing(2)


@power(
    "m1055a2",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    narrative=("skill:bluff",),
)
def m1055a2(c: Cast) -> None:
    """Small and biteless are written; looking like somebody is a Bluff
    circumstance with nothing on a board to roll against."""
    c.resize(Size.SMALL, on=c.me)
    c.forbid("m1055a1", on=c.me, until=When.ENCOUNTER)


@power(
    "m1055a3",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1055a3(c: Cast) -> None:
    _advantage_rider(c, "1d6", ("melee",))


# --------------------------------------------------------------------------
# m1124
# --------------------------------------------------------------------------


@power(
    "m1124a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 2),
)
def m1124a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1124a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 4),
)
def m1124a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1124a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 0),
)
def m1124a2(c: Cast) -> None:
    """Two arrows at one creature, each rolled and each paying out on its own.

    Written as two rolls rather than as `UpTo(2)` because the printed line
    says "two attacks" and names no second target, so nailing the same
    creature twice is the reading it allows and a two-target header is not.
    """
    for _ in range(2):
        if c.strike():
            c.hit()


@power(
    "m1124a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("3d6", 3, kind=LIMITED),
)
def m1124a3(c: Cast) -> None:
    """The card states this twice and the two statements disagree.

    One sentence is a single 3d6+3 shot and the other is two shots of 1d10+4
    with a step between them -- two printings of the same power, extracted on
    top of each other. The header takes the first, which is the one
    `cards.py` reads, and the step is kept because both halves print it.
    """
    if c.strike():
        c.hit()
    c.shift(3)


@power(
    "m1124a4",
    level=3,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it has made an attack roll",
    on=Trigger(AttackRolled, by_me, "it has made an attack roll"),
)
def m1124a4(c: Cast) -> None:
    """`keep="new"` is the printed "must use the second roll, even if lower"."""
    c.reroll_attack(keep="new")


@power(
    "m1124a5",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    once_per_round=True,
)
def m1124a5(c: Cast) -> None:
    """Name the nearest enemy, then one extra die a round against it.

    The rider is armed once and reads the relation each time, so re-using
    the minor action moves the quarry without laying a second rider -- two
    copies would pay the printed sentence out twice.
    """
    foe = _nearest(c)
    if foe is None:
        return
    for old in c.world.relations.targets(Relation.QUARRY_OF, c.me):
        if old != foe:
            c.world.relations.clear(Relation.QUARRY_OF, c.me, old, c.ref)
    c.quarry(on=foe)
    if not _armed(c, c.ref):
        _per_round_rider(c, "1d6", lambda ev: c.is_quarry(on=ev.target))


@power(
    "m1124a6",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is damaged by a melee attack",
    on=Trigger(DamageApplied, both(targets_me, by_melee), "a melee attack damages it"),
)
def m1124a6(c: Cast) -> None:
    c.shift(2)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=c.me, until=When.EONT, kind="power")


# --------------------------------------------------------------------------
# m1126
# --------------------------------------------------------------------------


@power(
    "m1126a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d4", 1),
)
def m1126a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1126a1",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d4", 3, kind=LIMITED),
)
def m1126a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1126a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 5),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d4", 6),
)
def m1126a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1126a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("1d4", 3, kind=LIMITED),
)
def m1126a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)


@power(
    "m1126a4",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1126a4(c: Cast) -> None:
    """Once a round, not once an attack -- the die is spent on the first hit
    of the round that had the drop on its target."""
    _per_round_rider(c, "2d6", c.had_advantage)


@power(
    "m1126a5",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    trigger="it takes damage",
    on=Trigger(DamageApplied, targets_me, "it takes damage"),
)
def m1126a5(c: Cast) -> None:
    """Gone until he swings, and swinging is watched rather than assumed.

    `resolve.attack` has no hand in invisibility, so "until he attacks" is
    its own watch on the creature's next `Hit` or `Miss` -- either outcome
    gives him away.
    """
    me = c.me
    gone = c.invisible(on=me, until=When.EONT)

    def shown(ev: Any) -> None:
        if getattr(ev, "attacker", None) == me:
            c.end_effect(gone, why="it attacked")

    c.watch(Hit, shown, until=When.EONT, on=me, once=True, label=f"{c.ref} seen")
    c.watch(Miss, shown, until=When.EONT, on=me, once=True, label=f"{c.ref} seen")


@power(
    "m1126a6",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1126a6(c: Cast) -> None:
    _hides_with_cover(c)


@power(
    "m1126a7",
    level=3,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1126a7(c: Cast) -> None:
    """Walk and vanish. There is no Stealth roll on a board and no movement
    penalty to be exempt from, so what is left that can be said is the
    consequence: wherever he could try, he has."""
    c.move(c.speed_of(c.me))
    _conceal(c)


# --------------------------------------------------------------------------
# m1136
# --------------------------------------------------------------------------


@power(
    "m1136a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 3),
)
def m1136a0(c: Cast) -> None:
    """High crit: the extra die is **rolled**, not maxed. `c.damage` maxes
    its dice on a critical, so putting the rider inside the crit branch as a
    second `c.damage` would hand over 8 instead of a roll."""
    if c.strike():
        c.hit()
        if c.crit:
            c.flat(c.roll("1d8"))


@power(
    "m1136a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d10", 2),
)
def m1136a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1136a2",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    requires=_while_bloodied,
    requires_text="usable only while bloodied",
)
def m1136a2(c: Cast) -> None:
    """A granted swing, so `c.basic` rather than a hand-written roll: this
    creature points `Powers.basic` at one of its own rows and a longhand copy
    would quietly ignore that."""
    c.basic(on=c.target)
    c.heal(11, on=c.me)


@power(
    "m1136a3",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    charges=True,
    trigger="it drops an enemy",
    on=Trigger(Dropped, by_me, "it drops an enemy"),
    dropped=("Dropped.power",),
)
def m1136a3(c: Cast) -> None:
    """The charge is written; "with a ranged attack" is the dropped half.

    `Dropped` carries who struck the blow but not what struck it, so the
    narrowing cannot be asked. `charges=True` is what makes the engine
    measure reach the way a charge needs -- without it the row is refused
    whenever the target is further off than a sword, which is every
    situation a charge is for.
    """
    foe = _nearest(c)
    if foe is not None:
        c.charge_at(foe)


# --------------------------------------------------------------------------
# m115787
# --------------------------------------------------------------------------


@power(
    "m115787a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115787a0(c: Cast) -> None:
    c.threatens(2)


@power(
    "m115787a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 6),
)
def m115787a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115787a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 4),
)
def m115787a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115787a3",
    level=3,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115787a3(c: Cast) -> None:
    """It steps first, then the allies step to where it now is.

    "The allies must end adjacent to it" is a destination rather than a
    distance, so each ally's square is picked against the creature's new
    position and handed to `c.shift(to=)`; an ally with nowhere legal to go
    simply stays put, which is the printed permission.
    """
    beside = [mate for mate in c.allies() if c.adjacent(mate)]
    c.shift(1)
    for mate in beside:
        where = _step_beside(c, mate, c.me)
        if where is not None:
            c.shift(1, who=mate, to=where)


@power(
    "m115787a4",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy enters a square adjacent to it",
    on=Trigger(AdjacencyGained, _enemy_stepped_beside, "an enemy steps up to it"),
)
def m115787a4(c: Cast) -> None:
    c.shift(3)


# --------------------------------------------------------------------------
# m115824
# --------------------------------------------------------------------------


@power(
    "m115824a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("compendium.silvered",),
)
def m115824a0(c: Cast) -> None:
    """Regeneration lands; the silver that switches it off does not.

    Nothing marks a weapon as silvered, so the suspension clause has no
    property to read. The healing half is the whole of what plays."""
    c.regeneration(5)


@power(
    "m115824a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 6),
    requires=_shapes("humanoid", "hybrid"),
    requires_text="it must be in humanoid or hybrid form",
)
def m115824a1(c: Cast) -> None:
    """"Or 2d6 + 6 with combat advantage" is two expressions, so the bigger
    one is rolled in the body rather than declared -- the header holds the
    ordinary line, which is what a card prints and a policy reads.

    The printed Requirement names a shape the creature is in and nothing
    records which one, which is the dropped half.
    """
    result = c.strike()
    if not result:
        return
    if result.advantage:
        c.damage("2d6", 6)
    else:
        c.hit()


@power(
    "m115824a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d4", 4),
    dropped=("c.contract(ref)",),
    requires=_shapes("beast", "hybrid"),
    requires_text="it must be in beast or hybrid form",
)
def m115824a2(c: Cast) -> None:
    """The burn is gated on the target granting the drop, which is read off
    the roll: asking the board afterwards is too late, because a one-shot
    grant has already been spent by then."""
    result = c.strike()
    if result:
        c.hit()
        if result.advantage:
            c.ongoing(5)


@power(
    "m115824a3",
    level=3,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_shapes("beast"),
    requires_text="it must be in beast form",
)
def m115824a3(c: Cast) -> None:
    """The shift plays; the form the Requirement names is not recorded."""
    c.shift(c.speed_of(c.me))


@power(
    "m115824a4",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m115824a4(c: Cast) -> None:
    """It alters its physical form: humanoid, hybrid, beast.

    **Written now that a shape can be read.** This was appearance only,
    and correctly so while nothing could ask which form the creature was
    in -- its own note said the gated attacks carried the gap. Those
    Requirements are gates now, so the shape is what decides which of
    this creature's attacks it may use, and the row is no longer out of
    combat.

    `humanoid` leads the list because that is what the creature is before it
    changes anything, and one form replaces another -- which is what
    "until it uses this power again" means.

    The card ties the size to the shape -- a Tiny beast, a Medium
    humanoid -- so the resize follows whichever was taken rather than
    being a choice of its own.
    """
    taken = _shapechange(c, "humanoid", "hybrid", "beast")
    if taken:
        c.resize(Size.TINY if taken == "beast" else Size.MEDIUM,
                 on=c.me)
# --------------------------------------------------------------------------
# m1684
# --------------------------------------------------------------------------


@power(
    "m1684a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 5),
)
def m1684a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m1684a1",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 3, kind=LIMITED),
)
def m1684a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(3)
        c.shift(1)


@power(
    "m1684a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 1),
)
def m1684a2(c: Cast) -> None:
    """Both blades at one creature, and the shove is the pair landing.

    `hand=` is passed because the off-hand swing is a real distinction the
    engine carries -- a two-weapon rider reads it off the outcome -- and
    because both rolls otherwise arrive indistinguishable in the log.
    """
    landed = 0
    for hand in ("main", "off"):
        if c.strike(hand=hand):
            landed += 1
            c.hit()
    if landed == 2:
        c.push(1)


# --------------------------------------------------------------------------
# m2001
# --------------------------------------------------------------------------


@power(
    "m2001a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d4", 3, dtype=DamageType.NECROTIC),
)
def m2001a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2001a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d4", 3, dtype=DamageType.NECROTIC),
)
def m2001a1(c: Cast) -> None:
    """One creature at a time, and the blindness is tied to the grab.

    "Blinded until the grab ends" is not a duration the clock can measure,
    so the hold runs to the end of the encounter and is ended by the
    relation being cleared -- which is the printed sentence read literally.
    """
    if c.grabbing():
        return
    if not c.strike():
        return
    c.hit()
    foe = c.target
    c.grab()
    dark = c.blinded(until=When.ENCOUNTER)

    def freed(ev: Any) -> None:
        if ev.kind_ is Relation.GRABBED_BY and ev.target == foe:
            c.end_effect(dark, why="the grab ended")

    from combat_engine.engine.events import RelationCleared

    c.watch(RelationCleared, freed, until=When.ENCOUNTER, on=c.me, once=True)


@power(
    "m2001a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m2001a2(c: Cast) -> None:
    _mobile_attack(c, 5)


@power(
    "m2001a3",
    level=3,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it reduces an enemy to 0 hit points or fewer",
    on=Trigger(Dropped, by_me, "it drops an enemy"),
)
def m2001a3(c: Cast) -> None:
    """It splits, and the copy starts on the same hit points as the original.

    `c.summon` rather than a spawn: the second half of that verb is joining
    the initiative order, and without it the new creature stands there and
    never acts.
    """
    twin = c.summon("m2001")
    if not twin:
        return
    mine = c.world.get(c.me, Health)
    theirs = c.world.get(twin, Health)
    if mine is not None and theirs is not None:
        theirs.hp = mine.hp


# --------------------------------------------------------------------------
# m2022
# --------------------------------------------------------------------------


@power(
    "m2022a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 5),
)
def m2022a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2022a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("compendium.attack_defence",),
)
def m2022a1(c: Cast) -> None:
    """A mobile attack, written as the movement it is printed as.

    The card also carries "+6 vs ; 1d10+3" -- an attack line whose defence
    the extraction lost -- so that half cannot be declared at all and is
    named rather than guessed. What plays is the sentence that survived
    intact: half a move, one melee basic attack on the way, and no opening
    for the creature it swung at.
    """
    _mobile_attack(c, max(1, c.speed_of(c.me) // 2))


@power(
    "m2022a2",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2022a2(c: Cast) -> None:
    _advantage_rider(c, "2d6", ("melee",))


# --------------------------------------------------------------------------
# m3194
# --------------------------------------------------------------------------


@power(
    "m3194a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d4", 3),
)
def m3194a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.SOTNT)


@power(
    "m3194a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("3d4", 3),
    requires=_while_bloodied,
    requires_text="usable only while bloodied",
)
def m3194a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(2)


@power(
    "m3194a2",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3194a2(c: Cast) -> None:
    _advantage_rider(c, "1d6", ("melee",))


# --------------------------------------------------------------------------
# m3212
# --------------------------------------------------------------------------


@power(
    "m3212a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 3),
)
def m3212a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3212a1",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=6),
)
def m3212a1(c: Cast) -> None:
    """No damage at all -- the whole Hit line is the drop it gains."""
    if c.strike():
        c.grants_advantage(until=When.EONT)


@power(
    "m3212a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 3, kind=LIMITED),
    dropped=("Usage.RECHARGE(when=)",),
)
def m3212a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)
        c.push(2)
        c.slowed(until=When.EONT)
    if c.first:
        _recharge_when_bloodied(c)


@power(
    "m3212a3",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3212a3(c: Cast) -> None:
    _advantage_rider(c, "1d6")


@power(
    "m3212a4",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m3212a4(c: Cast) -> None:
    """Appearance and nothing else: the shape taken is the same size and
    keeps every number, so there is nothing a fight can read. Declared inert
    rather than given an invented mechanic."""
    c.note(f"{c.ref}: it takes the appearance of another creature of its own size")


# --------------------------------------------------------------------------
# m3227
# --------------------------------------------------------------------------


@power(
    "m3227a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 3),
)
def m3227a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3227a1",
    level=3,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3227a1(c: Cast) -> None:
    """When whoever is riding it charges, it gets a swing of its own.

    Watched on the rider's `Hit` rather than on the declaration, because the
    declaration is answered before the charge has resolved and the mount's
    swing belongs after it. Once a round, so a rider with two charges in one
    turn does not hand over two free attacks.
    """
    me, ref = c.me, c.ref
    spent: dict[str, int] = {}

    def charged(ev: Hit) -> None:
        if ev.attacker != c.rider() or not getattr(ev, "charge", False):
            return
        if spent.get("round") == c.world.round:
            return
        spent["round"] = c.world.round
        c.basic(on=ev.target, who=me)

    c.watch(Hit, charged, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m3227a2",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.grant_action('mount')",),
)
def m3227a2(c: Cast) -> None:
    """The whole of this line is "a creature of that size may ride it".

    `c.ride` can establish the relation but nothing offers mounting as an
    action, so there is no moment at which this row can become true. Named
    rather than approximated: setting the relation from here would put a
    rider on it that nobody chose."""


# --------------------------------------------------------------------------
# m3271
# --------------------------------------------------------------------------


@power(
    "m3271a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d12", 3),
)
def m3271a0(c: Cast) -> None:
    """"Crit 1d12 + 15" is the maximum of 1d12+3 plus a rolled high-crit
    die, so the extra one is `c.flat(c.roll(...))` -- a second `c.damage`
    inside the crit branch would be maxed as well."""
    if c.strike():
        c.hit()
        if c.crit:
            c.flat(c.roll("1d12"))


@power(
    "m3271a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 3),
)
def m3271a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3271a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d12", 0, kind=LIMITED),
    dropped=("Usage.RECHARGE(when=)",),
)
def m3271a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.crit:
            c.flat(c.roll("1d12"))
        c.ongoing(5)
    if c.first:
        _recharge_when_bloodied(c)


@power(
    "m3271a3",
    level=3,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is bloodied"),
)
def m3271a3(c: Cast) -> None:
    _mobile_attack(c, 3, shifting=True)


# --------------------------------------------------------------------------
# m3542
# --------------------------------------------------------------------------


@power(
    "m3542a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d12", 3),
)
def m3542a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.crit:
            c.flat(c.roll("1d12"))


@power(
    "m3542a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 3),
)
def m3542a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3542a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d12", 3),
)
def m3542a2(c: Cast) -> None:
    """The shove is two squares on a charge, read off `c.charge`.

    The printed Special -- "when charging it can use this in place of a melee
    basic attack" -- is `c.as_basic(window="charge")`, and this creature has
    no trait row to arm it from, so it is filed on first use. That makes the
    substitution available from the second charge onward rather than the
    first, which is the one way this row differs from its card.
    """
    if c.first:
        c.as_basic(c.ref, window="charge", until=When.ENCOUNTER)
    if c.strike():
        c.hit()
        if c.crit:
            c.flat(c.roll("1d12"))
        c.push(2 if c.charge else 1)


@power(
    "m3542a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d12", 3, kind=LIMITED),
    requires=_while_bloodied,
    requires_text="usable only while bloodied",
)
def m3542a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.crit:
            c.flat(c.roll("1d12"))
    c.heal(12, on=c.me)


# --------------------------------------------------------------------------
# m4184
# --------------------------------------------------------------------------


@power(
    "m4184a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 3),
)
def m4184a0(c: Cast) -> None:
    """Two expressions of two types, so the second is rolled in the body --
    the header carries the line a card prints and a policy reads."""
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.LIGHTNING)


@power(
    "m4184a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 3),
)
def m4184a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4184a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4184a2(c: Cast) -> None:
    """`again=True`, because the same at-will row is used twice in one action
    and the second use must not be refused as already spent."""
    for foe in (_adjacent_foes(c) * 2)[:2]:
        c.use_power("m4184a1", on=foe, again=True)
    c.shift(2)


@power(
    "m4184a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("2d6", 2, dtype=DamageType.LIGHTNING, kind=LIMITED),
    dropped=("Usage.RECHARGE(when=)",),
)
def m4184a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(1)
    if c.first:
        _recharge_when_bloodied(c)


# --------------------------------------------------------------------------
# m4616
# --------------------------------------------------------------------------


@power(
    "m4616a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("compendium.silvered",),
)
def m4616a0(c: Cast) -> None:
    """Regeneration plays; nothing marks a weapon as silvered, so the clause
    that switches it off has no property to read."""
    c.regeneration(10)


@power(
    "m4616a1",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4616a1(c: Cast) -> None:
    """Four squares from where its turn began buys it a bigger melee die.

    The starting square is recorded at `TurnStart` and the distance is
    measured on `Moved`, which is the only one of the three movement events
    that carries both ends of a step. The bonus is laid afresh each time the
    test passes and is gated to melee by the damage context's `ranged` key.
    """
    me = c.me
    began: dict[str, Square] = {}

    def start(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost:
            began["at"] = c.here

    def stepped(ev: Any) -> None:
        home = began.get("at")
        if ev.actor != me or home is None:
            return
        here = ev.to
        if max(abs(here[0] - home[0]), abs(here[1] - home[1])) < 4:
            return
        c.bonus(
            "damage", 0, dice="1d8", on=me, until=When.SONT,
            when=lambda ctx: not ctx.get("ranged"),
        )

    c.watch(TurnStart, start, until=When.ENCOUNTER, on=me, label=f"{c.ref} start")
    from combat_engine.engine.events import Moved

    c.watch(Moved, stepped, until=When.ENCOUNTER, on=me, label=f"{c.ref} roamed")


@power(
    "m4616a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d4", 4),
    dropped=("c.contract(ref)",),
    requires=_shapes("beast", "hybrid"),
    requires_text="it must be in beast or hybrid form",
)
def m4616a2(c: Cast) -> None:
    """The burn lands. The Requirement names a shape nothing records, and
    exposure to a disease has no verb to carry it."""
    if c.strike():
        c.hit()
        c.ongoing(2)


@power(
    "m4616a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 4),
    requires=_shapes("humanoid"),
    requires_text="it must be in humanoid form",
)
def m4616a3(c: Cast) -> None:
    """The swing plays; the shape the Requirement names is not recorded."""
    if c.strike():
        c.hit()


@power(
    "m4616a4",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4616a4(c: Cast) -> None:
    """Swing, step, swing -- and the step is what makes two creatures
    reachable where one destination would reach only the first."""
    _two_basics(c, separate=False, between=max(1, c.speed_of(c.me) // 2))


@power(
    "m4616a5",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m4616a5(c: Cast) -> None:
    """It alters its physical form: humanoid, hybrid, beast.

    **Written now that a shape can be read.** This was appearance only,
    and correctly so while nothing could ask which form the creature was
    in -- its own note said the gated attacks carried the gap. Those
    Requirements are gates now, so the shape is what decides which of
    this creature's attacks it may use, and the row is no longer out of
    combat.

    `humanoid` leads the list because that is what the creature is before it
    changes anything, and one form replaces another -- which is what
    "until it uses this power again" means.
    """
    _shapechange(c, "humanoid", "hybrid", "beast")
# --------------------------------------------------------------------------
# m4623
# --------------------------------------------------------------------------


@power(
    "m4623a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d4", 3),
)
def m4623a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.crit:
            c.flat(c.roll("2d4"))


@power(
    "m4623a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m4623a1(c: Cast) -> None:
    """The -2 is held for the length of the row and taken back afterwards:
    laid as a duration it would sit on the creature's opportunity attacks
    for the rest of the turn, which the card does not say."""
    _two_basics(c, separate=True, between=max(1, c.speed_of(c.me) // 2), penalty=2)


@power(
    "m4623a2",
    level=3,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is bloodied",
    on=Trigger(Bloodied, about_me, "it is bloodied"),
)
def m4623a2(c: Cast) -> None:
    """"In either order" is one decision, so the swing is taken first when
    somebody is already in reach and the step comes first when nobody is."""
    if _adjacent_foes(c):
        _two_basics(c, separate=False)
        c.shift(c.speed_of(c.me))
    else:
        c.shift(c.speed_of(c.me))
        foe = next(iter(_adjacent_foes(c)), None)
        if foe is not None:
            c.basic(on=foe)


@power(
    "m4623a3",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m4623a3(c: Cast) -> None:
    """A death throe, and an interrupt because the swing happens before the
    creature is gone -- answered as a reaction it would be made by something
    already off the board."""
    foe = next(iter(_adjacent_foes(c)), None)
    if foe is not None:
        c.basic(on=foe)


# --------------------------------------------------------------------------
# m4735
# --------------------------------------------------------------------------


@power(
    "m4735a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4735a0(c: Cast) -> None:
    """An aura that spoils aim and bites whoever lingers in it.

    The penalty is hung on the zone with `c.grants_in`, so it ends on the
    geometry rather than on a clock -- walking out is what takes it off.
    The damage is its own watch rather than `c.burns`, because that one
    bites on entry and at the top of a turn and the printed line is about
    **ending** a turn inside.
    """
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER)
    c.grants_in(ring, "attack", -2, side="enemy", kind="untyped")

    def lingered(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me:
            return
        if team(c.world, ev.actor) is not team(c.world, me) and c.in_my_aura(ev.actor):
            c.flat(3, on=ev.actor)

    c.watch(TurnEnd, lingered, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m4735a1",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4735a1(c: Cast) -> None:
    """Three clauses, and the third is already true of the grid.

    Sharing its square is `c.shares_space`, which lives on the creature
    being entered rather than on the mover. The shove immunity is gated:
    `c.immovable` would refuse a push from anywhere, and the printed line
    only refuses melee and ranged attacks, so it is written as a shortening
    large enough to swallow any of them with the reach read off the row that
    shoved. Squeezing through a narrow opening needs nothing: the smallest
    gap the grid has is one square, which this creature already fits.
    """
    c.shares_space(difficult=True)
    c.resist_forced(99, when=_shoved_by_hand)


@power(
    "m4735a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 5),
)
def m4735a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty(AC, 2, until=When.EOTNT)
        c.penalty(REF, 2, until=When.EOTNT)


@power(
    "m4735a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=6),
    damage=Damage("3d6", 6, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4735a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4735a4",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy within 3 squares hits it with a close or area attack",
    on=Trigger(Hit, _hit_me_from_a_distance, "a close or area attack catches it"),
)
def m4735a4(c: Cast) -> None:
    """It closes on whoever shelled it and bites.

    "Close or area" is its own predicate rather than `by_melee`: that one
    counts a close burst as melee, which is correct for its own question and
    would let a sword stroke fire this row.
    """
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    _shift_up_to(c, 3, toward=foe)
    c.use_power("m4735a2", on=foe, again=True)


# --------------------------------------------------------------------------
# m5066
# --------------------------------------------------------------------------


@power(
    "m5066a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=6),
    damage=Damage("2d6", 4),
)
def m5066a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5066a1",
    level=3,
    usage=Usage.RECHARGE,
    recharge=5,
    action=MOVE,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=8),
)
def m5066a1(c: Cast) -> None:
    """Five squares, one square at a time, and nobody caught twice.

    The row declares no targets: the route decides whom it passes, which is
    what "each enemy it moves adjacent to during the movement" means, and the
    set of who has already been caught is the rest of that sentence.
    """
    struck: set[int] = set()
    for _ in range(5):
        c.shift(1)
        for foe in _adjacent_foes(c):
            if foe in struck:
                continue
            struck.add(foe)
            if c.strike(on=foe):
                c.slide(2, on=foe)
                c.prone(on=foe)


# --------------------------------------------------------------------------
# m5074
# --------------------------------------------------------------------------


@power(
    "m5074a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=4),
    damage=Damage("1d10", 3, dtype=DamageType.FIRE),
)
def m5074a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5074a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(0),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d10", 3, dtype=DamageType.FIRE),
)
def m5074a1(c: Cast) -> None:
    """Melee 0, written as printed: it reaches only into its own space, which
    is a real range for a creature something can be standing inside."""
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m5078
# --------------------------------------------------------------------------


@power(
    "m5078a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5078a0(c: Cast) -> None:
    """Two of them over one enemy make standing up expensive.

    Standing is announced as the prone hold ending with `why == "stood up"`,
    which is the only way to tell it from a save or a cure. Every creature
    with this trait arms its own copy, so the window would open once per
    holder for one printed sentence -- the lowest-numbered holder is the one
    that opens it, which is arbitrary and consistent.
    """
    me, ref = c.me, c.ref

    def stood(ev: ConditionEnded) -> None:
        if ev.condition is not Condition.PRONE or ev.why != "stood up":
            return
        foe = ev.target
        if team(c.world, foe) is team(c.world, me):
            return
        holders = sorted(
            who
            for who in (me, *c.allies())
            if _carries(c.world, who, ref) and adjacent(c.world, who, foe)
        )
        if len(holders) < 2 or holders[0] != me:
            return
        for watcher in holders:
            c.provoke(watcher, on=foe, why=ref)

    c.watch(ConditionEnded, stood, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m5078a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 4),
)
def m5078a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5078a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 2),
)
def m5078a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5078a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target("enemy", 1, label="one creature it has combat advantage against"),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 4),
    requires=_has_the_drop,
    requires_text="one creature it has combat advantage against",
)
def m5078a3(c: Cast) -> None:
    """The target line narrows the pool and `Target` carries no filter for
    it, so the restriction is read in the body.

    Asked of the board before the roll rather than off the result, which is
    the one place that ordering is right: this is an entry requirement on who
    may be aimed at, not a rider on an attack that has already happened.
    """
    if c.target is None or not has_combat_advantage(c.world, c.me, c.target):
        return
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m5078a4",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target("enemy", 1, label="one prone creature"),
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d4", 6),
    requires=_has_somebody_prone,
    requires_text="one prone creature",
)
def m5078a4(c: Cast) -> None:
    """Prone only, and the step is an Effect rather than a rider on the hit,
    so it happens whether the blow lands or not."""
    if not c.is_(Condition.PRONE):
        c.shift(2)
        return
    if c.strike():
        c.hit()
        c.ongoing(5)
    c.shift(2)


# --------------------------------------------------------------------------
# m5133
# --------------------------------------------------------------------------


@power(
    "m5133a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5133a0(c: Cast) -> None:
    aquatic_edge(c)


@power(
    "m5133a1",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5133a1(c: Cast) -> None:
    """Only slowed creatures lose the opening, so the immunity is gated on
    `ctx["actor"]` -- the window's own word for whoever would swing."""
    c.no_provoke(
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: c.is_(Condition.SLOWED, on=ctx.get("actor")),
    )


@power(
    "m5133a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 6),
)
def m5133a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5133a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d6", 5, kind=LIMITED),
    dropped=("Usage.RECHARGE(when=)",),
)
def m5133a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.POISON)
        c.slowed(until=When.EOTNT)
    if c.first:
        _recharge_when_bloodied(c)


# --------------------------------------------------------------------------
# m5316
# --------------------------------------------------------------------------


@power(
    "m5316a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.ignore_cover(concealment=)",),
)
def m5316a0(c: Cast) -> None:
    """It sees a wounded creature however well hidden, and the gate is read
    on the attack context's target.

    `c.ignore_cover` waives cover **and** concealment together, and the card
    waives only the second -- so this is the printed clause plus a little
    more, which is the narrowing the marker names.
    """
    c.ignore_cover(
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: c.bloodied(on=ctx.get("target")),
    )


@power(
    "m5316a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 6, dtype=DamageType.POISON),
)
def m5316a1(c: Cast) -> None:
    """A venom that worsens on each failed save, written as `escalate`.

    Each stage replaces the hold it grew out of, which is also what clears
    the callback -- leaving the old one standing would mean two saving
    throws for one printed effect.
    """
    if not c.strike():
        return
    c.hit()
    foe = c.target
    stage = {"failed": 0}

    def worsen(eff: Effect) -> None:
        stage["failed"] += 1
        c.world.effects.end(eff, "the venom spread")
        worse = Condition.IMMOBILIZED if stage["failed"] == 1 else Condition.HELPLESS
        c.condition(worse, until=When.SAVE_ENDS, on=foe, escalate=worsen)

    c.condition(Condition.SLOWED, until=When.SAVE_ENDS, on=foe, escalate=worsen)


@power(
    "m5316a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=Target("enemy", 1, label="one immobilized, restrained, or helpless creature"),
    keywords=[Keyword.HEALING],
    attack=Attack(vs=FORT, printed=6),
    requires=_holds_somebody_down,
    requires_text="one immobilized, restrained, or helpless creature",
)
def m5316a2(c: Cast) -> None:
    """It drinks. `c.spend_surge` is the printed "loses a healing surge" and
    is pointed at the target: it defaults to the caster, which would have
    spent the wrong creature's."""
    held = (Condition.IMMOBILIZED, Condition.RESTRAINED, Condition.HELPLESS)
    if not any(c.is_(what) for what in held):
        return
    if c.strike():
        c.spend_surge(on=c.target)
        c.heal(10, on=c.me)


@power(
    "m5316a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5316a3(c: Cast) -> None:
    struck: set[int] = set()
    for foe in _adjacent_foes(c, 2):
        if len(struck) >= 2:
            break
        struck.add(foe)
        c.use_power("m5316a1", on=foe, again=True)


@power(
    "m5316a4",
    level=3,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5316a4(c: Cast) -> None:
    c.shift(max(1, c.speed_of(c.me) // 2))


@power(
    "m5316a5",
    level=3,
    usage=Usage.RECHARGE,
    recharge=4,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=6),
    damage=Damage("1d8", 7, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m5316a5(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)
        for defence in (AC, FORT, REF, WILL):
            c.penalty(defence, 2, until=When.EONT)


@power(
    "m5316a6",
    level=3,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    narrative=("skill:stealth",),
    dropped=("Usage.RECHARGE(when=)",),
)
def m5316a6(c: Cast) -> None:
    """It thins out: unhittable, able to walk through things, and unable to
    swing. All three end together on the free action the card offers.

    The +5 to Stealth is the narrative clause: no board rolls one, so there
    is nothing for the bonus to be read by and nothing missing.
    """
    light = c.insubstantial(until=When.ENCOUNTER, on=c.me)
    through = c.phasing(until=When.ENCOUNTER, on=c.me)
    held = c.cannot_attack(on=c.me, until=When.ENCOUNTER)

    def solidify() -> None:
        for effect in (light, through):
            c.end_effect(effect, why=c.ref)

    c.endable(held, FREE, then=solidify)
    if c.first:
        _recharge_when_bloodied(c)


@power(
    "m5316a7",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(3),
    target=NO_TARGET,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 8, dtype=DamageType.ACID),
    trigger="an enemy hits it with a melee or a close attack",
    on=Trigger(Hit, both(targets_me, by_melee), "a melee or close attack hits it"),
)
def m5316a7(c: Cast) -> None:
    """`by_melee` is exactly this sentence: it counts a close burst and a
    close blast as melee, which is wrong for a row meaning "a sword" and
    right for one printed "a melee or a close attack".

    The step comes before the attack because the card puts it there -- it is
    what brings the triggering creature inside three squares.
    """
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    c.shift(1)
    if c.strike(on=foe):
        c.hit(on=foe)
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS, on=foe)


# --------------------------------------------------------------------------
# m5845
# --------------------------------------------------------------------------


@power(
    "m5845a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5845a0(c: Cast) -> None:
    """Laid when the line is crossed rather than gated inside a `when`:
    `query.speed` is asked with no context in most places, so a gate reading
    one would be false exactly where movement is measured."""
    me = c.me

    def faster() -> None:
        c.bonus("speed", 2, on=me, until=When.ENCOUNTER, kind="power")

    def bled(ev: Bloodied) -> None:
        if ev.actor == me:
            faster()

    if c.bloodied(on=me):
        faster()
    else:
        c.watch(Bloodied, bled, until=When.ENCOUNTER, on=me, once=True, label=c.ref)


@power(
    "m5845a1",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5845a1(c: Cast) -> None:
    """Asked at the moment of the roll, not when the trait arms: who is
    standing next to whom changes every time anything moves."""
    c.gains_advantage(
        lambda ctx: ctx.get("target") is not None
        and any(adjacent(c.world, mate, ctx["target"]) for mate in c.allies()),
        until=When.ENCOUNTER,
        on=c.me,
    )


@power(
    "m5845a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 6),
)
def m5845a2(c: Cast) -> None:
    result = c.strike()
    if not result:
        return
    if result.advantage:
        c.damage("2d6", 6)
    else:
        c.hit()


@power(
    "m5845a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires=_while_bloodied,
    requires_text="it must be bloodied",
)
def m5845a3(c: Cast) -> None:
    """A reckless version of its own at-will, so the row is used rather than
    copied -- `c.landed` reads the borrowed attack's outcome, which is what
    the printed "if the attack hits" asks."""
    foe = c.target
    c.use_power("m5845a2", on=foe, again=True)
    if c.landed:
        c.damage("2d6", on=foe, detail=c.ref)
    else:
        c.damage("1d6", on=c.me, detail=c.ref)


@power(
    "m5845a4",
    level=3,
    usage=Usage.RECHARGE,
    recharge=4,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5845a4(c: Cast) -> None:
    _shift_up_to(c, max(1, c.speed_of(c.me) // 2), toward=_nearest(c))
    for foe in _adjacent_foes(c):
        c.grants_advantage(on=foe, until=When.EOT, to=c.me)


# --------------------------------------------------------------------------
# m6034
# --------------------------------------------------------------------------


@power(
    "m6034a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6034a0(c: Cast) -> None:
    """Named terrain, not all of it: `kind=` is the label a zone carries, so
    this creature still slows down in rubble."""
    c.ignores_difficult("web", on=c.me, until=When.ENCOUNTER)


@power(
    "m6034a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 3),
)
def m6034a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m6034a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6034a2(c: Cast) -> None:
    """In, bite, out. `c.jump` rather than `c.move`: a jump clears what is in
    the way, which is the difference between this and walking."""
    c.no_provoke(on=c.me, until=When.EOT)
    c.jump(4)
    foe = next(iter(_adjacent_foes(c)), None)
    if foe is not None:
        c.basic(on=foe)
    c.jump(4)


# --------------------------------------------------------------------------
# m6350
# --------------------------------------------------------------------------


@power(
    "m6350a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6350a0(c: Cast) -> None:
    _advantage_rider(c, "1d6")


@power(
    "m6350a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 3),
)
def m6350a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m6350a2",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d6", 4, dtype=DamageType.POISON, kind=LIMITED),
)
def m6350a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m6350a3",
    level=3,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6350a3(c: Cast) -> None:
    c.shift(max(1, c.speed_of(c.me) // 2))


@power(
    "m6350a4",
    level=3,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is bloodied"),
)
def m6350a4(c: Cast) -> None:
    """`c.restore_use` then `c.use_power`: the card recharges the blast and
    fires it in one free action, and spending the restored use is what makes
    the row cost something afterwards."""
    c.restore_use("m6350a2", on=c.me)
    c.use_power("m6350a2")


# --------------------------------------------------------------------------
# m6514
# --------------------------------------------------------------------------


@power(
    "m6514a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6514a0(c: Cast) -> None:
    """Only against openings, read off the attack context's own flag."""
    c.bonus(
        AC, 4, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


@power(
    "m6514a1",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6514a1(c: Cast) -> None:
    c.resist_forced(1)


@power(
    "m6514a2",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6514a2(c: Cast) -> None:
    """A save to stay on its feet, and `bare=True` is why it can succeed.

    `Effects.apply` installs the condition and then announces it, so by the
    time this is heard the creature is already prone -- the save is rolled
    against nothing in particular and winning it is written as curing the
    hold that just landed. An ordinary `c.save` looks for a save-ends effect,
    finds none, and returns False without ever rolling.
    """
    me = c.me

    def shoved(ev: ConditionApplied) -> None:
        if ev.target != me or ev.condition is not Condition.PRONE:
            return
        if c.save(on=me, bare=True):
            c.cure(Condition.PRONE, on=me)

    c.watch(ConditionApplied, shoved, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6514a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 6),
)
def m6514a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


# --------------------------------------------------------------------------
# m6567
# --------------------------------------------------------------------------


@power(
    "m6567a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6567a0(c: Cast) -> None:
    """Anything that would stop it answering m6567a4 ends instead.

    Two watches, because a domination arrives as a `RelationSet` and is never
    announced as a condition at all -- a single `ConditionApplied` listener
    is correctly armed and silently misses the one condition the printed
    sentence names first.
    """
    me = c.me

    def landed(ev: ConditionApplied) -> None:
        if ev.target == me and ev.condition in _SILENCING:
            c.end_effect(on=me, carrying=ev.condition, why=c.ref)

    def tied(ev: RelationSet) -> None:
        if ev.target == me and ev.kind_ is Relation.DOMINATED_BY:
            c.cure(Condition.DOMINATED, on=me)

    c.watch(ConditionApplied, landed, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(RelationSet, tied, until=When.ENCOUNTER, on=me, label=f"{c.ref} freed")


@power(
    "m6567a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 3),
)
def m6567a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m6567a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(2),
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=6),
)
def m6567a2(c: Cast) -> None:
    """No damage line at all -- the whole Hit is the domination."""
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


@power(
    "m6567a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=0,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("2d8", 3, kind=LIMITED),
    trigger="an enemy adjacent to it misses it",
    on=Trigger(Miss, _missed_me_from_beside, "an adjacent enemy misses it"),
    dropped=("Usage.RECHARGE(when=)",),
)
def m6567a3(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.slide(3, on=foe)
    if c.first:
        _recharge_when_bloodied(c)


@power(
    "m6567a4",
    level=3,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy is within 3 squares when its turn starts, or ends its turn within 3 squares",
    on=(
        Trigger(TurnStart, _foe_near_at_my_turn, "an enemy is within 3 as its turn starts"),
        Trigger(TurnEnd, _foe_ended_near_me, "an enemy ends its turn within 3 squares"),
    ),
)
def m6567a4(c: Cast) -> None:
    """Two printed triggers, so two declared ones -- `on=` takes a sequence,
    and declaring half of a two-clause trigger looks finished and is wrong.

    Which creature is "the triggering enemy" differs between them: the turn
    that ended names its own actor, and its own turn starting names nobody,
    so the nearest enemy is the one it goes for.
    """
    actor = getattr(c.trigger, "actor", None)
    foe = actor if actor is not None and actor != c.me else _nearest(c)
    if foe is None:
        return
    _shift_up_to(c, max(1, c.speed_of(c.me) // 2), toward=foe)
    c.use_power("m6567a1", on=foe, again=True)


# --------------------------------------------------------------------------
# m6577
# --------------------------------------------------------------------------


@power(
    "m6577a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6577a0(c: Cast) -> None:
    """Regeneration 5 while airborne, switched off for a turn by psychic.

    **Two printed clauses and they are different mechanisms**, which is why
    the row says both and not one:

    * on the ground it heals nothing *that* turn -- state, read at the tick,
      so `unless=`. Nothing is switched off; the next turn in the air heals
      normally.
    * psychic damage switches the trait off for the whole of its next turn --
      an event with a clock, so `c.suspend_when` with `When.EONT`. `SONT`
      would be wrong: the suspension has to still be standing when the turn
      *starts*, which is the moment the healing would happen.
    """
    heals = c.regeneration(
        5, until=When.ENCOUNTER, on=c.me, unless=lambda: c.height(on=c.me) == 0
    )
    c.suspend_when(
        heals, DamageApplied,
        lambda ev: ev.target == c.me
        and DamageType.PSYCHIC in {ev.dtype, *ev.dtypes},
        for_=When.EONT,
    )


@power(
    "m6577a1",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6577a1(c: Cast) -> None:
    """"While flying to move" is a state rather than a permission, which is
    what `c.moving_as` answers -- `Movement.modes` only ever said what the
    creature *could* do."""
    for defence in (AC, FORT, REF, WILL):
        c.bonus(
            defence, 4, on=c.me, until=When.ENCOUNTER, kind="power",
            when=lambda ctx: c.moving_as("fly", on=c.me),
        )


@power(
    "m6577a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 4),
)
def m6577a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6577a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("2d8", 3, kind=LIMITED),
)
def m6577a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


# --------------------------------------------------------------------------
# m6580
# --------------------------------------------------------------------------


@power(
    "m6580a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6580a0(c: Cast) -> None:
    """Regeneration 5, switched off for a turn by cold or psychic."""
    heals = c.regeneration(5, until=When.ENCOUNTER, on=c.me)
    c.suspend_when(
        heals, DamageApplied,
        lambda ev: ev.target == c.me
        and bool({DamageType.COLD, DamageType.PSYCHIC} & {ev.dtype, *ev.dtypes}),
        for_=When.EONT,
    )


@power(
    "m6580a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 3),
)
def m6580a1(c: Cast) -> None:
    """Ongoing damage of one type does not stack -- the highest applies --
    so "increase it by 5 to a maximum of 10" is one call with the standing
    burn read first. Two calls would be refused as the weaker of the pair."""
    if not c.strike():
        return
    c.hit()
    foe = c.target
    if foe is None:
        return
    standing = _ongoing_of(c, foe, DamageType.FIRE)
    c.ongoing(min(10, standing + 5), DamageType.FIRE, on=foe)


@power(
    "m6580a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("2d8", 3, dtype=DamageType.FIRE, kind=LIMITED),
)
def m6580a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6580a3",
    level=3,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6580a3(c: Cast) -> None:
    c.shift(max(1, c.speed_of(c.me) // 2))


# --------------------------------------------------------------------------
# m6583
# --------------------------------------------------------------------------


@power(
    "m6583a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6583a0(c: Cast) -> None:
    """Regeneration 5, switched off for a turn by fire or psychic."""
    heals = c.regeneration(5, until=When.ENCOUNTER, on=c.me)
    c.suspend_when(
        heals, DamageApplied,
        lambda ev: ev.target == c.me
        and bool({DamageType.FIRE, DamageType.PSYCHIC} & {ev.dtype, *ev.dtypes}),
        for_=When.EONT,
    )


@power(
    "m6583a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 4),
)
def m6583a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6583a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.POISON, Keyword.ZONE],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("2d6", 4, dtype=DamageType.POISON, kind=LIMITED, half_on_miss=True),
)
def m6583a2(c: Cast) -> None:
    """The cloud it leaves shelters it, and the shelter is hung on the zone.

    `c.grants_in` ends on the geometry rather than on a clock, which is what
    "while in the zone" means. "Lightly obscured" is the dropped half: a
    zone can block sight outright or not at all, and there is nothing
    between the two for concealment to come out of.
    """
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)
    if c.first:
        cloud = c.zone(c.area(), until=When.EONT, obscured="dim")
        for defence in (AC, FORT, REF, WILL):
            c.grants_in(cloud, defence, 2, side="team", kind="power")
        _recharge_when_bloodied(c)


@power(
    "m6583a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    dropped=("c.ignore_squeeze_penalty()",),
)
def m6583a3(c: Cast) -> None:
    """It thins out, and the printed Sustain Standard is its own hold.

    `c.insubstantial` takes no sustain of its own, so the hold that is
    sustained is separate and re-lays the insubstantiality each time it is
    kept up -- without `c.on_sustain` the clock would refresh and the
    payout half of the line would go nowhere.

    Moving at full speed while squeezing, and not granting the drop for it,
    is the dropped clause: the squeeze penalties are not waivable.
    """
    c.insubstantial(until=When.EONT, on=c.me)
    held = c.effect(c.ref, until=When.SUSTAIN, on=c.me, sustain=STANDARD)
    c.on_sustain(held, lambda: c.insubstantial(until=When.EONT, on=c.me))


# --------------------------------------------------------------------------
# m850
# --------------------------------------------------------------------------


@power(
    "m850a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 3),
)
def m850a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m850a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 3),
)
def m850a1(c: Cast) -> None:
    """Two axes, two creatures, and a step before each swing.

    The row declares no target: the two it catches depend on where the steps
    put it, which is the printed "separate targets" read as the sentence it
    is rather than as a two-target header.
    """
    struck: set[int] = set()
    for _ in range(2):
        c.shift(1)
        foe = next((f for f in _adjacent_foes(c) if f not in struck), None)
        if foe is None:
            continue
        struck.add(foe)
        if c.strike(on=foe):
            c.hit(on=foe)


@power(
    "m850a2",
    level=3,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    trigger="it hits a bloodied enemy",
    on=Trigger(Hit, _hit_a_bloodied_enemy, "it hits a bloodied enemy"),
    defect="the printed attack line has no defence in the compendium",
)
def m850a2(c: Cast) -> None:
    """The extraction lost both defences this attack names.

    The card reads "+6 vs <one> or <other> (whichever is lower)" with the two
    names gone, so there is no defence to declare and no pair to compare --
    the attack cannot be rolled at all. Named rather than guessed: picking
    one would be an invented number in a header a policy reads as printed.
    """


@power(
    "m850a3",
    level=3,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="a melee attack misses it",
    on=Trigger(Miss, both(targets_me, by_melee), "a melee attack misses it"),
)
def m850a3(c: Cast) -> None:
    c.shift(1)


@power(
    "m850a4",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m850a4(c: Cast) -> None:
    """Gated on the *effect's* keywords, which the save context carries:
    `durations` reads them off the label of whatever laid the hold, so
    "against fear or charm effects" is a real narrowing rather than a flat
    bonus that would be too generous in every other save it took."""
    c.bonus(
        "save", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(
            set(ctx.get("keywords", ())) & {Keyword.FEAR, Keyword.CHARM}
        ),
    )


# --------------------------------------------------------------------------
# m851
# --------------------------------------------------------------------------


@power(
    "m851a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 3),
)
def m851a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m851a1",
    level=3,
    usage=AT_WILL,
    action=MOVE,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=6),
)
def m851a1(c: Cast) -> None:
    """It steps three squares and then picks a victim, so the row declares no
    target: choosing one at declaration would measure reach from where it
    stood rather than from where it arrives.

    No damage at all -- the whole Hit line is the drop it gains.
    """
    _shift_up_to(c, 3, toward=_nearest(c))
    foe = next(iter(_adjacent_foes(c)), None)
    if foe is not None and c.strike(on=foe):
        c.grants_advantage(on=foe, until=When.EONT, to=c.me)


@power(
    "m851a2",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m851a2(c: Cast) -> None:
    _advantage_rider(c, "1d6")


@power(
    "m851a3",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m851a3(c: Cast) -> None:
    """Appearance only: the shape taken is the same size and keeps every
    number, so a fight can read nothing off it."""
    c.note(f"{c.ref}: it takes the appearance of another creature of its own size")
