"""Bard, level 1: the ranged and burst attacks, and the three no-action riders.

The riders hang off a basic attack, so they declare `Trigger(Hit, ...)` with a
predicate that asks whether the row that swung was that creature's *own*
basic -- a monster or a character can have its basic replaced, and comparing
against the engine's two default refs alone would miss it.
"""

from __future__ import annotations

from combat_engine.content.powers.bard._shared import (
    free_near,
    square_of,
)
from combat_engine.engine import *

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


def _my_basic_hit(world: World, me: int, ev: Event) -> bool:
    """You hit with a basic attack -- whichever row that creature's actually is."""
    if getattr(ev, "attacker", None) != me:
        return False
    known = world.get(me, Powers)
    own = (known.basic if known else "") or ""
    return getattr(ev, "power", "") in {own, MELEE, RANGED}


@power(
    "p11108",
    level=1,
    cls="bard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(CHA, vs=WILL),
)
def p11108(c: Cast) -> None:
    """The ally swings after the push rather than during it: the printed line
    allows either and only one of them is a moment the engine has."""
    if not c.strike():
        return
    victim = c.target
    c.damage(0, c.cha_mod, dtype=DamageType.THUNDER)
    c.push(2, on=victim)
    mates = [a for a in c.within(1, of=victim, side="ally") if a != c.me]
    pick = c.choose(mates, "which ally makes the free melee basic attack", optional=True)
    if pick is not None:
        c.grant_attack(pick, on=victim)


@power(
    "p11109",
    level=1,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p11109(c: Cast) -> None:
    """Judged where the target *finishes* its next turn rather than tracked
    square by square: entering the spot and stepping out again would pay the
    damage under the printed line and does not here."""
    if not c.strike():
        return
    victim = c.target
    c.damage("1d8", c.cha_mod, dtype=DamageType.PSYCHIC)
    here = square_of(c, victim)
    if here is None:
        return
    spot = c.choose(sorted(spread({here}, 1) - {here}), "the square the target must enter")
    if spot is None:
        return
    sting, done = c.cha_mod, []

    def check(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != victim or done:
            return
        done.append(1)
        if square_of(c, victim) != spot:
            c.flat(sting, dtype=DamageType.PSYCHIC, on=victim)

    c.watch(TurnEnd, check, until=When.ENCOUNTER, on=c.me, label="p11109")


@power(
    "p11110",
    level=1,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p11110(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", c.cha_mod, dtype=DamageType.PSYCHIC)
        if c.cha_mod > 0:
            c.push(c.cha_mod)
    else:
        c.half_damage("1d10", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.push(1)
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            if mate != c.me:
                c.shift(1, who=mate)


@power(
    "p12511",
    level=1,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE, Keyword.TELEPORTATION],
    attack=Attack(CHA, vs=WILL),
)
def p12511(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    c.damage("1d8", c.cha_mod, dtype=DamageType.FORCE)
    here = square_of(c, victim)
    taken: set[Square] = set()
    for mate in [a for a in c.within(5, of=victim, side="ally") if a != c.me][:2]:
        spot = free_near(c, here, skip=frozenset(taken))
        if spot is None:
            return
        taken.add(spot)
        c.teleport(20, who=mate, to=spot)


@power(
    "p14451",
    level=1,
    cls="bard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
    trigger="you hit an enemy within 5 squares of you with a basic attack using a weapon",
    on=Trigger(Hit, _my_basic_hit, "you hit an enemy with a basic attack"),
)
def p14451(c: Cast) -> None:
    foe = getattr(c.trigger, "target", None)
    if foe is None:
        return
    c.damage(c.w(), on=foe)
    here = square_of(c, foe)
    spot = free_near(c, here)
    if spot is not None:
        c.teleport(20, to=spot)
    mates = [a for a in c.within(5, side="ally") if a != c.me]
    pick = c.choose(mates, "which ally teleports in", optional=True)
    if pick is not None:
        second = free_near(c, here)
        if second is not None:
            c.teleport(20, who=pick, to=second)


@power(
    "p14452",
    level=1,
    cls="bard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    trigger="you hit an enemy with a basic attack using a weapon",
    on=Trigger(Hit, _my_basic_hit, "you hit an enemy with a basic attack"),
)
def p14452(c: Cast) -> None:
    foe = getattr(c.trigger, "target", None)
    if foe is not None:
        c.dazed(on=foe, until=When.EONT)


@power(
    "p14453",
    level=1,
    cls="bard",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.THUNDER],
    trigger="you hit an enemy with a basic attack using a weapon",
    on=Trigger(Hit, _my_basic_hit, "you hit an enemy with a basic attack"),
)
def p14453(c: Cast) -> None:
    """The concealment half is dropped: concealment is cover's cousin here and
    nothing takes it away from one creature."""
    foe = getattr(c.trigger, "target", None)
    if foe is None:
        return
    c.flat(5, dtype=DamageType.THUNDER, on=foe)
    c.grants_advantage(on=foe, to="allies", until=When.EONT)


@power(
    "p2346",
    level=1,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CHARM],
    attack=Attack(CHA, vs=WILL),
)
def p2346(c: Cast) -> None:
    """"Until you or one of your allies attacks the target" is a second watch,
    not a duration: the hold has to be ended early by something."""
    if not c.strike():
        return
    victim = c.target
    shielded = c.choose([c.me, *c.allies()], "who the target cannot attack")
    if shielded is None:
        return
    held = c.cannot_attack(on=victim, against=shielded, until=When.EONT)
    if held is None:
        return

    def broken(ev: AttackDeclared) -> None:
        if ev.target != victim:
            return
        if ev.attacker == c.me or ev.attacker in c.allies():
            c.world.effects.end(held, "the charm is broken")

    c.watch(AttackDeclared, broken, until=When.EONT, on=c.me, label="p2346")


@power(
    "p2347",
    level=1,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CHARM],
    attack=Attack(CHA, vs=WILL),
)
def p2347(c: Cast) -> None:
    """The bard's Intelligence build is the printed Virtue of Cunning line."""
    if not c.strike():
        return
    victim = c.target
    c.damage("1d6", c.cha_mod)
    c.slide(2, on=victim)
    swing = 1 + c.int_mod if c.build("f1s0") else 2
    mates = c.within(1, of=victim, side="ally")
    pick = c.choose(mates, "who takes the free melee basic attack", optional=True)
    if pick is not None:
        c.grant_attack(pick, on=victim, attack_bonus=swing)


@power(
    "p2348",
    level=1,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.WEAPON],
    attack=Attack(CHA, vs=AC),
)
def p2348(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2), c.cha_mod)
    for mate in c.within(5, side="ally"):
        if mate != c.me:
            c.bonus("attack", 1, on=mate, until=When.EONT, kind="power")


