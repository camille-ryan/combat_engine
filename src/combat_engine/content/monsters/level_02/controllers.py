"""Monster abilities, level 2: the controllers and the minions beside them.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=7)` and `Damage("1d8", 2)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths. A minion's flat damage says so with `kind=MINION`
and rescales with everything else. See `engine/scaling.py` and
`engine/monster_math.py`.

Two shapes recur here and are settled once.

An **aura that acts when a turn ends in it** is the aura plus a `TurnEnd`
watch that asks the zone who is standing in it. Membership is never kept as
a list: the aura travels with its owner and a stored one would be stale the
moment either of them moved.

A printed range of "10/20" is a normal range and a long range, and `Range`
holds one number, so the row takes the normal one -- the band where it
shoots without a penalty the engine has no way to apply.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_01 import aquatic_edge, settle
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
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
    Ranged,
    Target,
    Usage,
    When,
    World,
    get,
    power,
    use,
)
from combat_engine.engine.events import Dropped, Hit, TurnEnd
from combat_engine.engine.monster_math import MINION
from combat_engine.engine.query import alive, team
from combat_engine.engine.triggers import Trigger, about_me

#: The three conditions m4787a0 pays its larger number against. Written out
#: rather than asked one at a time so the row reads as the printed line does.
HELD_FAST = (Condition.IMMOBILIZED, Condition.RESTRAINED, Condition.HELPLESS)


def _bloodied(world: World, eid: int) -> bool:
    """A printed Requirement line wants a predicate on the caster, and
    `Cast.bloodied` is only reachable once the body is already running."""
    health = world.get(eid, Health)
    return health is not None and health.bloodied


def _hit_by_cold(world: World, me: int, ev: Hit) -> bool:
    """"Hit by a cold attack": the keyword is on the power, not the event.

    `by_melee` asks the same registry the same way for the reach of the
    thing that landed; this asks for its keywords.
    """
    if getattr(ev, "target", None) != me:
        return False
    p = get(getattr(ev, "power", "") or "")
    return p is not None and Keyword.COLD in p.keywords


def _enemy_hits_me(world: World, me: int, ev: Hit) -> bool:
    """"An enemy hits it" -- at any range, so `enemy_within` cannot say it."""
    if getattr(ev, "target", None) != me:
        return False
    attacker = getattr(ev, "attacker", None)
    return attacker is not None and team(world, attacker) is not team(world, me)


# --------------------------------------------------------------------------
# m287
# --------------------------------------------------------------------------


@power(
    "m287a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m287a0(c: Cast) -> None:
    """Four modifiers, one per defence, each gated on the company it is in.

    The gate is asked when the defence is read rather than kept up to date
    as the crowd moves, so nothing has to watch anybody walking away. "Two
    or more allies" counts the neighbours: `side="ally"` includes the
    creature itself, which is not one of them.
    """

    def in_company(_ctx: dict[str, object]) -> bool:
        return len([a for a in c.within(1, side="ally") if a != c.me]) >= 2

    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=c.me, until=When.ENCOUNTER, when=in_company)


@power(
    "m287a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage(bonus=5, kind=MINION),
)
def m287a1(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m2941
# --------------------------------------------------------------------------


@power(
    "m2941a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 5, dtype=DamageType.PSYCHIC),
)
def m2941a0(c: Cast) -> None:
    """The spec prints no range for this one where it prints Ranged 10 for
    the next, so it is read as the creature's melee attack."""
    if c.strike():
        c.hit()


@power(
    "m2941a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=6),
    damage=Damage("1d4", 5, dtype=DamageType.PSYCHIC),
)
def m2941a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m2941a2",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(vs=WILL, printed=5),
)
def m2941a2(c: Cast) -> None:
    """No damage at all -- the whole of the hit is the hold.

    "First Failed Saving Throw" is `escalate`: the slow ends and the
    immobilisation replaces it, carrying no escalation of its own so it
    cannot fire twice.
    """

    def worsen(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.immobilized(until=When.SAVE_ENDS, on=eff.owner)

    if c.strike():
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, escalate=worsen)


@power(
    "m2941a3",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target("any", 1, label="One helpless or unconscious creature"),
    keywords=[Keyword.HEALING],
)
def m2941a3(c: Cast) -> None:
    """Settle on the kill and feed.

    The printed target restriction lives in the `Target` label, which is
    prose: `coup_de_grace` is the thing that enforces it, refusing outright
    for anything that is not actually helpless. The price is paid first
    either way, as printed. "Regains all of its hit points" is whatever it
    is currently down, so it is read off `c.missing` rather than assumed.
    """
    settle(c)
    if c.coup_de_grace() and not alive(c.world, c.target):
        c.heal(c.missing(on=c.me), on=c.me)


# --------------------------------------------------------------------------
# m306
# --------------------------------------------------------------------------


