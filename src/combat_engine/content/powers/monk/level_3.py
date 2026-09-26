"""Monk, level 3: encounter attacks, all of them two-part disciplines."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DEX,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    DamageType,
    Keyword,
    Melee,
    When,
    power,
)
from combat_engine.engine.events import DamageApplied, Miss

IMPLEMENT = [Keyword.IMPLEMENT]


@power(
    "p11216",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p11216(c: Cast) -> None:
    """`c.save` follows the target, so the monk's own saving throw has to
    name itself. The speed bonus printed on the move half is dropped: it is
    measured per attack suffered mid-move, which nothing counts."""
    if c.strike():
        c.damage("2d10", c.dex_mod)
        if c.save(on=c.me, bonus=c.wis_mod):
            c.flat(c.wis_mod)
    if c.last:
        c.move(c.speed_of() + 2)


@power(
    "p11218",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p11218(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.dex_mod)
        c.prone()
    if c.last:
        if c.str_mod > 0:
            c.resist(c.str_mod, until=When.EONT)
        c.shift(2)


@power(
    "p13146",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(DEX, vs=WILL),
)
def p13146(c: Cast) -> None:
    """Blinding yourself is printed as an Effect, so it happens before the
    attack and whether or not it lands. Blindsight has no representation,
    so only the blindness is written."""
    if c.first:
        c.blinded(on=c.me, until=When.SONT)
    if c.strike():
        c.damage("1d8", c.dex_mod)
        c.damage("1d8", 0, dtype=DamageType.PSYCHIC)
    if not c.last:
        return
    near = c.within(1, side="other")
    if near:
        partner = c.choose(near, "swap places with")
        if partner is not None:
            c.swap(partner)


@power(
    "p13148",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*IMPLEMENT, Keyword.THUNDER],
    attack=Attack(DEX, vs=FORT),
)
def p13148(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.dex_mod)
        victim = c.target
        busy: list[int] = []

        def echo(ev: DamageApplied) -> None:
            # The payout is damage, which is the event being answered.
            if busy or ev.target != victim or ev.amount <= 0:
                return
            busy.append(1)
            c.flat(3 + c.str_mod, dtype=DamageType.THUNDER, on=victim)

        c.watch(DamageApplied, echo, until=When.SONT, once=True)
    if c.last:
        c.move(c.speed_of() + 2)


@power(
    "p13150",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p13150(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.dex_mod)
        armed = c.wielding("light blade") or c.wielding("spear")
        c.slide(c.con_mod if armed else 2)
    if not c.last:
        return
    near = c.within(1, side="other")
    if near:
        anchor = c.choose(near, "jump to a square beside")
        if anchor is not None:
            c.no_provoke(until=When.EOT)
            c.run_at(anchor)


@power(
    "p13152",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=WILL),
)
def p13152(c: Cast) -> None:
    """The damage is owed only if the pull actually brings the target into
    contact, so adjacency is asked after the pull rather than before."""
    if c.strike():
        c.pull(1)
        if c.adjacent():
            c.damage("2d6", c.dex_mod)
            c.prone()
        armed = c.wielding("mace") or c.wielding("staff")
        c.bonus(AC, c.con_mod if armed else 2, on=c.me, until=When.EONT)
    if c.last:
        c.no_provoke(until=When.EOT)
        c.move(c.speed_of())


@power(
    "p13223",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p13223(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.dex_mod)
        c.push(3)
    if c.last:
        c.shift(1)


@power(
    "p15984",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p15984(c: Cast) -> None:
    """"Cannot charge" has nothing to hang on -- a charge is an action kind,
    not a row -- so only the slow is written."""
    if c.strike():
        c.damage("2d8", c.dex_mod)
        c.slowed(until=When.EONT)
    if not c.last:
        return
    c.shift(3)
    near = c.within(1, side="other")
    if near:
        partner = c.choose(near, "swap places with")
        if partner is not None:
            c.swap(partner)


@power(
    "p16150",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p16150(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.dex_mod)
        for defence in (AC, FORT, REF, WILL):
            c.penalty(defence, 2, until=When.EONT)
    if c.last:
        c.shift(1)
        c.bonus(AC, 2, on=c.me, until=When.EONT)
        c.bonus(FORT, 2, on=c.me, until=When.EONT)


@power(
    "p16152",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*IMPLEMENT, Keyword.FIRE],
    attack=Attack(DEX, vs=REF),
)
def p16152(c: Cast) -> None:
    """Partial concealment is written as the +2 it is worth to the monk's
    defences, for the length of the movement it is printed on."""
    if c.strike():
        c.damage("2d8", c.dex_mod)
        victim = c.target
        busy: list[int] = []

        def bloom(ev: DamageApplied) -> None:
            if busy or ev.target != victim or ev.amount <= 0:
                return
            busy.append(1)
            burn = 3 + c.cha_mod
            c.flat(burn, dtype=DamageType.FIRE, on=victim)
            for foe in c.within(1, of=victim, side="enemy"):
                if foe != victim:
                    c.flat(burn, dtype=DamageType.FIRE, on=foe)

        c.watch(DamageApplied, bloom, until=When.SONT, once=True)
    if not c.last:
        return
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=c.me, until=When.EOT, kind="concealment")
    c.move(c.speed_of() + 2)


@power(
    "p16154",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*IMPLEMENT, Keyword.COLD],
    attack=Attack(DEX, vs=FORT),
)
def p16154(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.dex_mod, dtype=DamageType.COLD)
        c.immobilized(until=When.EONT)
    if c.last:
        c.immobilized(on=c.me, until=When.SONT)
        c.resist(3 + c.str_mod, until=When.SONT)


@power(
    "p7459",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p7459(c: Cast) -> None:
    """The crowd is counted before the swing, so a target knocked out of
    the press by the hit does not change the arithmetic."""
    press = 2 * len(c.within(1, side="enemy"))
    if c.strike():
        c.damage("2d8", c.dex_mod)
        if press:
            c.flat(press)
    if not c.last:
        return

    def fumbled(ev: Miss) -> None:
        if ev.target == c.me and getattr(ev, "opportunity", False):
            c.grants_advantage(on=ev.attacker, to="me", until=When.EOT)

    hold = c.watch(Miss, fumbled, until=When.EOT)
    c.move(c.speed_of() + 2)
    c.world.effects.end(hold, "movement over")


@power(
    "p7460",
    level=3,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*IMPLEMENT, Keyword.THUNDER],
    attack=Attack(DEX, vs=FORT),
)
def p7460(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.dex_mod, dtype=DamageType.THUNDER)
        splash = [f for f in c.within(1, of=c.target, side="enemy") if f != c.target]
        if splash:
            unlucky = c.choose(splash, "who catches the echo")
            if unlucky is not None:
                c.damage("1d10", 0, dtype=DamageType.THUNDER, on=unlucky)
    if not c.last:
        return
    near = c.within(1, side="enemy")
    if near:
        ignored = c.choose(near, "whose reach to slip")
        if ignored is not None:
            c.no_provoke(from_=ignored, until=When.EOT)
    c.move(c.speed_of() + 2)