@power(
    "p2349",
    level=1,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(CHA, vs=FORT),
)
def p2349(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", c.cha_mod, dtype=DamageType.THUNDER)
        c.push(1)
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            if mate != c.me:
                c.slide(1, on=mate)


@power(
    "p2350",
    level=1,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.WEAPON],
    attack=Attack(CHA, vs=AC),
)
def p2350(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
        c.grants_advantage(on=victim, to="allies", until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.cha_mod)

    def onward(ev: Hit) -> None:
        if ev.attacker == c.me:
            c.grants_advantage(on=ev.target, to="allies", until=When.EONT)

    c.watch(Hit, onward, until=When.ENCOUNTER, on=c.me, label="p2350")


@power(
    "p2352",
    level=1,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.WEAPON],
    attack=Attack(CHA, vs=AC),
)
def p2352(c: Cast) -> None:
    """The mark belongs to the ally, not to the bard, so it goes in by hand:
    `c.mark` names the caster as the marker and cannot say anyone else."""
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
        mates = [a for a in c.within(5, side="ally") if a != c.me]
        pick = c.choose(mates, "which ally marks the target", optional=True)
        if pick is not None:
            c.mark(on=victim, by=pick)
    else:
        c.half_damage(c.w(2), c.cha_mod)

    spent: dict[int, int] = {}

    def relay(ev: Hit) -> None:
        if ev.attacker != c.me or spent.get(0) == c.world.round:
            return
        mates = [a for a in c.within(5, side="ally") if a != c.me]
        pick = c.choose(mates, "which ally marks the enemy", optional=True)
        if pick is None:
            return
        spent[0] = c.world.round
        c.mark(on=ev.target, by=pick)

    c.watch(Hit, relay, until=When.ENCOUNTER, on=c.me, label="p2352")
