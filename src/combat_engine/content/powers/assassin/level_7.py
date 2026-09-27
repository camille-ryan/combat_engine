"""Assassin, level 7."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DEX,
    ENCOUNTER,
    ONE_CREATURE,
    STANDARD,
    WILL,
    Attack,
    Cast,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    TurnEnd,
    TurnStart,
    When,
    power,
    spread,
)
from combat_engine.engine.query import squares


@power(
    "p16478",
    level=7,
    cls="assassin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION, Keyword.IMPLEMENT, Keyword.PSYCHIC, Keyword.SHADOW],
    attack=Attack(DEX, vs=WILL),
)
def p16478(c: Cast) -> None:
    """"Including those with blindsight or tremorsense" is a sense model the
    engine does not keep, and "or until you attack" is a break condition
    `c.invisible` does not take -- `c.hide` has it, but not the clock."""
    victim = c.target
    if c.strike():
        c.damage("2d10", c.dex_mod, dtype=DamageType.PSYCHIC)
    for foe in c.enemies():
        if foe != victim:
            c.invisible(to=foe, on=c.me, until=When.EONT)


@power(
    "p9431",
    level=7,
    cls="assassin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.SHADOW, Keyword.TELEPORTATION, Keyword.WEAPON],
    attack=Attack(DEX, vs=AC),
)
def p9431(c: Cast) -> None:
    """The deferred free action is resolved at once: nothing here can hand a
    creature an action to spend on a later turn."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        free = [s for s in spread({c.here}, 1) if not c.in_squares([s])]
        if free:
            c.teleport(5, who=victim, to=sorted(free)[0])


@power(
    "p9432",
    level=7,
    cls="assassin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.PSYCHIC, Keyword.SHADOW, Keyword.TELEPORTATION],
    attack=Attack(DEX, vs=WILL),
)
def p9432(c: Cast) -> None:
    """The build rider grants a minor-action teleport on a later turn, which
    is an action nothing can hand out, so it is dropped."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage("1d10", c.dex_mod, dtype=DamageType.PSYCHIC)

        def late(ev: TurnEnd) -> None:
            if ev.actor == victim and len(c.within(2, of=victim)) > 1:
                c.flat(10, dtype=DamageType.PSYCHIC, on=victim)

        c.watch(TurnEnd, late, until=When.ENCOUNTER, once=True)


@power(
    "p9433",
    level=7,
    cls="assassin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.SHADOW, Keyword.WEAPON],
    attack=Attack(DEX, vs=AC),
)
def p9433(c: Cast) -> None:
    """Sharing the target's square is `share=True`; moving with it is riding
    it, which is the relation that makes a creature carry another. "Any melee
    or ranged attack that misses you hits the target instead" needs a redirect
    from inside the attack's own interrupt window and is dropped."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.shift(1, to=c.there, share=True)
        c.insubstantial(on=c.me, until=When.SONT)
        c.ride(on=victim)

        def step_off(ev: TurnStart) -> None:
            if ev.actor != c.me:
                return
            free = [s for s in spread(squares(c.world, victim), 1) if not c.in_squares([s])]
            if free:
                c.slide(1, on=c.me, to=sorted(free)[0])

        c.watch(TurnStart, step_off, until=When.ENCOUNTER, once=True)


@power(
    "p9434",
    level=7,
    cls="assassin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.SHADOW, Keyword.WEAPON],
    attack=Attack(DEX, vs=AC),
)
def p9434(c: Cast) -> None:
    """Printed against the shroud target, and the Hit rider spends shrouds;
    neither is modelled, so it takes one creature and the rider is dropped."""
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        if c.build("f1s0") and c.con_mod > 0:
            c.temp_hp(c.con_mod, on=c.me)
