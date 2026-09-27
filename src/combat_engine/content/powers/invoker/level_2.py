"""Invoker, level 2: the utilities.

Three of these are narrative only -- a skill bonus, a loud voice, a piece of
knowledge -- and carry `out_of_combat=True` rather than an invented mechanic.
The fourth rerolls a check, which is a real event, so it answers one.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    FREE,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    PERSONAL,
    SELF,
    STANDARD,
    Bloodied,
    Cast,
    CloseBurst,
    DamageRolled,
    DamageType,
    Dropped,
    Keyword,
    PowerUsed,
    Ranged,
    SkillCheck,
    Trigger,
    UpTo,
    Usage,
    When,
    get,
    my_check,
    power,
)
from combat_engine.engine.query import team

#: The three the card names.
_KNOWLEDGE = ("arcana", "history", "religion")
_A_KNOWLEDGE_CHECK = "you dislike the result of a knowledge check"


def _damaged_by_an_enemy(world: object, me: int, ev: object) -> bool:
    """"You are damaged by an enemy's attack." `hits_me` reads `attacker`
    and a damage event spells it `source`, so neither it nor `targets_me`
    alone says this."""
    source = getattr(ev, "source", None)
    return (
        getattr(ev, "target", None) == me
        and source is not None
        and team(world, source) is not team(world, me)
    )


@power(
    "p10093",
    level=2,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.HEALING, Keyword.ZONE],
)
def p10093(c: Cast) -> None:
    """"Becomes bloodied or drops" is two events; `Bloodied` already means
    the crossing rather than the state, so no nonbloodied test is needed
    on that half."""
    ward = c.zone(c.area(), until=When.EONT)
    mates = {c.me, *c.allies()}

    def rally(ev: Bloodied | Dropped, z: int = ward) -> None:
        who = ev.actor
        if who not in mates or who not in c.world.zones.occupants(z):
            return
        if c.may("spend a healing surge", who=who):
            c.surge(on=who)

    c.watch(Bloodied, rally, until=When.EONT)
    c.watch(Dropped, rally, until=When.EONT)


@power(
    "p11284",
    level=2,
    cls="invoker",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE, Keyword.RADIANT, Keyword.STANCE],
)
def p11284(c: Cast) -> None:
    """"Not adjacent to any creature" counts every creature, not only
    enemies, so the neighbour test runs over the whole board."""
    c.stance(label=c.ref)
    hurt = max(c.con_mod, c.int_mod)

    def smite(ev: PowerUsed) -> None:
        if ev.actor != c.me:
            return
        p = get(ev.power)
        if p is None or Keyword.DIVINE not in p.keywords:
            return
        if p.usage not in (Usage.ENCOUNTER, Usage.DAILY):
            return
        alone = [
            foe
            for foe in c.enemies()
            if c.can_see(foe) and not [x for x in c.within(1, of=foe) if x != foe]
        ]
        if not alone:
            return
        picked = c.choose(alone, "who the light singles out")
        if picked is not None:
            c.flat(hurt, dtype=DamageType.RADIANT, on=picked)

    c.watch(PowerUsed, smite, until=When.STANCE)


@power(
    "p2863",
    level=2,
    cls="invoker",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=UpTo(2, "ally"),
    keywords=[Keyword.DIVINE],
)
def p2863(c: Cast) -> None:
    c.pull(3)


@power(
    "p2864",
    level=2,
    cls="invoker",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
    out_of_combat=True,
)
def p2864(c: Cast) -> None:
    c.note("p2864: +5 to one social check, and two successes in a challenge")


@power(
    "p5190",
    level=2,
    cls="invoker",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
    out_of_combat=True,
)
def p5190(c: Cast) -> None:
    c.note("p5190: heard clearly for 500 feet, and a bonus to one check")


@power(
    "p7163",
    level=2,
    cls="invoker",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
)
def p7163(c: Cast) -> None:
    c.no_provoke(until=When.EONT)


@power(
    "p7164",
    level=2,
    cls="invoker",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.ZONE],
)
def p7164(c: Cast) -> None:
    hope = c.zone(c.area(), until=When.EONT)
    if c.int_mod <= 0:
        return
    for mate in (c.me, *c.allies()):
        c.bonus(
            "save",
            c.int_mod,
            on=mate,
            kind="power",
            until=When.EONT,
            when=lambda ctx, w=mate, z=hope: w in c.world.zones.occupants(z),
        )


@power(
    "p7165",
    level=2,
    cls="invoker",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
    out_of_combat=True,
)
def p7165(c: Cast) -> None:
    c.note("p7165: you learn one creature's resistances and vulnerabilities")


@power(
    "p7166",
    level=2,
    cls="invoker",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
    trigger=_A_KNOWLEDGE_CHECK,
    on=Trigger(SkillCheck, my_check(*_KNOWLEDGE), _A_KNOWLEDGE_CHECK),
)
def p7166(c: Cast) -> None:
    """"Use either result" is `keep="best"`: the roll is already made and
    disliked, so nobody takes the worse of the two on purpose."""
    c.reroll_check(keep="best", bonus=c.int_mod)


@power(
    "p7167",
    level=2,
    cls="invoker",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
    trigger="you are damaged by an enemy's attack",
    on=Trigger(DamageRolled, _damaged_by_an_enemy, "you are damaged by an enemy"),
)
def p7167(c: Cast) -> None:
    """The reduction is written onto the damage the interrupt is answering,
    which is the only place five points can come off one blow -- `c.resist`
    would shave every hit of the turn."""
    ev = c.trigger
    if ev is not None:
        ev.amount = max(0, ev.amount - 5)
    mates = [a for a in c.within(5, side="ally") if a != c.me]
    if not mates:
        return
    picked = c.choose(mates, "who is heartened")
    if picked is not None:
        c.bonus("attack", 1, on=picked, kind="power", until=When.SONT)


def _i_dropped_an_enemy(world: object, me: int, ev: object) -> bool:
    """"You drop a non-minion enemy with an invoker attack power."

    Left out of the first pass because `Dropped` carried only `actor` and
    `dead`, so nothing could say who did the dropping. It carries `source`
    now. A minion is the creature whose maximum is 1.
    """
    from combat_engine.engine import Health
    from combat_engine.engine.query import team

    if getattr(ev, "source", None) != me:
        return False
    victim = getattr(ev, "actor", None)
    if victim is None or team(world, victim) == team(world, me):
        return False
    health = world.get(victim, Health)
    return health is not None and health.max_hp > 1


@power(
    "p11285",
    level=2,
    cls="invoker",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ALLY,
    keywords=[Keyword.DIVINE],
    trigger="you drop a non-minion enemy to 0 hit points with an invoker attack power",
    on=Trigger(Dropped, _i_dropped_an_enemy, "you drop a non-minion enemy"),
)
def p11285(c: Cast) -> None:
    """The caster is a target too -- "you and each ally in the burst" -- and
    `EACH_ALLY` leaves the caster out, so the once-per-power line hands the
    caster its own share."""
    c.temp_hp(c.wis_mod)
    if c.first:
        c.temp_hp(c.wis_mod, on=c.me)
