"""Bard, level 5: the dailies.

Two of them judge whether a creature "moves closer" over the course of its
own turn, which is a distance taken at `TurnStart` and compared at `TurnEnd`
-- `Moved` fires square by square and would pay out for a step taken on the
way round an obstacle.
"""

from __future__ import annotations

from combat_engine.content.powers.bard._shared import gap
from combat_engine.engine import *

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]
ARCANE_WEAPON = [Keyword.ARCANE, Keyword.WEAPON]


@power(
    "p12514",
    level=5,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.TELEPORTATION],
    attack=Attack(CHA, vs=WILL),
)
def p12514(c: Cast) -> None:
    """Banishment is `Condition.REMOVED`, which is what "removed from play"
    already means here; coming back is the condition lapsing."""
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.PSYCHIC)
    c.condition(Condition.REMOVED, until=When.SAVE_ENDS)


@power(
    "p2370",
    level=5,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p2370(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.PSYCHIC)
        held = c.effect("p2370 satire", on=victim, until=When.SAVE_ENDS)
    else:
        c.half_damage("2d6", c.cha_mod, dtype=DamageType.PSYCHIC)
        held = None
    c.push(3, on=victim)
    if held is None:
        return
    start: dict[int, int] = {}

    def began(ev: TurnStart) -> None:
        if ev.actor == victim and not ev.ghost:
            start[0] = c.distance(to=victim)

    def ended(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != victim or held.ended:
            return
        was = start.pop(0, None)
        if was is not None and c.distance(to=victim) < was:
            c.damage("1d6", c.cha_mod, dtype=DamageType.PSYCHIC, on=victim)
            c.dazed(on=victim, until=When.EOTNT)

    c.watch(TurnStart, began, until=When.ENCOUNTER, on=c.me, label="p2370 start")
    c.watch(TurnEnd, ended, until=When.ENCOUNTER, on=c.me, label="p2370 end")


@power(
    "p2975",
    level=5,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p2975(c: Cast) -> None:
    """The Effect is dropped whole: nothing announces a recharge, and nothing
    hands a spent encounter power back."""
    if c.strike():
        c.damage("3d8", c.cha_mod, dtype=DamageType.PSYCHIC)
    else:
        c.half_damage("3d8", c.cha_mod, dtype=DamageType.PSYCHIC)


@power(
    "p3100",
    level=5,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(CHA, vs=WILL),
)
def p3100(c: Cast) -> None:
    """"Cannot take move actions" is immobilised: it is the condition that says
    the creature stays put while a forced slide still works on it, which is
    exactly the shape of this row."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.PSYCHIC)
        held = c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=victim)

        def shove(ev: TurnEnd) -> None:
            if ev.ghost or ev.actor != victim or held is None or held.ended:
                return
            c.slide(5, on=victim)

        c.watch(TurnEnd, shove, until=When.ENCOUNTER, on=c.me, label="p3100")
        return

    c.half_damage("2d8", c.cha_mod, dtype=DamageType.PSYCHIC)
    c.immobilized(on=victim, until=When.EOTNT)
    spent: list[int] = []

    def once(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != victim or spent:
            return
        spent.append(1)
        c.slide(5, on=victim)

    c.watch(TurnEnd, once, until=When.EOTNT, on=victim, label="p3100 miss")


@power(
    "p4994",
    level=5,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CHARM],
    attack=Attack(CHA, vs=WILL),
)
def p4994(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.EONT, on=victim)
    others = [f for f in c.enemies() if f != victim]
    mark = c.choose(others, "who the target swings at")
    if mark is not None and victim is not None:
        c.basic(who=victim, on=mark)


@power(
    "p4995",
    level=5,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CHA, vs=WILL),
)
def p4995(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.COLD)
        c.slowed(until=When.SAVE_ENDS)
    else:
        c.half_damage("2d6", c.cha_mod, dtype=DamageType.COLD)
        c.slowed(until=When.EONT)
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            if mate != c.me:
                c.slide(3, on=mate)


@power(
    "p4996",
    level=5,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=AC),
)
def p4996(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        c.half_damage(c.w(3), c.cha_mod, dtype=DamageType.PSYCHIC)
        return
    c.damage(c.w(3), c.cha_mod, dtype=DamageType.PSYCHIC)
    mates = [a for a in c.within(5, side="ally") if a != c.me]
    keeper = c.choose(mates, "which ally the target must not approach")
    if keeper is None:
        return
    held = c.effect("p4996 aversion", on=victim, until=When.SAVE_ENDS)
    if held is None:
        return
    start: dict[int, int] = {}

    def began(ev: TurnStart) -> None:
        if ev.actor == victim and not ev.ghost:
            start[0] = gap(c, keeper, victim)

    def ended(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != victim or held.ended:
            return
        was = start.pop(0, None)
        if was is not None and gap(c, keeper, victim) < was:
            c.flat(c.cha_mod, dtype=DamageType.PSYCHIC, on=victim)

    c.watch(TurnStart, began, until=When.ENCOUNTER, on=c.me, label="p4996 start")
    c.watch(TurnEnd, ended, until=When.ENCOUNTER, on=c.me, label="p4996 end")


@power(
    "p5685",
    level=5,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p5685(c: Cast) -> None:
    """The upgrade is written onto the live result as well as onto the event:
    the body reads the result when it rolls its damage, and everything else
    reads the event."""
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
    else:
        c.half_damage(c.w(2), c.cha_mod)
    mates = [a for a in c.within(10, side="ally") if a != c.me]
    keeper = c.choose(mates, "whose blow might turn critical")
    if keeper is None:
        return
    spent: list[int] = []

    def sharpen(ev: Hit) -> None:
        if spent or ev.critical or ev.attacker != keeper or ev.target != victim:
            return
        if c.roll("1d20") < 15:
            return
        spent.append(1)
        ev.critical = True
        res = getattr(ev, "result", None)
        if res is not None:
            res.critical = True

    c.watch(Hit, sharpen, until=When.ENCOUNTER, on=c.me, label="p5685")


@power(
    "p5686",
    level=5,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CHA, vs=FORT),
)
def p5686(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.FIRE)
    else:
        c.half_damage("2d6", c.cha_mod, dtype=DamageType.FIRE)
    sting = c.cha_mod

    def flare(ev: Hit) -> None:
        if ev.target == victim and ev.attacker in c.allies():
            c.flat(sting, dtype=DamageType.FIRE, on=victim)

    c.watch(Hit, flare, until=When.ENCOUNTER, on=c.me, label="p5686")


@power(
    "p5687",
    level=5,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.HEALING],
    attack=Attack(CHA, vs=FORT),
)
def p5687(c: Cast) -> None:
    """"The first time during each of its turns" is `once_per_round` on
    `c.on_attack`, which is the errata'd line rather than the printed one."""
    victim = c.target
    if c.strike():
        c.damage("2d6", c.cha_mod)
    else:
        c.half_damage("2d6", c.cha_mod)
    mend = c.cha_mod

    def comfort(ev: AttackDeclared) -> None:
        mates = c.allies()
        if not mates:
            return
        nearest = min(mates, key=lambda a: gap(c, a, victim))
        c.heal(mend, on=nearest)

    c.on_attack(
        comfort, by=victim, until=When.ENCOUNTER, once_per_round=True, label="p5687"
    )