@power(
    "m306a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m306a0(c: Cast) -> None:
    """Ending a turn in it, not entering it or starting there, so this is a
    `TurnEnd` watch rather than `c.hazard`, whose teeth bite at the other
    two moments. Who is inside is asked of the zone as the turn ends."""
    ring = c.aura(1, until=When.ENCOUNTER)

    def sting(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor not in c.enemies():
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.flat(2, on=ev.actor)

    c.watch(TurnEnd, sting, until=When.ENCOUNTER, on=c.me, label="m306a0")


@power(
    "m306a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=5),
    damage=Damage(bonus=4, kind=MINION),
)
def m306a1(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m4787
# --------------------------------------------------------------------------


@power(
    "m4787a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=5),
    damage=Damage(bonus=6, kind=MINION),
)
def m4787a0(c: Cast) -> None:
    """"6, or 9 against a held target": the extra three ride on top of the
    declared damage rather than replacing it, so the row still rescales."""
    if c.strike():
        c.hit()
        if any(c.is_(cond) for cond in HELD_FAST):
            c.flat(3)


# --------------------------------------------------------------------------
# m4840
# --------------------------------------------------------------------------


@power(
    "m4840a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4840a0(c: Cast) -> None:
    ring = c.aura(1, until=When.ENCOUNTER)

    def nudge(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor not in c.enemies():
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.slide(1, on=ev.actor)

    c.watch(TurnEnd, nudge, until=When.ENCOUNTER, on=c.me, label="m4840a0")


@power(
    "m4840a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 2, dtype=DamageType.COLD),
)
def m4840a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)


@power(
    "m4840a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 4, dtype=DamageType.COLD),
)
def m4840a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m4840a3",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires=_bloodied,
    requires_text="the m4840 must be bloodied",
)
def m4840a3(c: Cast) -> None:
    """Both rows rather than a copy of their numbers, so the damage lines
    stay in one place and rescale with them; free of charge, both being
    at-wills. Neither printed line says how the two are shared out, so both
    go into the creature this body was called for."""
    use(c.world, c.me, "m4840a1", targets=[c.target], spend=False)
    use(c.world, c.me, "m4840a2", targets=[c.target], spend=False)


_M4840_CHILLED = "the m4840 is hit by a cold attack"


@power(
    "m4840a4",
    level=2,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4840_CHILLED,
    on=Trigger(Hit, when=_hit_by_cold, text=_M4840_CHILLED),
)
def m4840a4(c: Cast) -> None:
    """The aura is m4840a0's and is an aura 1, so "each enemy in it" is each
    enemy within 1 -- asked of the board rather than of the zone, which this
    row has no handle on."""
    for who in c.within(1, side="enemy"):
        c.slide(1, on=who)


# --------------------------------------------------------------------------
# m4880
# --------------------------------------------------------------------------


@power(
    "m4880a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4880a0(c: Cast) -> None:
    aquatic_edge(c)


@power(
    "m4880a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 6),
)
def m4880a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m4880a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=5),
    damage=Damage("2d6", 2),
)
def m4880a2(c: Cast) -> None:
    """Dragged in first and put down where it lands, which is the printed
    order and the one that leaves it adjacent."""
    if c.strike():
        c.hit()
        c.pull(2)
        c.prone()


_M4880_DROPS = "the m4880 drops to 0 hit points"


@power(
    "m4880a3",
    level=2,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.POISON],
    trigger=_M4880_DROPS,
    on=Trigger(Dropped, when=about_me, text=_M4880_DROPS),
    attack=Attack(vs=FORT, printed=5),
    damage=Damage("1d6", 7, dtype=DamageType.POISON),
)
def m4880a3(c: Cast) -> None:
    """`EACH_OTHER` rather than `EACH_CREATURE`: a close burst's origin is
    the creature itself, and "creatures in the burst" does not mean it."""
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m730
# --------------------------------------------------------------------------


@power(
    "m730a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m730a0(c: Cast) -> None:
    """A gate rather than an effect put on and taken off around every move:
    the attack context carries `opportunity`, so the modifier is asked
    whether it applies at the moment the defence is read."""
    c.bonus(
        AC,
        2,
        until=When.ENCOUNTER,
        on=c.me,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


@power(
    "m730a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage(bonus=4, kind=MINION),
)
def m730a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m730a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage(bonus=4, kind=MINION),
)
def m730a2(c: Cast) -> None:
    if c.strike():
        c.hit()


_M730_HIT_BY_ENEMY = "an enemy hits the m730 with an attack"


@power(
    "m730a3",
    level=2,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger=_M730_HIT_BY_ENEMY,
    on=Trigger(Hit, when=_enemy_hits_me, text=_M730_HIT_BY_ENEMY),
)
def m730a3(c: Cast) -> None:
    """The new roll stands whatever it is, so `keep="new"` rather than
    "worst". An interrupt: the reroll has to land before the hit is acted
    on, because what it is for is the hit turning into a miss."""
    c.reroll_attack(keep="new")
