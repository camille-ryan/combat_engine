"""Bard, level 1 continued: the rest of the attacks."""

from __future__ import annotations

from combat_engine.content.powers.bard._shared import gap
from combat_engine.engine import *

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]
ARCANE_WEAPON = [Keyword.ARCANE, Keyword.WEAPON]


@power(
    "p4987",
    level=1,
    cls="bard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p4987(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(), c.cha_mod)
    which = c.choose([AC, FORT, REF, WILL], "which defence the penalty lands on")
    if which is not None:
        c.penalty(which, 2, until=When.EONT)


@power(
    "p4988",
    level=1,
    cls="bard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p4988(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    c.damage(c.w(), c.cha_mod)
    given = c.con_mod

    def reward(ev: Hit) -> None:
        if ev.target == victim and ev.attacker in c.allies():
            c.temp_hp(given, on=ev.attacker)

    if given > 0:
        c.watch(Hit, reward, until=When.EONT, on=c.me, label="p4988")


@power(
    "p4989",
    level=1,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.HEALING],
    attack=Attack(CHA, vs=WILL),
)
def p4989(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.PSYCHIC)
    mend = c.cha_mod

    def pay(ev: Hit) -> None:
        if ev.target == victim and ev.attacker in c.allies():
            c.heal(mend, on=ev.attacker)

    c.watch(Hit, pay, until=When.ENCOUNTER, on=c.me, label="p4989")


@power(
    "p5676",
    level=1,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(CHA, vs=REF),
)
def p5676(c: Cast) -> None:
    """`crit_range` is read off the **attacker**, so the widened range is hung
    on everybody who might swing, gated on this being the creature they swing
    at. Hung on the target it would never be read."""
    if not c.strike():
        return
    victim = c.target
    c.damage("1d10", c.cha_mod, dtype=DamageType.THUNDER)
    for who in [c.me, *c.allies()]:
        c.bonus(
            "crit_range", 2, on=who, until=When.EONT,
            when=lambda ctx: ctx.get("target") == victim,
        )


@power(
    "p5677",
    level=1,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(CHA, vs=FORT),
)
def p5677(c: Cast) -> None:
    """The hiding-and-concealment half is dropped -- nothing takes concealment
    away from one creature. The burn is the rest of it, and it is an Effect
    line, so it lands whether or not the attack did."""
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.THUNDER)
    c.ongoing(5, DamageType.THUNDER, until=When.SAVE_ENDS)


@power(
    "p5679",
    level=1,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p5679(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
    else:
        c.half_damage(c.w(2), c.cha_mod)
    mates = [a for a in c.within(10, side="ally") if a != c.me]
    keeper = c.choose(mates, "which ally the target must stay beside")
    if keeper is None:
        return
    held = c.effect("p5679 tether", on=victim, until=When.SAVE_ENDS)
    c.bonus(
        "attack", 2, on=keeper, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") == victim, kind="power")
    if held is None:
        return

    def sting(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != victim or held.ended:
            return
        if gap(c, keeper, victim) > 1:
            c.flat(5, on=victim)

    c.watch(TurnEnd, sting, until=When.ENCOUNTER, on=c.me, label="p5679")


@power(
    "p6608",
    level=1,
    cls="bard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(CHA, vs=FORT),
)
def p6608(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    c.damage("1d8", c.cha_mod, dtype=DamageType.THUNDER)
    if c.con_mod > 0:
        c.slide(c.con_mod, on=victim)
    if [x for x in c.within(1, of=victim) if x != victim]:
        return
    mates = [a for a in c.within(10, side="ally") if a != c.me]
    pick = c.choose(mates, "which ally makes the free ranged basic attack", optional=True)
    if pick is not None:
        c.basic(who=pick, on=victim, ranged=True)


@power(
    "p7403",
    level=1,
    cls="bard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p7403(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.pull(2)


@power(
    "p7425",
    level=1,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p7425(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.PSYCHIC)

    def drag(ev: Hit) -> None:
        if ev.target == victim and ev.attacker in c.allies():
            c.slowed(on=victim, until=When.EOTNT)

    c.watch(Hit, drag, until=When.ENCOUNTER, on=c.me, label="p7425")
