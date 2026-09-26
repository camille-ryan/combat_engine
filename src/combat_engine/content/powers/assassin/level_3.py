"""Assassin, level 3."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DEX,
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
    DamageType,
    Hit,
    Keyword,
    Melee,
    TurnEnd,
    When,
    power,
    spread,
)


@power(
    "p9419",
    level=3,
    cls="assassin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.ILLUSION, Keyword.SHADOW, Keyword.WEAPON],
    attack=Attack(DEX, vs=WILL),
)
def p9419(c: Cast) -> None:
    """"Any enemy that ends its turn adjacent to the target" is read from the
    caster's side of the board: the target lashes out at its own allies, which
    is the only reading that makes the row worth using."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(), c.dex_mod)
        plus = c.cha_mod if c.build("second-cha") else 0

        def lash(ev: TurnEnd) -> None:
            if ev.actor == victim or ev.actor not in c.enemies():
                return
            if c.adjacent_to(victim, ev.actor):
                c.grant_attack(victim, on=ev.actor, attack_bonus=plus)

        c.watch(TurnEnd, lash, until=When.EONT)


@power(
    "p9420",
    level=3,
    cls="assassin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT, Keyword.SHADOW],
    attack=Attack(DEX, vs=FORT),
)
def p9420(c: Cast) -> None:
    """The Effect is permission to hide on worse terms than usual, so it is
    written as the hide itself, offered once for the whole blast."""
    if c.strike():
        c.damage("2d6", c.dex_mod, dtype=DamageType.COLD)
    if c.last and c.may("slip out of sight", who=c.me):
        for seen_by in c.targets:
            c.hide(from_=seen_by, until=When.EOT)


@power(
    "p9421",
    level=3,
    cls="assassin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.SHADOW, Keyword.TELEPORTATION, Keyword.WEAPON],
    attack=Attack(DEX, vs=AC),
    charges=True,
)
def p9421(c: Cast) -> None:
    """Printed against "your assassin's shroud target"; shrouds are not
    modelled, so it takes any one creature. `charges=True` because the
    teleport is the row's Effect line -- without it the engine measures the
    weapon's reach first and refuses every use the row exists for."""
    victim = c.target
    if victim is None:
        return
    free = [s for s in spread({c.there}, 1) if not c.in_squares([s])]
    if free:
        c.teleport(5, to=sorted(free)[0])
    if c.strike():
        c.damage(c.w(2), c.dex_mod)


@power(
    "p9422",
    level=3,
    cls="assassin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.SHADOW, Keyword.WEAPON],
    attack=Attack(DEX, vs=REF),
)
def p9422(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        step = 3 if c.build("second-con") else 2
        c.slide(step, on=victim)

        def jerked(ev: Hit) -> None:
            if ev.target == victim:
                c.slide(step - 1, on=victim)

        c.watch(Hit, jerked, until=When.EONT)
